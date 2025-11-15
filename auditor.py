"""
AstrBot Plugin Static Auditor
Runs ruff + pylint + mypy against a generated AstrBot plugin (main.py) with
AstrBot-specific rules and heuristics.

Only one configuration knob is required from the plugin config:
- lint_profile: one of ["off", "basic", "strict", "astrbot"]
  - off:     skip static analysis
  - basic:   run ruff only with basic style and banned-imports rules
  - strict:  run ruff + pylint + mypy with stricter settings
  - astrbot: tailored defaults for AstrBot plugins (recommended, default)

This module is self-contained and generates temporary config files for tools,
so the host project does not need to ship separate config files.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import ast


@dataclass
class AuditIssue:
    tool: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None

    def to_text(self) -> str:
        loc = f"{self.line}:{self.column}" if self.line is not None else "-"
        return f"[{self.tool}] {loc} {self.message}".strip()


@dataclass
class AuditReport:
    passed: bool
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    raw_reports: Dict[str, Any] = field(default_factory=dict)


class AstrPluginAuditor:
    def __init__(self, lint_profile: str = "astrbot") -> None:
        self.profile = (lint_profile or "astrbot").lower()

    async def audit_code(self, code: str) -> AuditReport:
        if self.profile == "off":
            return AuditReport(passed=True)

        issues: List[AuditIssue] = []
        suggestions: List[str] = []
        raw: Dict[str, Any] = {}

        # Create temp dir and write code to main.py
        with tempfile.TemporaryDirectory(prefix="astr_audit_") as td:
            tmpdir = Path(td)
            main_file = tmpdir / "main.py"
            main_file.write_text(code, encoding="utf-8")

            # Write tool configs depending on profile
            pyproject = self._make_ruff_config()
            (tmpdir / "pyproject.toml").write_text(pyproject, encoding="utf-8")

            pylintrc = self._make_pylint_rc()
            (tmpdir / ".pylintrc").write_text(pylintrc, encoding="utf-8")

            mypyini = self._make_mypy_ini()
            (tmpdir / "mypy.ini").write_text(mypyini, encoding="utf-8")

            # Always run basic AST checks
            ast_issues, ast_suggestions = self._run_ast_checks(code)
            issues.extend(ast_issues)
            suggestions.extend(ast_suggestions)

            # Run ruff for basic/strict/astrbot
            if self.profile in {"basic", "strict", "astrbot"}:
                ruff_issues, ruff_raw = await self._run_ruff(tmpdir, main_file)
                raw["ruff"] = ruff_raw
                issues.extend(ruff_issues)

            # Run pylint & mypy for strict/astrbot
            if self.profile in {"strict", "astrbot"}:
                pylint_issues, pylint_raw = await self._run_pylint(tmpdir, main_file)
                raw["pylint"] = pylint_raw
                issues.extend(pylint_issues)

                mypy_issues, mypy_raw = await self._run_mypy(tmpdir, main_file)
                raw["mypy"] = mypy_raw
                issues.extend(mypy_issues)

        # Make user-facing issues list and final decision
        text_issues = [i.to_text() for i in issues]
        passed = len(text_issues) == 0
        if not passed:
            # Provide generic suggestions tuned for AstrBot plugins
            suggestions.extend(
                [
                    "使用 'from astrbot.api import logger' 替代任何 logging 模块的用法",
                    "避免使用 requests，请改用 aiohttp 或 httpx（异步）",
                    "确保从 'astrbot.api.event' 正确导入 filter 对象",
                    "请确认至少存在一个继承自 Star 的插件主类，并在其中定义事件处理函数",
                ]
            )

        return AuditReport(passed=passed, issues=text_issues, suggestions=list(dict.fromkeys(suggestions)), raw_reports=raw)

    def _make_ruff_config(self) -> str:
        # Ruff 0.6+ configuration style
        # Include tidy-imports to ban logging and requests
        return (
            "[tool.ruff]\n"
            "target-version = \"py310\"\n"
            "line-length = 120\n"
            "[tool.ruff.lint]\n"
            "select = [\"E\", \"F\", \"I\", \"UP\", \"B\", \"SIM\", \"Q\", \"TID\"]\n"
            "ignore = [\"E402\"]\n"
            "[tool.ruff.lint.flake8-tidy-imports]\n"
            "banned-modules = {logging = \"请使用 astrbot.api.logger\", requests = \"请使用 aiohttp 或 httpx（异步）\"}\n"
        )

    def _make_pylint_rc(self) -> str:
        # Pylint tuned for AstrBot plugin code
        return (
            "[MASTER]\n"
            "ignore-patterns=__pycache__\n"
            "load-plugins=\n"
            "[MESSAGES CONTROL]\n"
            # disable some noisy checks; we rely on ruff for styling
            "disable=C0114,C0115,C0116,C0103,R0903,R0801,import-error,unused-argument\n"
            "[FORMAT]\n"
            "max-line-length=120\n"
            "[TYPECHECK]\n"
            "ignored-modules=astrbot,astrbot.api,astrbot.api.event,astrbot.api.star,astrbot.core\n"
            "[IMPORTS]\n"
            "deprecated-modules=logging,requests\n"
            "[BASIC]\n"
            "good-names=_,i,j,k,ex,Run,_,e,self,event,ctx\n"
        )

    def _make_mypy_ini(self) -> str:
        strict = self.profile == "strict"
        return (
            "[mypy]\n"
            "python_version = 3.10\n"
            "ignore_missing_imports = True\n"
            f"check_untyped_defs = {'True' if strict else 'False'}\n"
            "warn_unused_ignores = True\n"
            f"warn_return_any = {'True' if strict else 'False'}\n"
            f"disallow_untyped_defs = {'True' if strict else 'False'}\n"
        )

    async def _run_ruff(self, cwd: Path, main_file: Path) -> Tuple[List[AuditIssue], Any]:
        cmd = [sys.executable, "-m", "ruff", "check", "--no-cache", "--output-format", "json", str(main_file)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        issues: List[AuditIssue] = []
        raw: Any = None
        try:
            raw = json.loads(stdout.decode() or "[]")
            for item in raw:
                issues.append(
                    AuditIssue(
                        tool=f"ruff/{item.get('code','')}",
                        message=item.get("message", ""),
                        line=item.get("location", {}).get("row"),
                        column=item.get("location", {}).get("column"),
                    )
                )
        except Exception:
            # If ruff not available or output malformed, degrade gracefully
            err = stderr.decode().strip()
            lowered = err.lower()
            if "no module named ruff" in lowered or "ruff: not found" in lowered:
                # Tool not installed: skip reporting as failure
                return [], None
            if err:
                issues.append(AuditIssue(tool="ruff", message=err))
        return issues, raw

    async def _run_pylint(self, cwd: Path, main_file: Path) -> Tuple[List[AuditIssue], Any]:
        cmd = [
            sys.executable,
            "-m",
            "pylint",
            "--rcfile",
            str(cwd / ".pylintrc"),
            "--output-format=json",
            str(main_file),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        issues: List[AuditIssue] = []
        raw: Any = None
        try:
            data = stdout.decode() or "[]"
            raw = json.loads(data)
            for item in raw:
                issues.append(
                    AuditIssue(
                        tool=f"pylint/{item.get('symbol','')}",
                        message=item.get("message", ""),
                        line=item.get("line"),
                        column=item.get("column"),
                    )
                )
        except Exception:
            err = stderr.decode().strip()
            lowered = err.lower()
            if "no module named pylint" in lowered or "pylint: not found" in lowered:
                return [], None
            if err:
                issues.append(AuditIssue(tool="pylint", message=err))
        return issues, raw

    async def _run_mypy(self, cwd: Path, main_file: Path) -> Tuple[List[AuditIssue], Any]:
        cmd = [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(cwd / "mypy.ini"),
            "--hide-error-codes",
            "--no-color-output",
            "--error-format=json",
            str(main_file),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        issues: List[AuditIssue] = []
        raw: Any = None
        try:
            data = stdout.decode() or "[]"
            raw = json.loads(data)
            for item in raw:
                if item.get("severity") == "error":
                    issues.append(
                        AuditIssue(
                            tool="mypy",
                            message=item.get("message", ""),
                            line=item.get("line"),
                            column=item.get("column"),
                        )
                    )
        except Exception:
            err = stderr.decode().strip()
            lowered = err.lower()
            if "no module named mypy" in lowered or "mypy: not found" in lowered:
                return [], None
            if err:
                issues.append(AuditIssue(tool="mypy", message=err))
        return issues, raw

    def _run_ast_checks(self, code: str) -> Tuple[List[AuditIssue], List[str]]:
        issues: List[AuditIssue] = []
        suggestions: List[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            issues.append(AuditIssue(tool="ast", message=f"语法错误: {e}", line=e.lineno, column=e.offset))
            return issues, suggestions

        # Track imports
        imported_logging = False
        imported_requests = False
        imported_filter = False
        imported_logger = False
        has_star_subclass = False

        class_name_stars: List[str] = []

        class ImportVisitor(ast.NodeVisitor):
            def visit_Import(self, node: ast.Import) -> None:  # type: ignore[override]
                nonlocal imported_logging, imported_requests
                for n in node.names:
                    if n.name == "logging":
                        imported_logging = True
                    if n.name == "requests":
                        imported_requests = True
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # type: ignore[override]
                nonlocal imported_filter, imported_logger, imported_requests
                mod = node.module or ""
                if mod == "astrbot.api.event":
                    if any(n.name == "filter" for n in node.names):
                        imported_filter = True
                if mod == "astrbot.api":
                    if any(n.name == "logger" for n in node.names):
                        imported_logger = True
                if mod.startswith("requests"):
                    imported_requests = True
                self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef) -> None:  # type: ignore[override]
                nonlocal has_star_subclass
                for base in node.bases:
                    # best-effort: match base id/name endswith Star
                    name = None
                    if isinstance(base, ast.Name):
                        name = base.id
                    elif isinstance(base, ast.Attribute):
                        name = base.attr
                    if name == "Star":
                        has_star_subclass = True
                        class_name_stars.append(node.name)
                self.generic_visit(node)

        ImportVisitor().visit(tree)

        if imported_logging:
            issues.append(
                AuditIssue(tool="astr", message="禁止使用 logging，请改用 'from astrbot.api import logger'")
            )
            suggestions.append("替换 logging 为 astrbot.api.logger")
        if imported_requests:
            issues.append(AuditIssue(tool="astr", message="禁止使用 requests，请改用 aiohttp 或 httpx（异步）"))
            suggestions.append("替换 requests 为 aiohttp/httpx（异步）")
        if not imported_filter:
            # Not strictly mandatory for every plugin, but highly recommended
            issues.append(AuditIssue(tool="astr", message="未检测到 'from astrbot.api.event import filter' 导入，可能导致装饰器冲突"))
            suggestions.append("确保从 astrbot.api.event 正确导入 filter 对象")
        if not imported_logger:
            issues.append(AuditIssue(tool="astr", message="未检测到 'from astrbot.api import logger' 导入，建议统一日志接口"))
            suggestions.append("使用 astrbot.api.logger 进行日志记录")
        if not has_star_subclass:
            issues.append(AuditIssue(tool="astr", message="未检测到继承自 Star 的插件主类"))
            suggestions.append("创建一个继承自 Star 的主类")

        # Validate special hook functions not yielding
        def _has_forbidden_yield_in_hooks(fn: ast.AsyncFunctionDef) -> bool:
            # Detect if fn has forbidden yield statements
            class YieldVisitor(ast.NodeVisitor):
                found = False

                def visit_Yield(self, node: ast.Yield) -> None:  # type: ignore[override]
                    self.found = True

                def visit_YieldFrom(self, node: ast.YieldFrom) -> None:  # type: ignore[override]
                    self.found = True

            yv = YieldVisitor()
            yv.visit(fn)
            return yv.found

        def _decorator_matches(d: ast.expr, target: str) -> bool:
            # Match @filter.on_xxx(...)
            if isinstance(d, ast.Call):
                func = d.func
            else:
                func = d
            if isinstance(func, ast.Attribute):
                # filter.on_llm_request / filter.on_llm_response / filter.on_decorating_result / filter.after_message_sent
                if isinstance(func.value, ast.Name) and func.value.id == "filter":
                    return func.attr == target
            return False

        class HookVisitor(ast.NodeVisitor):
            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # type: ignore[override]
                decorators = node.decorator_list
                for target in (
                    "on_llm_request",
                    "on_llm_response",
                    "on_decorating_result",
                    "after_message_sent",
                ):
                    if any(_decorator_matches(d, target) for d in decorators):
                        # signature must have at least (self, event, third?) for llm hooks
                        if target in {"on_llm_request", "on_llm_response"}:
                            if not (len(node.args.args) >= 3):
                                issues.append(
                                    AuditIssue(
                                        tool="astr",
                                        message=f"{target} 钩子函数签名必须包含 self, event 以及第三个参数",
                                        line=node.lineno,
                                        column=node.col_offset,
                                    )
                                )
                        else:
                            if not (len(node.args.args) >= 2):
                                issues.append(
                                    AuditIssue(
                                        tool="astr",
                                        message=f"{target} 钩子函数签名必须至少包含 self, event",
                                        line=node.lineno,
                                        column=node.col_offset,
                                    )
                                )
                        if _has_forbidden_yield_in_hooks(node):
                            issues.append(
                                AuditIssue(
                                    tool="astr",
                                    message=f"{target} 钩子中禁止使用 yield 发送消息，请改用 event.send()",
                                    line=node.lineno,
                                    column=node.col_offset,
                                )
                            )
                self.generic_visit(node)

        HookVisitor().visit(tree)

        return issues, suggestions
