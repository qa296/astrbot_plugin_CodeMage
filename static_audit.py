"""
Static code auditing utilities tailored for AstrBot plugins.
Runs ruff + pylint + mypy (if available) on in-memory code and
adds AstrBot-specific rule checks. Designed to be used inside
step 5 (代码审查与修复) without introducing a new workflow step.

This module avoids shelling out by preferring library APIs. If a tool
is not available at runtime, it degrades gracefully and still performs
project-specific validations so generation can proceed.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class StaticAuditOptions:
    # General toggles
    enable_ruff: bool = True
    enable_pylint: bool = True
    enable_mypy: bool = True

    # Ruff options
    ruff_select: Optional[List[str]] = None
    ruff_ignore: Optional[List[str]] = None
    ruff_line_length: int = 120

    # Pylint options
    pylint_disable: Optional[List[str]] = None
    pylint_enable: Optional[List[str]] = None
    pylint_max_line_length: int = 120

    # Mypy options
    mypy_ignore_missing_imports: bool = True
    mypy_strict: bool = False


@dataclass
class Issue:
    tool: str
    code: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    severity: str = "warning"  # one of: info, warning, error

    def to_text(self) -> str:
        loc = f"L{self.line}" if self.line else ""
        return f"[{self.tool}:{self.code}]{' ' + loc if loc else ''} {self.message}"


@dataclass
class StaticAuditResult:
    approved: bool
    satisfaction_score: int
    reason: str
    issues: List[Issue] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def to_review_payload(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "satisfaction_score": self.satisfaction_score,
            "reason": self.reason,
            "issues": [i.to_text() for i in self.issues],
            "suggestions": list(self.suggestions),
        }


class StaticCodeAuditor:
    def __init__(self, options: StaticAuditOptions | None = None):
        self.options = options or StaticAuditOptions()

    def _write_temp_python_file(self, code: str, metadata: Dict[str, Any]) -> Tuple[str, str]:
        """Create a temp dir with a main.py and optional typing helpers.
        Returns (tmp_dir, main_path).
        """
        tmp_dir = tempfile.mkdtemp(prefix="codemage_static_audit_")
        main_path = os.path.join(tmp_dir, "main.py")
        with open(main_path, "w", encoding="utf-8") as f:
            f.write(code)
        # Write a minimal pyproject for ruff, if needed
        try:
            pyproj_path = os.path.join(tmp_dir, "pyproject.toml")
            with open(pyproj_path, "w", encoding="utf-8") as f:
                f.write(
                    """
[tool.ruff]
line-length = 120
# Ruff will be further configured via CLI args if provided
""".strip()
                )
        except Exception:
            pass
        return tmp_dir, main_path

    def _severity_for_ruff(self, code: str) -> str:
        # Use common ruff prefix meanings
        if code.startswith("E") or code.startswith("F"):
            return "error"
        if code.startswith("W"):
            return "warning"
        return "info"

    def _run_ruff(self, tmp_dir: str) -> List[Issue]:
        if not self.options.enable_ruff:
            return []
        try:
            # Prefer programmatic API via ruff.__main__ to avoid subprocess
            import sys
            import contextlib
            import ruff.__main__ as ruff_main  # type: ignore

            args = [
                "ruff",
                "check",
                tmp_dir,
                "--format",
                "json",
                "--quiet",
                "--line-length",
                str(self.options.ruff_line_length),
            ]
            if self.options.ruff_select:
                args += ["--select", ",".join(self.options.ruff_select)]
            if self.options.ruff_ignore:
                args += ["--ignore", ",".join(self.options.ruff_ignore)]

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                saved = list(sys.argv)
                try:
                    sys.argv = args
                    try:
                        ruff_main.main()
                    except SystemExit:
                        # Ruff CLI might call sys.exit; treat as normal termination
                        pass
                finally:
                    sys.argv = saved
            out = buf.getvalue().strip()
            issues: List[Issue] = []
            if out:
                try:
                    data = json.loads(out)
                    for item in data:
                        issues.append(
                            Issue(
                                tool="ruff",
                                code=item.get("code", "RUFF"),
                                message=item.get("message", ""),
                                line=item.get("location", {}).get("row"),
                                column=item.get("location", {}).get("column"),
                                severity=self._severity_for_ruff(item.get("code", "")),
                            )
                        )
                except Exception:
                    # If JSON parsing fails, fallback to text (unlikely with --format json)
                    for line in out.splitlines():
                        if not line.strip():
                            continue
                        issues.append(Issue(tool="ruff", code="RUFF", message=line, severity="warning"))
            return issues
        except Exception:
            return []

    def _run_pylint(self, main_path: str) -> List[Issue]:
        if not self.options.enable_pylint:
            return []
        try:
            from pylint.lint import Run as PylintRun  # type: ignore
            try:
                # Newer pylint
                from pylint.reporters.json_reporter import JSONReporter  # type: ignore
            except Exception:
                # Older pylint
                from pylint.reporters.json import JSONReporter  # type: ignore

            output = io.StringIO()
            reporter = JSONReporter(output=output)

            args = [
                main_path,
                f"--max-line-length={self.options.pylint_max_line_length}",
                "--score=n",
                "--reports=n",
            ]
            if self.options.pylint_disable:
                args.append(f"--disable={','.join(self.options.pylint_disable)}")
            if self.options.pylint_enable:
                args.append(f"--enable={','.join(self.options.pylint_enable)}")

            # Pylint will write JSON to reporter
            try:
                PylintRun(args, reporter=reporter, do_exit=False)
            except SystemExit:
                pass

            data_text = output.getvalue().strip()
            issues: List[Issue] = []
            if data_text:
                try:
                    data = json.loads(data_text)
                    for item in data:
                        typ = (item.get("type") or "warning").lower()
                        sev = "error" if typ in {"error", "fatal"} else ("warning" if typ in {"warning", "convention", "refactor"} else "info")
                        issues.append(
                            Issue(
                                tool="pylint",
                                code=item.get("symbol", "pylint"),
                                message=item.get("message", ""),
                                line=item.get("line"),
                                column=item.get("column"),
                                severity=sev,
                            )
                        )
                except Exception:
                    # If JSON parsing fails, provide raw text as a single issue
                    issues.append(Issue(tool="pylint", code="pylint", message=data_text, severity="warning"))
            return issues
        except Exception:
            return []

    def _run_mypy(self, main_path: str) -> List[Issue]:
        if not self.options.enable_mypy:
            return []
        try:
            from mypy import api as mypy_api  # type: ignore
            args = [main_path]
            if self.options.mypy_ignore_missing_imports:
                args.append("--ignore-missing-imports")
            if self.options.mypy_strict:
                args.append("--strict")
            args.append("--no-error-summary")
            args.append("--hide-error-context")

            stdout, stderr, status = mypy_api.run(args)
            combined = "\n".join([s for s in [stdout, stderr] if s])
            issues: List[Issue] = []
            for line in combined.splitlines():
                line = line.strip()
                # Typical mypy line: /tmp/main.py:12: error: Something [code]
                if ": error:" in line or ": note:" in line or ": warning:" in line:
                    try:
                        path_part, rest = line.split(": ", 1)
                        # extract line number
                        parts = path_part.split(":")
                        lineno = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                        msg = rest
                    except Exception:
                        lineno = None
                        msg = line
                    sev = "error" if ": error:" in line else ("warning" if ": warning:" in line else "info")
                    # Extract square-bracket code if present
                    code = "mypy"
                    lb = msg.rfind("[")
                    rb = msg.rfind("]")
                    if lb != -1 and rb != -1 and rb > lb:
                        code = msg[lb + 1 : rb]
                    issues.append(Issue(tool="mypy", code=code, message=msg, line=lineno, severity=sev))
            return issues
        except Exception:
            return []

    def _run_astrbot_specific_checks(self, code: str) -> List[Issue]:
        issues: List[Issue] = []
        code_low = code.lower()
        # logger import check
        if "from astrbot.api import logger" not in code:
            issues.append(
                Issue(
                    tool="astrbot",
                    code="ASTR001",
                    message="必须从 astrbot.api 导入 logger (from astrbot.api import logger)",
                    severity="error",
                )
            )
        if "import logging" in code_low or "logging.getlogger" in code_low:
            issues.append(
                Issue(
                    tool="astrbot",
                    code="ASTR002",
                    message="禁止使用 logging 模块，请改用 from astrbot.api import logger",
                    severity="error",
                )
            )
        # filter import check
        if "from astrbot.api.event import filter" not in code:
            issues.append(
                Issue(
                    tool="astrbot",
                    code="ASTR003",
                    message="必须从 astrbot.api.event 导入 filter 对象 (from astrbot.api.event import filter)",
                    severity="error",
                )
            )
        # Star subclass check
        if "class" in code and "Star" in code and "class" not in code.split("Star")[0]:
            # not reliable; add a simple presence check
            pass
        else:
            if "class" not in code or "Star" not in code:
                issues.append(
                    Issue(
                        tool="astrbot",
                        code="ASTR004",
                        message="main.py 必须包含一个继承自 Star 的插件类",
                        severity="error",
                    )
                )
        # Dangerous calls
        dangerous = ["eval(", "exec(", "__import__(", "os.system(", "subprocess."]
        for pat in dangerous:
            if pat in code:
                issues.append(
                    Issue(
                        tool="astrbot",
                        code="ASTR005",
                        message=f"检测到潜在危险调用: {pat}",
                        severity="error",
                    )
                )
        return issues

    def analyze(self, code: str, metadata: Dict[str, Any]) -> StaticAuditResult:
        # Write code to temp directory
        tmp_dir, main_path = self._write_temp_python_file(code, metadata)
        try:
            all_issues: List[Issue] = []
            # AstrBot-specific checks first
            all_issues.extend(self._run_astrbot_specific_checks(code))
            # Tool-based checks
            all_issues.extend(self._run_ruff(tmp_dir))
            all_issues.extend(self._run_pylint(main_path))
            all_issues.extend(self._run_mypy(main_path))

            # Compute score: start at 100, subtract per-issue with weights
            score = 100
            for item in all_issues:
                if item.tool == "mypy":
                    delta = 12 if item.severity == "error" else 6
                elif item.tool == "pylint":
                    delta = 10 if item.severity == "error" else 5
                elif item.tool == "ruff":
                    delta = 6 if item.severity == "error" else 3
                else:  # astrbot rules are important
                    delta = 15 if item.severity == "error" else 8
                score -= delta
            score = max(0, min(100, score))

            approved = score >= 80 and not any(i.severity == "error" and i.tool == "astrbot" for i in all_issues)

            reason = (
                "静态审查通过" if approved else "静态审查未通过：存在需要修复的问题"
            )

            suggestions: List[str] = []
            if any(i.tool == "astrbot" and i.code == "ASTR001" for i in all_issues):
                suggestions.append("确保使用: from astrbot.api import logger")
            if any(i.tool == "astrbot" and i.code == "ASTR003" for i in all_issues):
                suggestions.append("确保使用: from astrbot.api.event import filter")
            if any(i.tool == "astrbot" and i.code == "ASTR004" for i in all_issues):
                suggestions.append("确保 main.py 定义继承自 Star 的插件类")
            if any(i.tool == "astrbot" and i.code == "ASTR005" for i in all_issues):
                suggestions.append("移除危险函数调用 (eval/exec/os.system/subprocess 等)")

            return StaticAuditResult(
                approved=approved,
                satisfaction_score=score,
                reason=reason,
                issues=all_issues,
                suggestions=suggestions,
            )
        finally:
            # Clean temp files
            try:
                import shutil
                shutil.rmtree(tmp_dir)
            except Exception:
                pass


def options_from_config(config: Any) -> StaticAuditOptions:
    """Build StaticAuditOptions from AstrBotConfig-like mapping."""
    try:
        ruff_select = config.get("ruff_select") if isinstance(config.get("ruff_select"), list) else None
        ruff_ignore = config.get("ruff_ignore") if isinstance(config.get("ruff_ignore"), list) else None
        pylint_disable = config.get("pylint_disable") if isinstance(config.get("pylint_disable"), list) else None
        pylint_enable = config.get("pylint_enable") if isinstance(config.get("pylint_enable"), list) else None
        return StaticAuditOptions(
            enable_ruff=True,
            enable_pylint=True,
            enable_mypy=True,
            ruff_select=ruff_select,
            ruff_ignore=ruff_ignore,
            ruff_line_length=int(config.get("ruff_line_length", 120)),
            pylint_disable=pylint_disable,
            pylint_enable=pylint_enable,
            pylint_max_line_length=int(config.get("pylint_max_line_length", 120)),
            mypy_ignore_missing_imports=bool(config.get("mypy_ignore_missing_imports", True)),
            mypy_strict=bool(config.get("mypy_strict", False)),
        )
    except Exception:
        return StaticAuditOptions()
