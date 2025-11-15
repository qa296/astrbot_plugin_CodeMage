"""
AstrBot 插件代码静态审查工具

- 集成 ruff / pylint / mypy 三种静态分析器（若未安装则自动跳过）
- 内置 AstrBot 专用规则集（不依赖外部工具也可运行）
- 输出统一的审查结果，供生成流程使用
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger


@dataclass
class ToolReport:
    name: str
    available: bool
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class AuditResult:
    approved: bool
    satisfaction_score: int
    reason: str
    issues: List[str]
    suggestions: List[str]
    tool_reports: Dict[str, ToolReport] = field(default_factory=dict)


class AstrBotPluginAuditor:
    """AstrBot 插件静态审查器。

    优先运行内置的 AstrBot 特定规则；
    如果系统中安装了 ruff/pylint/mypy，则会将其报告合并到结果中。
    """

    def __init__(self, python_version: str = "3.10") -> None:
        self.python_version = python_version

    # ------------------------------ 外部工具运行 ------------------------------
    def _write_temp_project(self, code: str) -> Tuple[str, str]:
        """将代码写入临时目录，并生成针对性的配置文件。

        Returns:
            (root_dir, main_file_path)
        """
        root = tempfile.mkdtemp(prefix="astrbot_audit_")
        main_py = os.path.join(root, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write(code)

        # Ruff 配置（尽量精选规则，避免噪音）
        pyproject = f"""
[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = [
  "E",   # pycodestyle errors
  "F",   # pyflakes
  "W",   # pycodestyle warnings
  "B",   # flake8-bugbear
  "I",   # isort
  "UP",  # pyupgrade
  "PL",  # Pylint rules (ruff 内置子集)
]
ignore = [
  "PLR0913",  # 允许较多参数（AstrBot handler 常见）
  "PLR2004",  # 魔法数字警告
]
        """.strip()
        with open(os.path.join(root, "pyproject.toml"), "w", encoding="utf-8") as f:
            f.write(pyproject)

        # pylint 配置（弱化风格类告警，聚焦缺陷）
        pylintrc = f"""
[MASTER]
py-version={self.python_version}

[MESSAGES CONTROL]
disable=
    C,
    R,
    W1203,  # logging-fstring-interpolation（AstrBot logger 接口允许）
    W1514,  # unspecified-encoding（生成代码经常使用 utf-8，ruff 也会提示）

[FORMAT]
max-line-length=120
        """.strip()
        with open(os.path.join(root, ".pylintrc"), "w", encoding="utf-8") as f:
            f.write(pylintrc)

        # mypy 配置（忽略外部依赖类型缺失）
        mypy_ini = f"""
[mypy]
python_version = {self.python_version}
ignore_missing_imports = True
follow_imports = silent
warn_unused_ignores = True
no_implicit_optional = False
check_untyped_defs = False
        """.strip()
        with open(os.path.join(root, "mypy.ini"), "w", encoding="utf-8") as f:
            f.write(mypy_ini)
        return root, main_py

    def _run_subprocess(self, cmd: List[str], cwd: Optional[str]) -> Tuple[int, str, str]:
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except FileNotFoundError:
            return 127, "", ""
        except Exception as e:
            return 1, "", str(e)

    def _run_ruff(self, root: str, main_file: str) -> ToolReport:
        report = ToolReport(name="ruff", available=shutil.which("ruff") is not None)
        if not report.available:
            return report
        code, out, err = self._run_subprocess(
            ["ruff", "check", main_file, "--output-format", "json"], cwd=root
        )
        # ruff 即使有问题也会返回非 0，这里统一解析输出
        try:
            findings = json.loads(out or "[]")
        except Exception:
            findings = []
        for item in findings:
            rule = item.get("code", "")
            msg = item.get("message", "")
            loc = item.get("location", {})
            line = loc.get("row", "?")
            col = loc.get("column", "?")
            report.issues.append(f"[ruff {rule}] L{line}:{col} {msg}")
        return report

    def _run_pylint(self, root: str, main_file: str) -> ToolReport:
        report = ToolReport(name="pylint", available=shutil.which("pylint") is not None)
        if not report.available:
            return report
        code, out, err = self._run_subprocess(
            ["pylint", "-f", "json", os.path.basename(main_file)], cwd=root
        )
        try:
            findings = json.loads(out or "[]")
        except Exception:
            findings = []
        for item in findings:
            sym = item.get("symbol", "")
            msg = item.get("message", "")
            line = item.get("line", "?")
            col = item.get("column", "?")
            report.issues.append(f"[pylint {sym}] L{line}:{col} {msg}")
        return report

    def _run_mypy(self, root: str, main_file: str) -> ToolReport:
        report = ToolReport(name="mypy", available=shutil.which("mypy") is not None)
        if not report.available:
            return report
        code, out, err = self._run_subprocess(
            [
                "mypy",
                os.path.basename(main_file),
                "--config-file",
                "mypy.ini",
                "--show-error-codes",
                "--hide-error-context",
                "--no-error-summary",
                "--no-color-output",
            ],
            cwd=root,
        )
        lines = (out or "").splitlines()
        for ln in lines:
            # 格式: main.py:12:4: error: MSG  [code]
            m = re.match(r"^([^:]+):(\d+):(\d+):\s+(error|note|warning):\s+(.*)$", ln.strip())
            if m:
                line = m.group(2)
                col = m.group(3)
                kind = m.group(4)
                msg = m.group(5)
                report.issues.append(f"[mypy {kind}] L{line}:{col} {msg}")
        return report

    # ------------------------------ AstrBot 专用规则 ------------------------------
    def _audit_astrbot_rules(self, code: str) -> Tuple[List[str], List[str], List[str]]:
        """返回 (critical_issues, issues, suggestions)"""
        critical: List[str] = []
        issues: List[str] = []
        suggestions: List[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            critical.append(f"代码存在语法错误: {e}")
            return critical, issues, suggestions

        # 1) 日志规范：必须且只能 from astrbot.api import logger；禁止 logging / loguru
        imports_logger = False
        uses_logging_module = False
        uses_loguru = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                names = {n.name for n in node.names}
                if mod == "astrbot.api" and ("logger" in names):
                    imports_logger = True
                if mod.startswith("logging"):
                    uses_logging_module = True
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "logging" or alias.name.startswith("logging."):
                        uses_logging_module = True
                    if alias.name.startswith("loguru"):
                        uses_loguru = True
        if not imports_logger:
            critical.append("必须使用 'from astrbot.api import logger' 获取日志对象")
            suggestions.append("在文件顶部添加: from astrbot.api import logger")
        if uses_logging_module:
            critical.append("禁止使用内置 logging 模块，请改用 astrbot.api.logger")
            suggestions.append("将所有 logging.* 调用替换为 logger.*，并确保已从 astrbot.api 导入 logger")
        if uses_loguru:
            critical.append("禁止使用第三方日志库 loguru，请改用 astrbot.api.logger")
            suggestions.append("移除 loguru 相关代码，改用 astrbot.api.logger")

        # 2) filter 装饰器导入检查
        has_filter_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "astrbot.api.event":
                if any(n.name == "filter" for n in node.names):
                    has_filter_import = True
                    break
        # 若代码使用了 @filter.xxx 但并未导入 filter，则报错
        uses_filter_decorator = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Attribute) and isinstance(dec.value, ast.Name) and dec.value.id == "filter":
                        uses_filter_decorator = True
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if isinstance(dec.func.value, ast.Name) and dec.func.value.id == "filter":
                            uses_filter_decorator = True
        if uses_filter_decorator and not has_filter_import:
            critical.append("检测到使用 @filter 装饰器，但未正确导入：from astrbot.api.event import filter")
            suggestions.append("请添加: from astrbot.api.event import filter")

        # 3) main.py / 插件类：至少存在一个继承 Star 的类
        has_star_subclass = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    # 简单匹配 Star 标识
                    if (isinstance(base, ast.Name) and base.id == "Star") or (
                        isinstance(base, ast.Attribute) and base.attr == "Star"
                    ):
                        has_star_subclass = True
        if not has_star_subclass:
            critical.append("未找到继承自 Star 的插件类。请定义 class MyPlugin(Star): ...")

        # 4) LLM 钩子签名与 yield 限制
        disallow_yield_hooks = {"on_llm_request", "on_llm_response", "on_decorating_result", "after_message_sent"}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                decorators = node.decorator_list
                is_llm_hook = False
                for dec in decorators:
                    # @filter.on_xxx()
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if isinstance(dec.func.value, ast.Name) and dec.func.value.id == "filter":
                            attr = dec.func.attr
                            if attr in disallow_yield_hooks:
                                is_llm_hook = True
                            if attr in {"on_llm_request", "on_llm_response"}:
                                # 参数个数检查：self, event, req/resp
                                total_args = len(node.args.args)
                                if total_args < 3:
                                    critical.append(
                                        f"{attr} 钩子函数参数必须为 (self, event, xxx)，当前参数个数为 {total_args}"
                                    )
                                    suggestions.append(
                                        f"修改 {attr} 定义，例如：async def {func_name}(self, event: AstrMessageEvent, obj): ..."
                                    )
                if is_llm_hook:
                    # 检查函数体中是否出现 yield 语句
                    has_yield = any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in ast.walk(node))
                    if has_yield:
                        critical.append(
                            f"在 {func_name} 中检测到 yield 语句。该钩子中禁止使用 yield，请改用 await event.send(...)"
                        )
                        suggestions.append(
                            f"将 {func_name} 内的 yield event.xxx_result(...) 改为 await event.send(event.xxx_result(...))"
                        )

        # 5) @filter.llm_tool 与 @filter.permission_type 不可同用
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                has_llm_tool = False
                has_perm_type = False
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if isinstance(dec.func.value, ast.Name) and dec.func.value.id == "filter":
                            attr = dec.func.attr
                            if attr == "llm_tool":
                                has_llm_tool = True
                            if attr == "permission_type":
                                has_perm_type = True
                if has_llm_tool and has_perm_type:
                    critical.append("@filter.llm_tool 装饰的方法上不支持再使用 @filter.permission_type 进行权限控制")

        # 6) 事件监听器签名检查：除 on_astrbot_loaded 外均应包含 event 参数
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                has_filter_deco = False
                deco_names = set()
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if isinstance(dec.func.value, ast.Name) and dec.func.value.id == "filter":
                            has_filter_deco = True
                            deco_names.add(dec.func.attr)
                if has_filter_deco and ("on_astrbot_loaded" not in deco_names):
                    # 检查参数
                    if not node.args.args or len(node.args.args) < 2:
                        issues.append(
                            f"事件监听器 {node.name} 缺少 event 参数，应为 (self, event, ...)"
                        )
                        suggestions.append(
                            f"修改 {node.name} 签名为 (self, event: AstrMessageEvent, ...)"
                        )

        # 7) 禁止使用 requests，同步网络 I/O 视为问题
        if re.search(r"\bimport\s+requests\b|\bfrom\s+requests\s+import\b", code):
            critical.append("检测到使用 requests 库。请改用 aiohttp 或 httpx 等异步库")
            suggestions.append("示例：使用 aiohttp.ClientSession 进行异步 HTTP 请求")

        # 8) 高危 API 检查（与 utils.validate_plugin_code 保持一致）
        dangerous = [r"eval\s*\(", r"exec\s*\(", r"__import__\s*\(", r"subprocess\.", r"os\.system\s*\("]
        for pat in dangerous:
            if re.search(pat, code):
                critical.append(f"检测到潜在危险调用：{pat}")

        return critical, issues, suggestions

    # ------------------------------ 汇总与打分 ------------------------------
    def _score(self, critical_cnt: int, normal_cnt: int, tool_issue_cnt: int) -> int:
        score = 100
        score -= critical_cnt * 15
        score -= normal_cnt * 5
        # 外部工具发现的问题每条扣 3 分，但最多扣 30 分
        score -= min(tool_issue_cnt * 3, 30)
        return max(0, min(100, score))

    def audit(self, code: str) -> AuditResult:
        """对代码进行静态审查并给出统一结果。"""
        # 1) AstrBot 专用规则
        critical, normal, sugg = self._audit_astrbot_rules(code)

        # 2) 外部工具（尽量不影响主流程，缺失则跳过）
        temp_root: Optional[str] = None
        tool_reports: Dict[str, ToolReport] = {}
        try:
            temp_root, main_file = self._write_temp_project(code)
            ruff_r = self._run_ruff(temp_root, main_file)
            pylint_r = self._run_pylint(temp_root, main_file)
            mypy_r = self._run_mypy(temp_root, main_file)
            tool_reports = {
                "ruff": ruff_r,
                "pylint": pylint_r,
                "mypy": mypy_r,
            }
        except Exception as e:
            logger.warning(f"运行外部工具时发生异常：{e}")
        finally:
            if temp_root and os.path.isdir(temp_root):
                try:
                    shutil.rmtree(temp_root)
                except Exception:
                    pass

        tool_issue_cnt = sum(len(r.issues) for r in tool_reports.values() if r.available)

        # 汇总问题
        all_issues: List[str] = []
        all_suggestions: List[str] = []
        all_issues.extend(critical)
        all_issues.extend(normal)
        all_suggestions.extend(sugg)
        # 附加工具输出（压缩为问题列表，避免过长）
        for name, rep in tool_reports.items():
            if rep.available and rep.issues:
                # 仅保留前若干条，避免刷屏
                for item in rep.issues[:50]:
                    all_issues.append(item)

        approved = len(critical) == 0
        score = self._score(len(critical), len(normal), tool_issue_cnt)
        reason = (
            "通过静态审查" if approved else "存在不满足 AstrBot 规范的关键问题，请修复后重试"
        )
        return AuditResult(
            approved=approved,
            satisfaction_score=score,
            reason=reason,
            issues=all_issues,
            suggestions=all_suggestions,
            tool_reports=tool_reports,
        )
