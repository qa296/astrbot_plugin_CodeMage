"""
Static code auditor specialized for AstrBot plugins.
Combines generic linters (ruff, pylint, mypy) with AstrBot-specific AST checks.
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
from astrbot.api import AstrBotConfig


@dataclass
class ToolFinding:
    tool: str
    message: str
    severity: str = "info"  # one of: info, warning, error, critical


@dataclass
class StaticAuditReport:
    approved: bool
    score: int
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    tool_findings: List[ToolFinding] = field(default_factory=list)
    tools_missing: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "satisfaction_score": self.score,
            "issues": list(self.issues),
            "suggestions": list(self.suggestions),
            "tools_missing": list(self.tools_missing),
            "tool_findings": [
                {"tool": f.tool, "message": f.message, "severity": f.severity}
                for f in self.tool_findings
            ],
        }


class StaticCodeAuditor:
    """Run static analysis for a given Python code string.

    - Executes ruff, pylint, mypy if available in environment
    - Performs AstrBot-specific semantic checks via AST
    - Produces an aggregate score (0-100) and pass/fail decision
    """

    def __init__(self, config: AstrBotConfig):
        self.config = config
        # Default rule toggles tailored for AstrBot plugin code
        self.ruff_select = (
            config.get("ruff_select")
            or [
                "E",  # pycodestyle errors
                "F",  # pyflakes
                "W",  # warnings
                "I",  # isort
                "PL",  # pylint compatibility
                "UP",  # pyupgrade
                "ASYNC",  # async rules
            ]
        )
        self.ruff_ignore = config.get("ruff_ignore") or [
            # Allow missing module docstring in plugin files
            "D",  # pydocstyle (entire family)
        ]
        # Pylint disables for AstrBot plugin code (imports resolve in runtime env)
        self.pylint_disable = config.get("pylint_disable") or [
            "C0114",  # missing-module-docstring
            "C0115",  # missing-class-docstring
            "C0116",  # missing-function-docstring
            "E0401",  # import-error (astrbot runtime)
        ]
        # mypy flags tuned for plugin style
        self.mypy_flags = config.get("mypy_flags") or [
            "--ignore-missing-imports",
            "--python-version", "3.10",
            "--follow-imports", "silent",
        ]

    def _run_subprocess(self, args: List[str], *, input_text: Optional[str] = None, cwd: Optional[str] = None) -> Tuple[int, str, str]:
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if input_text is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                text=True,
            )
            stdout, stderr = proc.communicate(input=input_text, timeout=60)
            return proc.returncode, stdout or "", stderr or ""
        except FileNotFoundError:
            # Tool missing
            return 127, "", "not found"
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            return 124, "", "timeout"
        except Exception as e:
            return 1, "", str(e)

    def _run_ruff(self, code_path: str, base_dir: str) -> Tuple[List[ToolFinding], List[str]]:
        findings: List[ToolFinding] = []
        missing: List[str] = []
        if shutil.which("ruff") is None:
            # Try python -m ruff
            code, out, err = self._run_subprocess(["python3", "-m", "ruff", "--version"])
            if code != 0:
                missing.append("ruff")
                return findings, missing
        # Use stdin or file path. We'll use file path for better diagnostics
        ruff_args = [
            "ruff", "check", code_path,
            "--format", "text",
            "--quiet",
        ]
        if self.ruff_select:
            ruff_args += ["--select", ",".join(self.ruff_select)]
        if self.ruff_ignore:
            ruff_args += ["--ignore", ",".join(self.ruff_ignore)]

        # Prefer direct ruff binary, fallback to python -m ruff
        if shutil.which("ruff") is None:
            ruff_args = ["python3", "-m", "ruff"] + ruff_args[1:]
        code, out, err = self._run_subprocess(ruff_args, cwd=base_dir)
        text = (out or "") + ("\n" + err if err else "")
        for line in text.splitlines():
            # Format: path:line:col: code message
            m = re.match(r"^.+:\d+:\d+:\s+([A-Z0-9]+)\s+(.*)$", line.strip())
            if not m:
                continue
            rule, msg = m.groups()
            sev = "warning"
            if rule.startswith("E") or rule in {"F401", "F821", "F541", "F632"}:
                sev = "error"
            findings.append(ToolFinding(tool="ruff", message=f"{rule}: {msg}", severity=sev))
        return findings, missing

    def _run_pylint(self, code_path: str, base_dir: str) -> Tuple[List[ToolFinding], List[str]]:
        findings: List[ToolFinding] = []
        missing: List[str] = []
        # Ensure pylint exists
        if shutil.which("pylint") is None:
            code, out, err = self._run_subprocess(["python3", "-m", "pylint", "--version"])
            if code != 0:
                missing.append("pylint")
                return findings, missing
        args = [
            "pylint",
            code_path,
            "--score=n",
            "-j", "0",
            "--output-format=text",
        ]
        if self.pylint_disable:
            args += ["--disable", ",".join(self.pylint_disable)]
        if shutil.which("pylint") is None:
            args = ["python3", "-m", "pylint"] + args[1:]
        code, out, err = self._run_subprocess(args, cwd=base_dir)
        text = (out or "") + ("\n" + err if err else "")
        for line in text.splitlines():
            # Pattern: path:line:col: [C/W/E/F(ref)] message (symbol)
            m = re.match(r"^.+:(\d+):(\d+):\s+\[([CWEFR])[0-9]*[^\]]*\]\s+(.*)$", line.strip())
            if not m:
                continue
            _ln, _col, cat, msg = m.groups()
            sev = {
                "C": "info",
                "W": "warning",
                "R": "warning",
                "E": "error",
                "F": "critical",
            }.get(cat, "info")
            findings.append(ToolFinding(tool="pylint", message=msg, severity=sev))
        return findings, missing

    def _run_mypy(self, code_path: str, base_dir: str) -> Tuple[List[ToolFinding], List[str]]:
        findings: List[ToolFinding] = []
        missing: List[str] = []
        if shutil.which("mypy") is None:
            code, out, err = self._run_subprocess(["python3", "-m", "mypy", "--version"])
            if code != 0:
                missing.append("mypy")
                return findings, missing
        args = [
            "mypy",
            code_path,
        ] + list(self.mypy_flags)
        if shutil.which("mypy") is None:
            args = ["python3", "-m", "mypy"] + args[1:]
        code, out, err = self._run_subprocess(args, cwd=base_dir)
        text = (out or "") + ("\n" + err if err else "")
        for line in text.splitlines():
            # Typical: path:line: col: error: message  [code]
            if ": error:" in line:
                msg = line.split(": error:", 1)[1].strip()
                findings.append(ToolFinding(tool="mypy", message=msg, severity="error"))
        return findings, missing

    def _astrbot_semantic_checks(self, code: str) -> Tuple[List[ToolFinding], List[str]]:
        issues: List[ToolFinding] = []
        suggestions: List[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            issues.append(ToolFinding(tool="ast", message=f"语法错误: {e}", severity="critical"))
            return issues, suggestions

        has_logger_import = False
        imports_logging = False
        has_filter_import = False
        has_star_class = False

        # Helper: get decorator base name string
        def deco_name(d: ast.AST) -> str:
            if isinstance(d, ast.Name):
                return d.id
            if isinstance(d, ast.Attribute):
                return f"{deco_name(d.value)}.{d.attr}" if hasattr(d, "value") else d.attr
            if isinstance(d, ast.Call):
                return deco_name(d.func)
            return ""

        # Scan imports and classes
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "astrbot.api":
                    for n in node.names:
                        if n.name == "logger":
                            has_logger_import = True
                if mod == "astrbot.api.event":
                    for n in node.names:
                        if n.name == "filter":
                            has_filter_import = True
            elif isinstance(node, ast.Import):
                for n in node.names:
                    if n.name == "logging" or n.name.startswith("logging."):
                        imports_logging = True
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Star":
                        has_star_class = True
                    elif isinstance(base, ast.Attribute) and base.attr == "Star":
                        has_star_class = True

        if imports_logging:
            issues.append(ToolFinding(
                tool="astrbot",
                message="禁止使用 logging 模块，请使用 from astrbot.api import logger",
                severity="error",
            ))
            suggestions.append("改为: from astrbot.api import logger，并使用 logger.info()/error() 等")
        if not has_logger_import:
            issues.append(ToolFinding(
                tool="astrbot",
                message="必须使用 astrbot.api.logger 作为日志记录器",
                severity="warning",
            ))
            suggestions.append("添加: from astrbot.api import logger")
        if not has_filter_import:
            issues.append(ToolFinding(
                tool="astrbot",
                message="必须 from astrbot.api.event import filter，否则会与内置 filter 冲突",
                severity="error",
            ))
            suggestions.append("在文件顶部添加: from astrbot.api.event import filter")
        if not has_star_class:
            issues.append(ToolFinding(
                tool="astrbot",
                message="插件中需要存在继承自 Star 的类",
                severity="error",
            ))
            suggestions.append("确保存在: class MyPlugin(Star): ...")

        # Hook signatures and llm_tool/permission_type conflict
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                decos = [deco_name(d) for d in node.decorator_list]
                has_llm_request = any(d.endswith("filter.on_llm_request") for d in decos)
                has_llm_response = any(d.endswith("filter.on_llm_response") for d in decos)
                has_llm_tool = any(d.endswith("filter.llm_tool") for d in decos)
                has_perm_type = any(d.endswith("filter.permission_type") for d in decos)

                if has_llm_request or has_llm_response:
                    # must have 3 parameters
                    if not node.args.args or len(node.args.args) < 3:
                        issues.append(ToolFinding(
                            tool="astrbot",
                            message=f"{node.name} 钩子函数参数数量必须为3: (self, event, req/resp)",
                            severity="error",
                        ))
                        suggestions.append("修正 on_llm_request/on_llm_response 签名为 (self, event, obj)")
                if has_llm_tool and has_perm_type:
                    issues.append(ToolFinding(
                        tool="astrbot",
                        message=f"{node.name} 使用了 @filter.llm_tool 不可与 @filter.permission_type 同时使用",
                        severity="error",
                    ))
                    suggestions.append("移除 llm_tool 上的 permission_type 装饰器")

        # Dangerous API usage simple regex checks
        critical_patterns = [
            r"\beval\s*\(",
            r"\bexec\s*\(",
            r"\bos\.system\s*\(",
            r"\bos\.popen\s*\(",
            r"\bsubprocess\.",
            r"__import__\s*\(",
        ]
        for pat in critical_patterns:
            if re.search(pat, code):
                issues.append(ToolFinding(
                    tool="astrbot",
                    message=f"检测到危险调用: {pat}",
                    severity="critical",
                ))
                suggestions.append("移除危险调用，避免执行任意命令或代码")

        return issues, suggestions

    def audit_code(self, code: str) -> StaticAuditReport:
        # Prepare temp dir and write file
        base_dir = tempfile.mkdtemp(prefix="codemage_audit_")
        code_path = os.path.join(base_dir, "main.py")
        try:
            with open(code_path, "w", encoding="utf-8") as f:
                f.write(code)
            all_findings: List[ToolFinding] = []
            tools_missing: List[str] = []

            # AstrBot semantic checks
            sem_findings, sem_suggestions = self._astrbot_semantic_checks(code)
            all_findings.extend(sem_findings)

            # Run tools when enabled in env
            ruff_findings: List[ToolFinding] = []
            pylint_findings: List[ToolFinding] = []
            mypy_findings: List[ToolFinding] = []

            ruff_findings, missing = self._run_ruff(code_path, base_dir)
            tools_missing.extend(missing)
            all_findings.extend(ruff_findings)

            pylint_findings, missing = self._run_pylint(code_path, base_dir)
            tools_missing.extend(missing)
            all_findings.extend(pylint_findings)

            mypy_findings, missing = self._run_mypy(code_path, base_dir)
            tools_missing.extend(missing)
            all_findings.extend(mypy_findings)

            # Aggregate scoring
            score = 100
            approved = True
            issues: List[str] = []
            suggestions: List[str] = list(dict.fromkeys(sem_suggestions))

            for f in all_findings:
                if f.severity == "critical":
                    score -= 10
                    approved = False
                elif f.severity == "error":
                    score -= 5
                elif f.severity == "warning":
                    score -= 2
                else:
                    score -= 0
                issues.append(f"[{f.tool}] {f.message}")

            score = max(0, min(100, score))
            # Fail if any critical astrbot semantic issue
            if any(f.severity == "critical" for f in all_findings):
                approved = False
            # If too many errors/warnings, reduce approval
            error_count = sum(1 for f in all_findings if f.severity in {"critical", "error"})
            if error_count >= 3:
                approved = False

            return StaticAuditReport(
                approved=approved,
                score=score,
                issues=issues,
                suggestions=suggestions,
                tool_findings=all_findings,
                tools_missing=sorted(set(tools_missing)),
            )
        finally:
            try:
                shutil.rmtree(base_dir)
            except Exception:
                pass
