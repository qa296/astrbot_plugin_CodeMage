"""
AstrBot 插件静态审查工具
针对 LLM 生成的插件代码进行本地静态规则检查，不依赖网络与外部 LLM。

目标：
- 不新增生成流程步骤，作为现有“代码审查与修复”步骤中的子检查使用
- 专门适配 AstrBot 插件规范与本项目约束
- 支持通过 _conf_schema.json 的配置开关与规则项进行定制
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from astrbot.api import logger

try:
    # AstrBotConfig 在运行时由 AstrBot 注入，此处仅作类型标注
    from astrbot.api import AstrBotConfig  # type: ignore
except Exception:  # pragma: no cover - 仅为类型兼容
    AstrBotConfig = dict  # type: ignore


@dataclass
class StaticAuditResult:
    approved: bool
    satisfaction_score: int
    reason: str
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


class AstrBotStaticAuditor:
    """AstrBot 插件静态审查器。

    规则总述：
    - 安全与危险 API：禁止 eval/exec/subprocess/os.system/os.popen/os.spawn/os.exec
    - 网络库：禁止 requests，建议使用 httpx/aiohttp
    - 日志：必须使用 from astrbot.api import logger，禁止 import logging / loguru
    - 结构：必须存在继承自 Star 的类
    - 事件/命令：@filter.command 必须 async def；出现 @filter.* 时需正确导入 filter
    - LLM 钩子：on_llm_request / on_llm_response 必须为 async，并且参数为 (self, event, req/resp)，且内部禁止 yield
    - 依赖：requirements/metadata 中的依赖不得包含黑名单包
    """

    def __init__(self, config: AstrBotConfig):
        self.config = config or {}
        rules = self.config.get("static_audit_rules", {}) or {}

        # 允许通过配置对规则进行细粒度调整
        self.rule_require_logger_import: bool = rules.get("require_logger_from_astrbot", True)
        self.rule_disallow_logging_module: bool = rules.get("disallow_logging_module", True)
        self.rule_disallow_requests: bool = rules.get("disallow_requests", True)
        self.rule_banned_dependencies: List[str] = list(rules.get("banned_dependencies", ["requests", "loguru"]))

        # 评分基准
        self.max_score = 100

    def audit(self, code: str, metadata: Dict[str, Any], requirements: Optional[List[str]] = None) -> StaticAuditResult:
        issues: List[str] = []
        suggestions: List[str] = []
        score = self.max_score
        critical = False

        # 解析 AST
        try:
            tree = ast.parse(code)
        except Exception as e:
            # 无法解析代码，直接判定为不通过
            reason = f"无法解析生成的 Python 代码: {e}"
            return StaticAuditResult(
                approved=False,
                satisfaction_score=0,
                reason=reason,
                issues=[reason],
                suggestions=["请重新生成代码，或修复语法错误后再试"],
            )

        # 规则：必须存在 Star 子类
        if not self._has_star_subclass(tree):
            critical = True
            issues.append("未发现继承自 Star 的插件类")
            suggestions.append("确保存在 class MyPlugin(Star): 并在 __init__ 中调用 super().__init__(context)")
            score -= 40

        # 规则：禁止危险 API
        dangerous_patterns = [
            r"eval\s*\(",
            r"exec\s*\(",
            r"subprocess\.",
            r"os\.system\s*\(",
            r"os\.popen\s*\(",
            r"os\.spawn",
            r"os\.exec",
            r"__import__\s*\(",
        ]
        for pat in dangerous_patterns:
            if re.search(pat, code):
                critical = True
                issues.append(f"检测到危险 API 使用：{pat}")
                suggestions.append("移除危险 API。若需执行外部请求或命令，请采用受控的异步调用方式并加入严格校验")
                score -= 50

        # 规则：日志导入与 logging 使用
        if self.rule_require_logger_import:
            if "from astrbot.api import logger" not in code:
                issues.append("未从 astrbot.api 导入 logger")
                suggestions.append("添加 'from astrbot.api import logger' 并使用 logger 进行日志记录")
                score -= 10
        if self.rule_disallow_logging_module:
            if re.search(r"\bimport\s+logging\b|\blogging\.", code):
                issues.append("检测到对 logging 模块的使用，AstrBot 插件应使用 astrbot.api.logger")
                suggestions.append("移除 logging 相关代码，使用 astrbot.api.logger 代替")
                score -= 20

        # 规则：禁止 requests
        if self.rule_disallow_requests and re.search(r"\bimport\s+requests\b|\bfrom\s+requests\s+import\b|\brequests\.", code):
            critical = True
            issues.append("检测到 requests 库的使用，AstrBot 插件请使用 aiohttp/httpx 等异步库")
            suggestions.append("替换为 aiohttp 或 httpx，并以异步方式进行网络 I/O")
            score -= 30

        # 规则：依赖黑名单
        reqs = set((requirements or []) + list(self._extract_dependencies_from_metadata(metadata)))
        banned_hit = [pkg for pkg in self.rule_banned_dependencies if pkg in reqs]
        if banned_hit:
            issues.append(f"requirements 存在不被允许的依赖: {', '.join(banned_hit)}")
            suggestions.append("移除不被允许的依赖，或改用受支持的异步/安全替代库")
            score -= 20

        # 规则：filter 正确导入
        if "@filter." in code and "from astrbot.api.event import filter" not in code:
            issues.append("检测到 @filter 装饰器，但未正确导入 filter：from astrbot.api.event import filter")
            suggestions.append("添加 'from astrbot.api.event import filter, AstrMessageEvent'")
            score -= 15

        # 规则：@filter.command 必须 async def；并且签名包含 event 参数
        for fn, dec_name in self._iter_decorated_functions(tree):
            if dec_name == "filter.command":
                if not isinstance(fn, ast.AsyncFunctionDef):
                    issues.append(f"命令处理函数 {fn.name} 必须使用 async def 定义")
                    suggestions.append("将 @filter.command 标注的方法改为 async def")
                    score -= 15
                if not self._has_param(fn, "event"):
                    issues.append(f"命令处理函数 {fn.name} 缺少 event 参数")
                    suggestions.append("为命令处理函数添加 event: AstrMessageEvent 参数")
                    score -= 10

        # 规则：LLM 钩子签名与内部 yield 禁止
        for fn, dec_name in self._iter_decorated_functions(tree):
            if dec_name in ("filter.on_llm_request", "filter.on_llm_response"):
                if not isinstance(fn, ast.AsyncFunctionDef):
                    issues.append(f"{dec_name} 修饰的函数 {fn.name} 必须为 async def")
                    suggestions.append("将 LLM 钩子函数改为 async def")
                    score -= 20
                # 需 3 个参数: self, event, req/resp
                if not self._has_min_args(fn, 3):
                    issues.append(f"{dec_name} 修饰的函数 {fn.name} 形参必须包含 (self, event, req/resp) 共 3 个")
                    suggestions.append("按规范将 LLM 钩子签名设为 (self, event: AstrMessageEvent, obj)")
                    score -= 15
                # 禁止 yield
                if self._contains_yield(fn):
                    issues.append(f"{dec_name} 修饰的函数 {fn.name} 内部禁止使用 yield 发送消息，请改用 event.send()")
                    suggestions.append("在 LLM 钩子中使用 await event.send(...) 发送消息")
                    score -= 20

        # 收敛评分区间 [0,100]
        score = max(0, min(100, score))
        approved = (not critical) and (score >= 60)  # 静态审查通过的最低线：无致命且分数>=60
        reason = "静态审查通过" if approved else "静态审查未通过，存在需修复的问题"

        return StaticAuditResult(
            approved=approved,
            satisfaction_score=score,
            reason=reason,
            issues=issues,
            suggestions=suggestions,
        )

    # ---- 内部工具函数 ----

    def _has_star_subclass(self, tree: ast.AST) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    # 允许多种写法：Star / api.star.Star 等
                    if isinstance(base, ast.Name) and base.id == "Star":
                        return True
                    if isinstance(base, ast.Attribute) and base.attr == "Star":
                        return True
        return False

    def _iter_decorated_functions(self, tree: ast.AST):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list:
                for dec in node.decorator_list:
                    name = None
                    if isinstance(dec, ast.Attribute):
                        # 形如 @filter.command
                        if isinstance(dec.value, ast.Name):
                            name = f"{dec.value.id}.{dec.attr}"
                    elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        # 形如 @filter.command("xxx")
                        if isinstance(dec.func.value, ast.Name):
                            name = f"{dec.func.value.id}.{dec.func.attr}"
                    if name:
                        yield node, name

    def _has_param(self, fn: ast.FunctionDef | ast.AsyncFunctionDef, param_name: str) -> bool:
        return any(arg.arg == param_name for arg in getattr(fn.args, "args", []))

    def _has_min_args(self, fn: ast.FunctionDef | ast.AsyncFunctionDef, n: int) -> bool:
        return len(getattr(fn.args, "args", [])) >= n

    def _contains_yield(self, fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for node in ast.walk(fn):
            if isinstance(node, (ast.Yield, ast.YieldFrom)):
                return True
        return False

    def _extract_dependencies_from_metadata(self, metadata: Dict[str, Any]) -> List[str]:
        try:
            md = metadata.get("metadata", {}) if isinstance(metadata, dict) else {}
            deps = md.get("dependencies", [])
            if isinstance(deps, list):
                return [str(d).strip() for d in deps if str(d).strip()]
        except Exception as e:
            logger.debug(f"提取依赖失败: {e}")
        return []
