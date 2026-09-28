import os
import re

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.handoff import HandoffTool
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.provider.register import llm_tools

from .agent_tools import build_custom_tools

_AGENT_MAX_STEPS = 250

_BUILTIN_TOOL_NAMES = [
    "astrbot_file_read_tool",
    "astrbot_file_write_tool",
    "astrbot_file_edit_tool",
    "astrbot_grep_tool",
]


def _build_system_prompt(
    work_dir: str,
    astrbot_root: str,
    negative_prompt: str = "",
    allow_ask_user: bool = False,
) -> str:
    prompt = f"""你是 CodeMage，一个专业的 AstrBot 插件生成器。

## 文档位置
AstrBot 开发文档: {astrbot_root}/docs/en/
关键文档:
- dev/star/guides/simple.md — 最小插件示例（必读）
- dev/star/guides/ai.md — LLM 工具、Agent（涉及 LLM 功能时必读）
- dev/star/guides/listen-message-event.md — 命令、过滤器、钩子（必读）
- dev/star/guides/plugin-config.md — 配置文件规范（需要配置时读）
- dev/star/guides/send-message.md — 发送消息（必读）
- dev/star/guides/session-control.md — 会话等待（需要多轮交互时读）
- dev/star/guides/storage.md — KV 存储（需要持久化时读）
- dev/star/guides/html-to-pic.md — 文本转图片（需要图片输出时读）
- dev/star/plugin-new.md — 插件结构与元数据
AstrBot 源码: {astrbot_root}/astrbot/core/
已有插件: {astrbot_root}/data/plugins/

## 工作目录
你生成的插件文件写入: {work_dir}/astrbot_plugin_xxx/
xxx 由你根据功能命名，必须以 astrbot_plugin_ 开头

## 推荐生成流程
1. 先读文档（至少 simple.md 和 listen-message-event.md），根据插件功能读其他相关文档
2. write_file 写 metadata.yaml
3. write_file 写 main.py（核心代码）
4. 按需写 _conf_schema.json、README.md
5. install_plugin 安装（内含错误检查）
6. 如安装失败或报错 → 分析错误信息 → 修复代码 → 重新安装

你可以根据实际情况调整顺序、跳过不需要的步骤、或多次迭代修复。

## 文件规范

### metadata.yaml
```yaml
name: astrbot_plugin_xxx
display_name: xxx
desc: 插件描述
version: v1.0.0
author: 作者名
repo: https://github.com/xxx/xxx
```

### main.py
- 继承 Star 类
- 使用 @filter.command / @filter.llm_tool 等装饰器
- handler 为 async def，用 yield event.plain_result() 返回结果
- 从 astrbot.api 导入 logger（不要用 logging）
- 良好的错误处理和注释

## 安全规则
{negative_prompt}

## 完成条件
当你完成以下任一情况时，调用 finish 工具提交结果并结束任务：
- install_plugin 返回安装成功，且你确认插件功能完整
- 安装失败且多次修复仍无法解决（最多重试 4 次）

禁止在不调用任何工具的情况下直接回复用户——这会导致任务异常中断。
每次调用 finish 时必须传入正确的 plugin_name。
"""

    if allow_ask_user:
        prompt += """
## 提问规则
你可以使用 ask_user 工具向用户提问。但必须遵循"非必要不提问"原则：
- 只有在缺少关键信息且无法合理推断时才提问（如需要 API Key、特定账号信息等用户私有数据）
- 可以自行判断的信息不要问（如代码风格、命名、合理的默认值、常见 API 用法等）
- 每次生成任务最多提问 2 次
- 提问时务必简洁明确
"""

    return prompt


def register_codemage_agent(
    context: Context,
    config,
    installer,
    work_dir: str,
    astrbot_root: str,
) -> HandoffTool:
    auto_approve = config.get("auto_approve", False)
    negative_prompt = config.get("negative_prompt", "")

    system_prompt = _build_system_prompt(
        work_dir=work_dir,
        astrbot_root=astrbot_root,
        negative_prompt=negative_prompt,
        allow_ask_user=not auto_approve,
    )

    custom_tools = build_custom_tools(
        installer, work_dir, allow_ask_user=not auto_approve
    )
    tools = list(_BUILTIN_TOOL_NAMES) + custom_tools

    agent = Agent(name="codemage", instructions=system_prompt, tools=tools)
    handoff = HandoffTool(agent=agent)

    provider_id = config.get("llm_provider_id")
    if provider_id:
        handoff.provider_id = provider_id

    llm_tools.func_list.append(handoff)

    return handoff


def unregister_codemage_agent(handoff: HandoffTool) -> None:
    if handoff in llm_tools.func_list:
        llm_tools.func_list.remove(handoff)


def _build_toolset_for_command(
    context: Context,
    event: AstrMessageEvent,
    custom_tools: list[FunctionTool],
) -> ToolSet:
    tool_mgr = context.get_llm_tool_manager()
    cfg = context.get_config(umo=event.unified_msg_origin)
    provider_settings = cfg.get("provider_settings", {})
    runtime = str(provider_settings.get("computer_use_runtime", "local"))
    booter = provider_settings.get("sandbox", {}).get("booter")

    runtime_tools = FunctionToolExecutor._get_runtime_computer_tools(
        runtime, tool_mgr, booter
    )

    toolset = ToolSet()
    for name in _BUILTIN_TOOL_NAMES:
        if name in runtime_tools:
            toolset.add_tool(runtime_tools[name])
    for tool in custom_tools:
        toolset.add_tool(tool)

    return toolset


def _extract_plugin_name(llm_resp, work_dir: str | None = None) -> str | None:
    text = getattr(llm_resp, "completion_text", "") or ""
    match = re.search(r"astrbot_plugin_[a-zA-Z0-9_]+", text)
    if match:
        return match.group(0)

    if work_dir and os.path.isdir(work_dir):
        for entry in os.listdir(work_dir):
            if entry.startswith("astrbot_plugin_") and os.path.isdir(
                os.path.join(work_dir, entry)
            ):
                return entry

    return None


async def run_agent_mode(
    context: Context,
    config,
    event: AstrMessageEvent,
    description: str,
    installer,
    work_dir: str,
    astrbot_root: str,
) -> dict:
    auto_approve = config.get("auto_approve", False)
    provider_id = config.get("llm_provider_id")
    negative_prompt = config.get("negative_prompt", "")

    if not provider_id:
        try:
            provider_id = await context.get_current_chat_provider_id(
                event.unified_msg_origin
            )
        except Exception:
            return {
                "success": False,
                "error": "未配置 LLM 提供商 ID，请在插件配置中设置 llm_provider_id",
            }

    system_prompt = _build_system_prompt(
        work_dir=work_dir,
        astrbot_root=astrbot_root,
        negative_prompt=negative_prompt,
        allow_ask_user=not auto_approve,
    )

    custom_tools = build_custom_tools(
        installer, work_dir, allow_ask_user=not auto_approve
    )
    toolset = _build_toolset_for_command(context, event, custom_tools)

    if toolset.empty():
        return {
            "success": False,
            "error": "无法构建工具集，请检查 AstrBot 配置中的 computer_use_runtime 设置",
        }

    try:
        llm_resp = await context.tool_loop_agent(
            event=event,
            chat_provider_id=provider_id,
            prompt=description,
            system_prompt=system_prompt,
            tools=toolset,
            max_steps=_AGENT_MAX_STEPS,
            tool_call_timeout=config.get("llm_timeout_seconds", 600),
        )

        if getattr(llm_resp, "role", "") == "err":
            return {
                "success": False,
                "error": llm_resp.completion_text or "LLM 请求失败",
            }

        completion_text = getattr(llm_resp, "completion_text", "") or ""
        if not completion_text.strip():
            plugin_name = _extract_plugin_name(llm_resp, work_dir)
            if plugin_name:
                return {
                    "success": True,
                    "plugin_name": plugin_name,
                    "response": "",
                }
            return {
                "success": False,
                "error": "Agent 未返回有效结果，且工作目录中未找到生成的插件",
            }

        plugin_name = _extract_plugin_name(llm_resp, work_dir)
        if not plugin_name:
            return {
                "success": False,
                "error": "Agent 未通过 finish 工具正常结束，且无法识别生成的插件名称",
            }

        return {
            "success": True,
            "plugin_name": plugin_name,
            "response": completion_text,
        }
    except Exception as e:
        logger.error(f"Agent 模式生成插件失败: {e}")
        return {"success": False, "error": str(e)}
