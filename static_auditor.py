"""
Static code auditing tool specialized for AstrBot plugins.
Runs ruff + pylint + mypy against a generated main.py and
applies AstrBot-specific checks. Designed to be enabled by a single
config switch (config['static_code_audit'] == True by default).

All tool dependencies are expected to be installable via requirements.txt
(ruff, pylint, mypy). The auditor will degrade gracefully if a tool is not
available in the runtime environment.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ToolIssue:
    tool: str
    file: str
    line: int
    column: int
    code: str
    message: str
    severity: str  # "error" | "warning" | "info"

    def to_text(self) -> str:
        loc = f"{self.file}:{self.line}:{self.column}" if self.line or self.column else self.file
        return f"[{self.tool}] {loc} {self.code}: {self.message}"


@dataclass
class AuditResult:
    success: bool
    issues: List[ToolIssue] = field(default_factory=list)
    skipped_tools: List[str] = field(default_factory=list)
    tool_errors: Dict[str, str] = field(default_factory=dict)

    def counts(self) -> Dict[str, int]:
        total = len(self.issues)
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        infos = sum(1 for i in self.issues if i.severity == "info")
        return {"total": total, "errors": errors, "warnings": warnings, "infos": infos}

    def flat_messages(self, limit: Optional[int] = None) -> List[str]:
        msgs = [i.to_text() for i in self.issues]
        return msgs if limit is None else msgs[:limit]


class StaticCodeAuditor:
    def __init__(self, config: Any):
        self.config = config

    async def audit_code(self, code: str, plugin_name: str = "generated_plugin") -> AuditResult:
        tmpdir = tempfile.mkdtemp(prefix="astrbot_audit_")
        try:
            # Write code file
            main_path = os.path.join(tmpdir, "main.py")
            with open(main_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Write configs tuned for AstrBot plugins
            await self._write_ruff_config(tmpdir)
            await self._write_pylint_config(tmpdir)
            await self._write_mypy_config(tmpdir)

            issues: List[ToolIssue] = []
            skipped: List[str] = []
            tool_errors: Dict[str, str] = {}

            # Run tools (best-effort)
            ruff_issues, err = await self._run_ruff(main_path, tmpdir)
            if err:
                tool_errors["ruff"] = err
            if ruff_issues is None:
                skipped.append("ruff")
            else:
                issues.extend(ruff_issues)

            pylint_issues, err = await self._run_pylint(main_path, tmpdir)
            if err:
                tool_errors["pylint"] = err
            if pylint_issues is None:
                skipped.append("pylint")
            else:
                issues.extend(pylint_issues)

            mypy_issues, err = await self._run_mypy(main_path, tmpdir)
            if err:
                tool_errors["mypy"] = err
            if mypy_issues is None:
                skipped.append("mypy")
            else:
                issues.extend(mypy_issues)

            # AstrBot-specific checks (string/regex based, fast)
            issues.extend(self._astrbot_specific_checks(main_path))

            success = True
            return AuditResult(success=success, issues=issues, skipped_tools=skipped, tool_errors=tool_errors)
        finally:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass

    async def _write_ruff_config(self, root: str) -> None:
        pyproject = f"""
[tool.ruff]
target-version = "py310"
line-length = 120
fix = false
show-fixes = false
select = [
    "E",  # pycodestyle
    "F",  # pyflakes
    "W",  # warning
    "N",  # pep8-naming
    "I",  # isort
    "UP", # pyupgrade
    "ASYNC", # asyncio
    "B",  # bugbear
]
ignore = [
    "D",      # pydocstyle (docs in generated code can be minimal)
    "ANN",    # typing annotations may be partial in generated code
]

[tool.ruff.isort]
force-single-line = false
known-first-party = []
profile = "black"

[tool.ruff.per-file-ignores]
"main.py" = ["D", "ANN"]
""".strip()
        path = os.path.join(root, "pyproject.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(pyproject + "\n")

    async def _write_pylint_config(self, root: str) -> None:
        pylintrc = """
[MASTER]
ignore=venv,.venv,build,dist

[MESSAGES CONTROL]
disable=
    missing-docstring,
    invalid-name,
    too-few-public-methods,
    too-many-arguments,
    too-many-instance-attributes,
    no-member,
    import-error,
    too-many-locals,
    too-many-branches,
    too-many-statements,
    duplicate-code

[FORMAT]
max-line-length=120

[BASIC]
good-names=_,i,j,k,ex,Run,_,e,ctx,req,resp,uid,cid,id
""".strip()
        path = os.path.join(root, ".pylintrc")
        with open(path, "w", encoding="utf-8") as f:
            f.write(pylintrc + "\n")

    async def _write_mypy_config(self, root: str) -> None:
        mypy_ini = """
[mypy]
python_version = 3.10
ignore_missing_imports = True
warn_unused_ignores = False
warn_redundant_casts = False
warn_no_return = False
check_untyped_defs = False
no_implicit_optional = False
allow_redefinition = True
follow_imports = silent
show_error_codes = False
pretty = True
""".strip()
        path = os.path.join(root, "mypy.ini")
        with open(path, "w", encoding="utf-8") as f:
            f.write(mypy_ini + "\n")

    def _classify_ruff(self, code: str) -> str:
        # Treat E and F as errors; others as warnings
        if code.startswith("E") or code.startswith("F"):
            return "error"
        return "warning"

    async def _run_ruff(self, main_path: str, cwd: str) -> Tuple[Optional[List[ToolIssue]], Optional[str]]:
        cmd = [sys.executable, "-m", "ruff", "check", "--exit-zero", "--format", "json", main_path]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out_b, err_b = await proc.communicate()
            if proc.returncode is None:
                # Should not happen, but guard
                return None, "ruff did not finish"
            if not out_b:
                return [], None
            try:
                data = json.loads(out_b.decode("utf-8", errors="ignore") or "[]")
            except Exception as e:  # noqa: BLE001
                return None, f"failed to parse ruff output: {e}"
            issues: List[ToolIssue] = []
            for item in data:
                loc = item.get("location", {})
                issues.append(
                    ToolIssue(
                        tool="ruff",
                        file=os.path.basename(main_path),
                        line=int(loc.get("row", 0)),
                        column=int(loc.get("column", 0)),
                        code=str(item.get("code", "RUF")),
                        message=str(item.get("message", "")),
                        severity=self._classify_ruff(str(item.get("code", "RUF"))),
                    )
                )
            return issues, None
        except FileNotFoundError:
            return None, None
        except Exception as e:  # noqa: BLE001
            return None, str(e)

    def _classify_pylint(self, msg_type: str, symbol: str) -> str:
        t = (msg_type or "").lower()
        # map pylint types to severity
        if t in {"fatal", "error"}:
            return "error"
        if t in {"warning"}:
            return "warning"
        return "info"

    async def _run_pylint(self, main_path: str, cwd: str) -> Tuple[Optional[List[ToolIssue]], Optional[str]]:
        # Prefer module execution to avoid PATH reliance
        cmd = [
            sys.executable,
            "-m",
            "pylint",
            "--output-format=json",
            "-r",
            "n",
            os.path.basename(main_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out_b, err_b = await proc.communicate()
            # Pylint returns non-zero for findings; treat output parse as success regardless of return code
            text = out_b.decode("utf-8", errors="ignore")
            if not text.strip():
                return [], None
            try:
                data = json.loads(text)
            except Exception as e:  # noqa: BLE001
                # sometimes pylint may emit non-JSON prelude; attempt recovery
                m = re.search(r"\[\s*{.*}\s*]", text, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except Exception:  # noqa: BLE001
                        return None, f"failed to parse pylint output: {e}"
                else:
                    return None, f"failed to parse pylint output: {e}"
            issues: List[ToolIssue] = []
            for item in data if isinstance(data, list) else []:
                issues.append(
                    ToolIssue(
                        tool="pylint",
                        file=os.path.basename(item.get("path", os.path.basename(main_path))),
                        line=int(item.get("line", 0) or 0),
                        column=int(item.get("column", 0) or 0),
                        code=str(item.get("symbol", "pylint")),
                        message=str(item.get("message", "")),
                        severity=self._classify_pylint(str(item.get("type", "")), str(item.get("symbol", ""))),
                    )
                )
            return issues, None
        except FileNotFoundError:
            return None, None
        except Exception as e:  # noqa: BLE001
            return None, str(e)

    async def _run_mypy(self, main_path: str, cwd: str) -> Tuple[Optional[List[ToolIssue]], Optional[str]]:
        # Try module API first
        try:
            from mypy import api as mypy_api  # type: ignore

            stdout, stderr, exit_status = mypy_api.run(
                ["--config-file", os.path.join(cwd, "mypy.ini"), os.path.basename(main_path)]
            )
            # mypy returns non-zero on issues; parse stdout
            issues: List[ToolIssue] = []
            for line in stdout.splitlines():
                # Format: main.py:line: column: error: message  [code]
                m = re.match(r"^(.*?):(\d+):(?::\s*(\d+):)?\s*(error|warning|note):\s*(.*)$", line.strip())
                if not m:
                    # Try another common pattern without column
                    m = re.match(r"^(.*?):(\d+):\s*(error|warning|note):\s*(.*)$", line.strip())
                if m:
                    file_, ln, col_or_type, type_or_msg, maybe_msg = m.groups()
                    if maybe_msg is None:
                        sev = (type_or_msg or "error").lower()
                        msg = str(col_or_type or "")
                        col = 0
                    else:
                        col = int(col_or_type or 0)
                        sev = (type_or_msg or "error").lower()
                        msg = maybe_msg
                    issues.append(
                        ToolIssue(
                            tool="mypy",
                            file=os.path.basename(file_ or os.path.basename(main_path)),
                            line=int(ln or 0),
                            column=col,
                            code="mypy",
                            message=msg,
                            severity="error" if sev == "error" else ("warning" if sev == "warning" else "info"),
                        )
                    )
            return issues, None
        except Exception:
            # Fallback to subprocess
            cmd = [sys.executable, "-m", "mypy", "--config-file", os.path.join(cwd, "mypy.ini"), os.path.basename(main_path)]
            try:
                proc = await asyncio.create_subprocess_exec(*cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                out_b, err_b = await proc.communicate()
                text = out_b.decode("utf-8", errors="ignore")
                issues: List[ToolIssue] = []
                for line in text.splitlines():
                    m = re.match(r"^(.*?):(\d+):(\d+):\s*(error|warning|note):\s*(.*)$", line.strip())
                    if not m:
                        m = re.match(r"^(.*?):(\d+):\s*(error|warning|note):\s*(.*)$", line.strip())
                    if not m:
                        continue
                    file_, ln, col, sev, msg = m.groups() if len(m.groups()) == 5 else (m.group(1), m.group(2), 0, m.group(3), m.group(4))
                    issues.append(
                        ToolIssue(
                            tool="mypy",
                            file=os.path.basename(file_ or os.path.basename(main_path)),
                            line=int(ln or 0),
                            column=int(col or 0),
                            code="mypy",
                            message=msg,
                            severity="error" if (sev or "error").lower() == "error" else ("warning" if (sev or "").lower() == "warning" else "info"),
                        )
                    )
                return issues, None
            except FileNotFoundError:
                return None, None
            except Exception as e:  # noqa: BLE001
                return None, str(e)

    def _astrbot_specific_checks(self, main_path: str) -> List[ToolIssue]:
        issues: List[ToolIssue] = []
        try:
            with open(main_path, "r", encoding="utf-8") as f:
                src = f.read()
        except Exception:
            return issues

        base = os.path.basename(main_path)

        # Must import logger from astrbot.api, forbid logging module directly
        if "from astrbot.api import logger" not in src:
            issues.append(
                ToolIssue(
                    tool="astrbot",
                    file=base,
                    line=1,
                    column=1,
                    code="ASTR001",
                    message="必须通过 'from astrbot.api import logger' 获取日志对象",
                    severity="error",
                )
            )
        if re.search(r"\bimport\s+logging\b|logging\.", src):
            issues.append(
                ToolIssue(
                    tool="astrbot",
                    file=base,
                    line=1,
                    column=1,
                    code="ASTR002",
                    message="禁止使用 logging 模块，请统一使用 astrbot.api.logger",
                    severity="error",
                )
            )

        # Ensure filter is imported from astrbot.api.event
        if not re.search(r"from\s+astrbot\.api\.event\s+import\s+filter", src):
            issues.append(
                ToolIssue(
                    tool="astrbot",
                    file=base,
                    line=1,
                    column=1,
                    code="ASTR003",
                    message="必须从 astrbot.api.event 导入 filter 以注册事件监听器",
                    severity="error",
                )
            )

        # Ensure a Star subclass exists
        if not re.search(r"class\s+\w+\(\s*Star\s*\):", src):
            issues.append(
                ToolIssue(
                    tool="astrbot",
                    file=base,
                    line=1,
                    column=1,
                    code="ASTR004",
                    message="未检测到继承自 Star 的插件主类",
                    severity="error",
                )
            )

        # Hooks must be async and have event in signature - soft check by pattern
        for hook in ["on_llm_request", "on_llm_response", "on_decorating_result", "after_message_sent"]:
            # If hook appears, try to ensure async def and (self, event, ...)
            m = re.search(rf"(async\s+def\s+{hook}\s*\(\s*self\s*,\s*event\s*:\s*\w+.*\):)", src)
            if hook in src and not m:
                issues.append(
                    ToolIssue(
                        tool="astrbot",
                        file=base,
                        line=1,
                        column=1,
                        code="ASTR005",
                        message=f"检测到 {hook}，其定义必须为 async 且包含 (self, event, ...) 签名",
                        severity="warning",
                    )
                )

        return issues
