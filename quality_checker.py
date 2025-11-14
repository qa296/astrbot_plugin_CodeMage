"""CodeMage 静态分析适配器。

负责对 LLM 生成的插件代码执行 ruff、pylint、mypy 等静态检查，
并将检查结果整理为便于后续自动修复与提示的结构化数据。
"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from astrbot.api import AstrBotConfig, logger

from .directory_detector import DirectoryDetector


DEFAULT_RUFF_CONFIG = textwrap.dedent(
    """
    [tool.ruff]
    line-length = 120
    target-version = "py310"
    extend-select = ["I"]
    """
).strip()

DEFAULT_PYLINT_RC = textwrap.dedent(
    """
    [MASTER]
    ignore=__pycache__
    extension-pkg-whitelist=
    unsafe-load-any-extension=no
    jobs=0

    [MESSAGES CONTROL]
    disable=missing-module-docstring,missing-class-docstring,missing-function-docstring,too-few-public-methods,too-many-arguments,too-many-locals,too-many-branches,too-many-statements,too-many-instance-attributes,too-many-return-statements,too-many-public-methods,logging-format-interpolation

    [FORMAT]
    max-line-length=120
    good-names=i,j,k,e,ex,Run,_,pk

    [TYPECHECK]
    ignored-modules=astrbot,astrbot.api,astrbot.api.event,astrbot.api.platform,astrbot.api.star,astrbot.core,astrbot.core.utils
    ignored-classes=Context,Star,AstrMessageEvent

    [SIMILARITIES]
    min-similarity-lines=8

    [REPORTS]
    output-format=text
    score=no
    """
).strip()

DEFAULT_MYPY_CONFIG = textwrap.dedent(
    """
    [mypy]
    python_version = 3.10
    ignore_missing_imports = True
    warn_unused_configs = True
    warn_unused_ignores = False
    warn_redundant_casts = True
    warn_unreachable = True
    """
).strip()


class QualityChecker:
    """在临时目录中对生成代码执行本地静态检查。"""

    def __init__(self, config: AstrBotConfig, directory_detector: DirectoryDetector):
        self.config = config
        self.directory_detector = directory_detector
        self.logger = logger

    # ------------------------------------------------------------------
    # 配置解析
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "y", "on"}:
                return True
            if lowered in {"false", "0", "no", "n", "off"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def resolve_settings(self) -> Dict[str, Any]:
        """解析 quality_checks 配置，返回带有默认值的设置。"""
        settings: Dict[str, Any] = {
            "enabled": True,
            "run_ruff": True,
            "run_pylint": True,
            "run_mypy": True,
            "max_retries": 2,
            "timeout": 60,
            "ruff_config_path": None,
            "pylint_rc_path": None,
            "mypy_config_path": None,
            "ruff_args": [],
            "pylint_args": [],
            "mypy_args": [],
        }

        raw = self.config.get("quality_checks", {})
        if isinstance(raw, dict):
            for key in ("enabled", "run_ruff", "run_pylint", "run_mypy"):
                if key in raw:
                    settings[key] = self._coerce_bool(raw.get(key), settings[key])

            if "max_retries" in raw:
                settings["max_retries"] = self._coerce_int(raw.get("max_retries"), settings["max_retries"])
            if "timeout" in raw:
                timeout = self._coerce_int(raw.get("timeout"), settings["timeout"])
                settings["timeout"] = timeout if timeout > 0 else settings["timeout"]

            for key, dest in (
                ("ruff_config_path", "ruff_config_path"),
                ("pylint_rc_path", "pylint_rc_path"),
                ("mypy_config_path", "mypy_config_path"),
            ):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    settings[dest] = value.strip()

            for key, dest in (
                ("ruff_args", "ruff_args"),
                ("pylint_args", "pylint_args"),
                ("mypy_args", "mypy_args"),
            ):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    try:
                        settings[dest] = shlex.split(value)
                    except ValueError:
                        settings[dest] = value.strip().split()
                elif isinstance(value, (list, tuple)):
                    settings[dest] = [str(item) for item in value]

        return settings

    # ------------------------------------------------------------------
    # 对外主方法
    # ------------------------------------------------------------------
    async def run_checks(
        self,
        code: str,
        plugin_name: str,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """在隔离环境中运行质量检查并返回汇总结果。"""
        resolved = settings or self.resolve_settings()

        if not resolved.get("enabled", True):
            summary = "静态检查未启用（quality_checks.enabled = false）"
            self.logger.info(summary)
            return {
                "success": True,
                "passed_tools": [],
                "failed_tools": [],
                "skipped_tools": [],
                "issues": [],
                "suggestions": [],
                "warnings": [],
                "summary": summary,
                "details": [],
            }

        active_tools = [
            tool
            for tool, flag in (
                ("ruff", resolved.get("run_ruff", True)),
                ("pylint", resolved.get("run_pylint", True)),
                ("mypy", resolved.get("run_mypy", True)),
            )
            if flag
        ]

        if not active_tools:
            summary = "未配置任何静态检查工具，已跳过"
            self.logger.info(summary)
            return {
                "success": True,
                "passed_tools": [],
                "failed_tools": [],
                "skipped_tools": [],
                "issues": [],
                "suggestions": [],
                "warnings": [],
                "summary": summary,
                "details": [],
            }

        timeout = resolved.get("timeout", 60)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = 60

        with tempfile.TemporaryDirectory(prefix="codemage_quality_") as tmp_dir:
            temp_path = Path(tmp_dir)
            main_path = temp_path / "main.py"
            main_path.write_text(code, encoding="utf-8")
            # 帮助类型检查识别为包
            (temp_path / "__init__.py").write_text("# generated by CodeMage\n", encoding="utf-8")

            configs = self._prepare_configs(temp_path, resolved)
            env = self._build_env(temp_path)

            results: List[Dict[str, Any]] = []
            for tool in active_tools:
                command = self._build_command(tool, configs, resolved)
                if not command:
                    results.append({
                        "tool": tool,
                        "status": "skipped",
                        "message": "未提供执行命令",
                        "stdout": "",
                        "stderr": "",
                        "exit_code": None,
                        "timeout": False,
                        "duration": 0.0,
                        "command": [],
                    })
                    continue

                result = await self._run_tool(tool, command, tmp_dir, env, timeout)
                results.append(result)

        return self._summarise_results(results, plugin_name)

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------
    def _prepare_configs(self, temp_path: Path, settings: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """查找或生成各工具的配置文件。"""
        configs: Dict[str, Optional[str]] = {
            "ruff": settings.get("ruff_config_path"),
            "pylint": settings.get("pylint_rc_path"),
            "mypy": settings.get("mypy_config_path"),
        }

        if not configs["ruff"]:
            configs["ruff"] = self._find_existing_config(["pyproject.toml", "ruff.toml"])
        if not configs["ruff"]:
            configs["ruff"] = self._write_default_config(temp_path, "pyproject.toml", DEFAULT_RUFF_CONFIG)

        if not configs["pylint"]:
            configs["pylint"] = self._find_existing_config([".pylintrc", "pylintrc"])
        if not configs["pylint"]:
            configs["pylint"] = self._write_default_config(temp_path, ".pylintrc", DEFAULT_PYLINT_RC)

        if not configs["mypy"]:
            configs["mypy"] = self._find_existing_config(["mypy.ini", ".mypy.ini"])
        if not configs["mypy"]:
            configs["mypy"] = self._write_default_config(temp_path, "mypy.ini", DEFAULT_MYPY_CONFIG)

        return configs

    def _build_env(self, temp_path: Path) -> Dict[str, str]:
        env = os.environ.copy()
        python_paths: List[str] = []
        python_paths.append(str(temp_path))
        plugin_root = Path(__file__).parent
        python_paths.append(str(plugin_root))
        astrbot_root = self.directory_detector.detect_astrbot_installation()
        if astrbot_root:
            python_paths.append(str(astrbot_root))

        for entry in sys.path:
            if entry:
                python_paths.append(str(entry))

        existing = env.get("PYTHONPATH")
        if existing:
            python_paths.append(existing)

        deduped: List[str] = []
        for path in python_paths:
            if path and path not in deduped:
                deduped.append(path)

        env["PYTHONPATH"] = os.pathsep.join(deduped)
        return env

    def _build_command(self, tool: str, configs: Dict[str, Optional[str]], settings: Dict[str, Any]) -> List[str]:
        if tool == "ruff":
            command = [sys.executable, "-m", "ruff", "check", "main.py", "--no-cache"]
            if configs.get("ruff"):
                command += ["--config", configs["ruff"]]
            command += settings.get("ruff_args", [])
            return command
        if tool == "pylint":
            command = [sys.executable, "-m", "pylint", "main.py", "--score", "no", "--output-format", "parseable"]
            if configs.get("pylint"):
                command += ["--rcfile", configs["pylint"]]
            command += settings.get("pylint_args", [])
            return command
        if tool == "mypy":
            command = [sys.executable, "-m", "mypy", "main.py", "--python-version", "3.10"]
            if configs.get("mypy"):
                command += ["--config-file", configs["mypy"]]
            command += settings.get("mypy_args", [])
            return command
        return []

    async def _run_tool(
        self,
        tool: str,
        command: List[str],
        tmp_dir: str,
        env: Dict[str, str],
        timeout: float,
    ) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmp_dir,
                env=env,
            )
        except FileNotFoundError:
            message = f"未找到命令：{' '.join(command)}"
            self.logger.warning(message)
            return {
                "tool": tool,
                "status": "skipped",
                "message": message,
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "timeout": False,
                "duration": 0.0,
                "command": command,
            }
        except Exception as exc:  # pylint: disable=broad-except
            message = f"执行 {tool} 失败：{exc}"
            self.logger.exception(message)
            return {
                "tool": tool,
                "status": "failed",
                "message": message,
                "stdout": "",
                "stderr": str(exc),
                "exit_code": None,
                "timeout": False,
                "duration": 0.0,
                "command": command,
            }

        timeout_flag = False
        stdout_bytes: bytes
        stderr_bytes: bytes
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            timeout_flag = True
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()

        duration = time.monotonic() - start
        stdout = stdout_bytes.decode("utf-8", errors="ignore")
        stderr = stderr_bytes.decode("utf-8", errors="ignore")
        exit_code = process.returncode

        combined_lower = (stdout + "\n" + stderr).lower()
        status: str
        message: str

        if timeout_flag:
            status = "failed"
            message = f"{tool} 执行超时"
        elif exit_code == 0:
            status = "passed"
            message = f"{tool} 检查通过"
        elif self._is_tool_missing(tool, combined_lower):
            status = "skipped"
            message = f"{tool} 未安装，已跳过"
        else:
            status = "failed"
            summary_line = self._extract_summary_line(stdout, stderr)
            message = summary_line or f"{tool} 检查失败（退出码 {exit_code}）"

        return {
            "tool": tool,
            "status": status,
            "message": message,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "timeout": timeout_flag,
            "duration": duration,
            "command": command,
        }

    @staticmethod
    def _is_tool_missing(tool: str, combined_lower: str) -> bool:
        target = tool.lower()
        return (
            f"no module named '{target}'" in combined_lower
            or f'no module named "{target}"' in combined_lower
            or f"no module named {target}" in combined_lower
        )

    @staticmethod
    def _extract_summary_line(stdout: str, stderr: str) -> str:
        for text in (stdout, stderr):
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    return stripped
        return ""

    @staticmethod
    def _truncate(text: str, limit: int = 1600) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "\n... (输出已截断)"

    def _summarise_results(self, results: List[Dict[str, Any]], plugin_name: str) -> Dict[str, Any]:
        passed = [r for r in results if r.get("status") == "passed"]
        failed = [r for r in results if r.get("status") == "failed"]
        skipped = [r for r in results if r.get("status") == "skipped"]

        issues: List[str] = []
        suggestions: List[str] = []
        warnings: List[str] = []

        for item in failed:
            tool = item["tool"]
            detail = self._truncate((item.get("stdout", "") + "\n" + item.get("stderr", "")).strip())
            summary_line = item.get("message") or self._extract_summary_line(item.get("stdout", ""), item.get("stderr", ""))
            summary_line = summary_line or f"{tool} 检测出问题"
            issues.append(f"[{tool}] {summary_line}")
            suggestions.append(f"请根据 {tool} 的输出修复问题：\n{detail}" if detail else f"请根据 {tool} 的提示修复问题。")

        for item in skipped:
            tool = item["tool"]
            warning = item.get("message") or f"{tool} 被跳过"
            warnings.append(f"⚠️ {warning}")

        summary_parts: List[str] = []
        if passed:
            summary_parts.append("通过：" + ", ".join(r["tool"] for r in passed))
        if failed:
            summary_parts.append("失败：" + ", ".join(r["tool"] for r in failed))
        if skipped:
            summary_parts.append(
                "跳过：" + ", ".join(f"{r['tool']}（{r.get('message', '已跳过')}）" for r in skipped)
            )

        summary = (
            "代码静态检查结果：" + "；".join(summary_parts)
            if summary_parts
            else "代码静态检查已完成"
        )

        self.logger.info("%s -> %s", plugin_name, summary)

        return {
            "success": not failed,
            "passed_tools": [r["tool"] for r in passed],
            "failed_tools": [r["tool"] for r in failed],
            "skipped_tools": [r["tool"] for r in skipped],
            "issues": issues,
            "suggestions": suggestions,
            "warnings": warnings,
            "summary": summary,
            "details": results,
        }

    def _find_existing_config(self, filenames: Sequence[str]) -> Optional[str]:
        checked: List[Path] = []
        search_dirs: List[Path] = [Path(__file__).parent]
        astrbot_root = self.directory_detector.detect_astrbot_installation()
        if astrbot_root:
            search_dirs.append(Path(astrbot_root))
        search_dirs.append(Path.cwd())

        for base in search_dirs:
            try:
                base = base.resolve()
            except FileNotFoundError:
                continue
            if base in checked:
                continue
            checked.append(base)
            for name in filenames:
                candidate = base / name
                if candidate.exists():
                    return str(candidate)
        return None

    @staticmethod
    def _write_default_config(temp_path: Path, filename: str, content: str) -> str:
        path = temp_path / filename
        path.write_text(content + "\n", encoding="utf-8")
        return str(path)
