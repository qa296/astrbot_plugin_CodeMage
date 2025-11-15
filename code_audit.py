"""
AstrBot 插件代码审查工具

- 结合 ruff / pylint / mypy 的本地静态检查（若环境缺失对应可执行文件，则自动降级跳过）
- 内置 AstrBot 专项规则检查（无需外部依赖）
- 输出统一的审查结果结构，便于在生成流程中集成
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ToolReport:
    name: str
    available: bool
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    raw_output: Optional[str] = None


@dataclass
class AuditResult:
    approved: bool
    satisfaction_score: int
    reason: str
    issues: List[str]
    suggestions: List[str]
    details: Dict[str, ToolReport]


class AstrbotPluginAuditor:
    """AstrBot 插件专用静态审查器

    说明：
    - 优先尝试在系统中调用 ruff / pylint / mypy 可执行文件
    - 若找不到则仅进行内置的 AstrBot 规则检查，不抛异常
    - 以 0-100 的分数衡量，存在严重问题或分数低于阈值时 approved=False
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.static_threshold = int(self.config.get("static_satisfaction_threshold", 85))
        self.enable_astr_checks = bool(self.config.get("enable_astrbot_checks", True))
        # 超时时间，避免外部工具卡住
        self._timeout_sec = float(self.config.get("static_tool_timeout", 20.0))

    async def analyze_code(self, code: str) -> AuditResult:
        """分析单文件插件代码（main.py 形式）"""
        temp_dir = tempfile.mkdtemp(prefix="astrbot_audit_")
        try:
            main_path = os.path.join(temp_dir, "main.py")
            with open(main_path, "w", encoding="utf-8") as f:
                f.write(code)

            # 写入最小化配置，尽量减少误报
            await self._write_configs(temp_dir)

            # 并行运行外部工具（若存在）
            ruff_task = asyncio.create_task(self._run_ruff(main_path, cwd=temp_dir))
            pylint_task = asyncio.create_task(self._run_pylint(main_path, cwd=temp_dir))
            mypy_task = asyncio.create_task(self._run_mypy(main_path, cwd=temp_dir))

            # AstrBot 专项检查
            astr_task = asyncio.create_task(self._run_astrbot_checks(code))

            ruff_report, pylint_report, mypy_report, astr_report = await asyncio.gather(
                ruff_task, pylint_task, mypy_task, astr_task
            )

            # 汇总评分
            score = 100
            issues: List[str] = []
            suggestions: List[str] = []
            details = {
                "ruff": ruff_report,
                "pylint": pylint_report,
                "mypy": mypy_report,
                "astrbot_checks": astr_report,
            }

            # 计分规则：
            # - ruff/pylint/mypy 发现的每个问题扣 1 分
            # - AstrBot 专项检查每个问题扣 5 分
            for rep in (ruff_report, pylint_report, mypy_report):
                issues.extend([f"[{rep.name}] {m}" for m in rep.issues])
                suggestions.extend(rep.suggestions)
                score -= min(len(rep.issues), 100)  # 单项最多扣 100 分以避免负数

            issues.extend([f"[astrbot] {m}" for m in astr_report.issues])
            suggestions.extend(astr_report.suggestions)
            score -= 5 * len(astr_report.issues)

            # 规范分数范围
            score = max(0, min(100, score))

            # 审批逻辑：
            # - AstrBot 专项出现关键问题直接不通过
            # - 否则以得分与阈值比较
            critical = any("[CRITICAL]" in m for m in astr_report.issues)
            approved = (not critical) and (score >= self.static_threshold)

            # 生成说明
            if critical:
                reason = "AstrBot 专项校验存在关键问题"
            elif score < self.static_threshold:
                reason = f"静态检查得分过低：{score} < {self.static_threshold}"
            else:
                reason = "通过"

            # 去重、裁剪
            issues = self._dedup_list(issues)
            suggestions = self._dedup_list(suggestions)

            return AuditResult(
                approved=approved,
                satisfaction_score=score,
                reason=reason,
                issues=issues,
                suggestions=suggestions,
                details=details,
            )
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    @staticmethod
    def _dedup_list(items: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for it in items:
            key = it.strip()
            if key and key not in seen:
                out.append(key)
                seen.add(key)
        return out

    async def _write_configs(self, temp_dir: str) -> None:
        """为外部工具写入最小化配置，避免误报"""
        # ruff
        pyproject = os.path.join(temp_dir, "pyproject.toml")
        if not os.path.exists(pyproject):
            with open(pyproject, "w", encoding="utf-8") as f:
                f.write(
                    """
[tool.ruff]
line-length = 120
select = ["E", "F", "W", "I", "UP", "N", "ANN"]
ignore = []

[tool.ruff.lint.isort]
combine-as-imports = true
force-sort-within-sections = true
                    """.strip()
                )

        # pylint
        pylintrc = os.path.join(temp_dir, ".pylintrc")
        if not os.path.exists(pylintrc):
            with open(pylintrc, "w", encoding="utf-8") as f:
                f.write(
                    """
[MASTER]
ignore-patterns=test_.*\.py

[MESSAGES CONTROL]
disable=import-error,missing-module-docstring,missing-class-docstring,missing-function-docstring

[FORMAT]
max-line-length=120
                    """.strip()
                )

        # mypy
        mypyini = os.path.join(temp_dir, "mypy.ini")
        if not os.path.exists(mypyini):
            with open(mypyini, "w", encoding="utf-8") as f:
                f.write(
                    """
[mypy]
python_version = 3.10
ignore_missing_imports = True
strict_optional = False
warn_unused_ignores = False
warn_return_any = False
no_site_packages = True
follow_imports = skip
show_error_codes = False
                    """.strip()
                )

    async def _run_ruff(self, main_path: str, cwd: Optional[str]) -> ToolReport:
        exe = shutil.which("ruff")
        if not exe:
            return ToolReport(name="ruff", available=False)
        try:
            proc = await asyncio.create_subprocess_exec(
                exe, "check", "--format", "json", os.path.basename(main_path),
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_sec)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolReport(name="ruff", available=True, issues=["执行超时"], suggestions=["检查是否存在死循环或超大文件"])

            raw = stdout.decode("utf-8", errors="ignore")
            issues: List[str] = []
            suggestions: List[str] = []
            try:
                data = json.loads(raw) if raw.strip() else []
                for item in data:
                    code = item.get("code", "")
                    msg = item.get("message", "")
                    line = item.get("location", {}).get("row")
                    col = item.get("location", {}).get("column")
                    issues.append(f"{code} L{line}:{col} {msg}")
                    sug = self._suggest_from_ruff(code, msg)
                    if sug:
                        suggestions.append(sug)
            except Exception:
                # 回退到文本
                for line in raw.splitlines():
                    line = line.strip()
                    if line:
                        issues.append(line)

            return ToolReport(name="ruff", available=True, issues=issues, suggestions=self._dedup_list(suggestions), raw_output=raw)
        except FileNotFoundError:
            return ToolReport(name="ruff", available=False)

    async def _run_pylint(self, main_path: str, cwd: Optional[str]) -> ToolReport:
        exe = shutil.which("pylint")
        if not exe:
            return ToolReport(name="pylint", available=False)
        try:
            proc = await asyncio.create_subprocess_exec(
                exe,
                "--output-format=json",
                "-sn",  # 不显示分数摘要
                "-rn",  # 不显示消息分类摘要
                os.path.basename(main_path),
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_sec)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolReport(name="pylint", available=True, issues=["执行超时"], suggestions=["检查复杂度或减少分析范围"])

            raw = stdout.decode("utf-8", errors="ignore")
            issues: List[str] = []
            suggestions: List[str] = []
            try:
                data = json.loads(raw) if raw.strip() else []
                for item in data:
                    msg = item.get("message", "")
                    sym = item.get("symbol", "")
                    line = item.get("line")
                    col = item.get("column")
                    issues.append(f"{sym} L{line}:{col} {msg}")
                    sug = self._suggest_from_pylint(sym, msg)
                    if sug:
                        suggestions.append(sug)
            except Exception:
                for line in raw.splitlines():
                    line = line.strip()
                    if line:
                        issues.append(line)

            return ToolReport(name="pylint", available=True, issues=issues, suggestions=self._dedup_list(suggestions), raw_output=raw)
        except FileNotFoundError:
            return ToolReport(name="pylint", available=False)

    async def _run_mypy(self, main_path: str, cwd: Optional[str]) -> ToolReport:
        exe = shutil.which("mypy")
        if not exe:
            return ToolReport(name="mypy", available=False)
        try:
            proc = await asyncio.create_subprocess_exec(
                exe,
                os.path.basename(main_path),
                "--python-version", "3.10",
                "--no-error-summary",
                "--hide-error-codes",
                "--ignore-missing-imports",
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_sec)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolReport(name="mypy", available=True, issues=["执行超时"], suggestions=["补全类型或简化泛型推断"]) 

            raw_out = stdout.decode("utf-8", errors="ignore")
            issues: List[str] = []
            suggestions: List[str] = []
            for line in raw_out.splitlines():
                txt = line.strip()
                if not txt:
                    continue
                # 典型格式：main.py:10:5: error: ...
                if ": error:" in txt:
                    issues.append(txt)
                    sug = self._suggest_from_mypy(txt)
                    if sug:
                        suggestions.append(sug)
            return ToolReport(name="mypy", available=True, issues=issues, suggestions=self._dedup_list(suggestions), raw_output=raw_out)
        except FileNotFoundError:
            return ToolReport(name="mypy", available=False)

    async def _run_astrbot_checks(self, code: str) -> ToolReport:
        if not self.enable_astr_checks:
            return ToolReport(name="astrbot_checks", available=True)

        issues: List[str] = []
        suggestions: List[str] = []

        # 1. 必须从 astrbot.api 导入 logger，且禁止使用 logging
        uses_logging = bool(re.search(r"\bimport\s+logging\b|\blogging\.getLogger\(", code))
        has_logger_import = bool(re.search(r"from\s+astrbot\.api\s+import\s+logger", code))
        if uses_logging:
            issues.append("[CRITICAL] 使用了 logging 模块。AstrBot 插件必须使用 from astrbot.api import logger")
            suggestions.append("移除 logging 相关代码，改为 from astrbot.api import logger")
        if not has_logger_import:
            issues.append("未发现 'from astrbot.api import logger' 导入")
            suggestions.append("添加: from astrbot.api import logger")

        # 2. 必须存在继承自 Star 的类
        star_class = bool(re.search(r"class\s+\w+\(\s*Star\s*\)\s*:", code))
        if not star_class:
            issues.append("[CRITICAL] 未找到继承自 Star 的插件类")
            suggestions.append("定义插件主类，例如: class MyPlugin(Star): ...")

        # 3. 事件装饰器必须从 astrbot.api.event 导入 filter
        has_filter_import = bool(re.search(r"from\s+astrbot\.api\.event\s+import\s+filter", code))
        if not has_filter_import and re.search(r"@\s*filter\.", code):
            issues.append("[CRITICAL] 使用了 @filter 装饰器但未从 astrbot.api.event 导入 filter")
            suggestions.append("添加: from astrbot.api.event import filter")

        # 4. 钩子函数签名检查与 yield 限制
        issues_sig, sug_sig = self._check_hooks_and_yield(code)
        issues.extend(issues_sig)
        suggestions.extend(sug_sig)

        return ToolReport(name="astrbot_checks", available=True, issues=issues, suggestions=self._dedup_list(suggestions))

    def _check_hooks_and_yield(self, code: str) -> Tuple[List[str], List[str]]:
        issues: List[str] = []
        suggestions: List[str] = []

        # 简单的基于正则/语法标记的检查，避免依赖 ast 复杂遍历导致版本差异
        def find_functions(pattern: str) -> List[Tuple[str, str]]:
            # 返回 (函数名, 函数体文本)
            out: List[Tuple[str, str]] = []
            # 近似匹配 async def ...() 定义（多行参数支持有限，但足够覆盖大多数生成代码）
            func_re = re.compile(rf"@\s*filter\.{pattern}.*\n\s*async\s+def\s+(\w+)\s*\(([^)]*)\)\s*:\n((?:\s+.*\n)*)", re.MULTILINE)
            for m in func_re.finditer(code):
                name = m.group(1)
                # 参数串与主体
                # 注意: group(2) 可能跨多行，这里仅用于参数计数
                params = m.group(2)
                body = m.group(3) or ""
                out.append((params, body))
            return out

        # 需要 3 个参数的钩子
        for dec in ("on_llm_request", "on_llm_response"):
            for params, body in find_functions(dec):
                # 统计逗号分隔的参数个数，排除 *args/**kwargs 的影响
                param_names = [p.strip() for p in params.split(',') if p.strip()]
                if len(param_names) < 3:
                    issues.append(f"[CRITICAL] {dec} 钩子函数参数必须包含 self, event, 第三个特定对象")
                    suggestions.append(f"修改 {dec} 钩子函数签名为包含三个参数")
                # 禁止 yield 发送
                if re.search(r"\byield\s+event\.", body):
                    issues.append(f"[CRITICAL] {dec} 钩子中禁止使用 yield 发送消息，请使用 event.send()")
                    suggestions.append("在这些钩子中改用 await event.send(...)")

        # 其他两个禁止 yield 的钩子
        for dec in ("on_decorating_result", "after_message_sent"):
            for params, body in find_functions(dec):
                if re.search(r"\byield\s+event\.", body):
                    issues.append(f"[CRITICAL] {dec} 钩子中禁止使用 yield 发送消息，请使用 event.send()")
                    suggestions.append("在这些钩子中改用 await event.send(...)")

        # 使用 @filter 装饰的监听器必须是 async def（on_astrbot_loaded 可无 event 参数，但仍建议 async）
        # 这里做一个粗略校验：如匹配到 @filter.command(...)[\n]def 则认为问题
        sync_listener = re.search(r"@\s*filter\.[a-zA-Z_]+\(.*\)\s*\n\s*def\s+\w+\s*\(", code)
        if sync_listener:
            issues.append("检测到同步的事件监听器，建议全部使用 async def")
            suggestions.append("将监听器改为 async def，并在内部使用 await 发送消息")

        # 除 on_astrbot_loaded 外，监听器应包含 event 参数
        # 粗略检测：command/on_* 监听器参数中无 event 关键词
        for dec in ("command", "event_message_type", "platform_adapter_type", "permission_type"):
            func_re = re.compile(rf"@\s*filter\.{dec}.*\n\s*async\s+def\s+\w+\s*\(([^)]*)\)")
            for m in func_re.finditer(code):
                params = (m.group(1) or "").replace(" ", "")
                if "event:" not in params and ",event," not in f",{params},":
                    issues.append(f"{dec} 监听器缺少 event 参数")
                    suggestions.append("在监听器签名中添加 event: AstrMessageEvent 参数")

        return issues, suggestions

    # 建议生成器
    def _suggest_from_ruff(self, code: str, msg: str) -> Optional[str]:
        mapping = {
            "E501": "将单行长度控制在 120 字以内，合理换行",
            "F401": "移除未使用的导入以减少冗余",
            "F841": "移除未使用的变量或以下划线前缀标记",
            "ANN": "为函数和变量添加必要的类型注解",
            "UP": "使用更现代/兼容的 Python 语法（升级语法）",
        }
        for k, v in mapping.items():
            if code.startswith(k) or code == k:
                return v
        if "imported but unused" in msg:
            return "移除未使用的导入"
        return None

    def _suggest_from_pylint(self, sym: str, msg: str) -> Optional[str]:
        mapping = {
            "unused-import": "移除未使用的导入",
            "unused-variable": "移除未使用的变量或改为下划线占位",
            "redefined-outer-name": "避免覆盖外部名称，重命名局部变量",
            "broad-except": "避免使用过宽的异常捕获，指定异常类型",
            "consider-using-with": "对于文件/资源操作使用 contextmanager (with)",
        }
        if sym in mapping:
            return mapping[sym]
        if "line too long" in msg:
            return "拆分超长行，控制在 120 列以内"
        return None

    def _suggest_from_mypy(self, line: str) -> Optional[str]:
        if "Incompatible types" in line:
            return "修正不兼容的类型，或为变量/参数添加显式类型注解"
        if "Missing return statement" in line:
            return "确保函数所有分支均有返回值，或标注返回类型 Optional"
        if "Name not defined" in line:
            return "检查变量/函数的作用域与导入是否正确"
        return None
