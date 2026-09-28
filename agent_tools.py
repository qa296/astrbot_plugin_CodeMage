import os

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.agent.tool import FunctionTool


def _validate_plugin_name(plugin_name: str) -> str | None:
    if ".." in plugin_name or "/" in plugin_name or "\\" in plugin_name:
        return "插件名称包含非法路径字符"
    if not plugin_name.startswith("astrbot_plugin_"):
        return "插件名称必须以 astrbot_plugin_ 开头"
    return None


async def _install_handler(
    event, plugin_name: str, installer, work_dir, **kwargs
) -> str:
    validation_error = _validate_plugin_name(plugin_name)
    if validation_error:
        return f"安装失败：{validation_error}"

    plugin_dir = os.path.join(work_dir, plugin_name)
    if not os.path.isdir(plugin_dir):
        return f"安装失败：插件目录不存在：{plugin_dir}"

    installer.set_install_timestamp()

    zip_path = await installer.create_plugin_zip(plugin_dir)
    if not zip_path:
        return "安装失败：插件打包失败"

    try:
        install_result = await installer.install_plugin(zip_path, plugin_name)
        if not install_result.get("success"):
            return f"安装失败：{install_result.get('error', '未知错误')}"

        status_result = await installer.check_plugin_install_status(plugin_name)

        if status_result.get("has_errors"):
            error_logs = "\n".join(status_result.get("error_logs", [])[:3])
            return f"安装成功，但插件存在运行时错误：\n{error_logs}"

        if not status_result.get("loaded", True):
            return f"安装成功，但插件未能加载：{status_result.get('error', '未知错误')}"

        return "安装成功，插件已正常加载运行。"
    except Exception as e:
        logger.error(f"安装插件时发生错误: {e}")
        return f"安装失败：{str(e)}"
    finally:
        try:
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass


async def _ask_user_handler(event: AstrMessageEvent, question: str, **kwargs) -> str:
    from astrbot.core.utils.session_waiter import SessionController, session_waiter

    await event.send(event.plain_result(f"🤔 {question}"))

    user_response = None

    @session_waiter(timeout=120, record_history_chains=False)
    async def wait_for_user(controller: SessionController, event: AstrMessageEvent):
        nonlocal user_response
        user_response = event.message_str
        controller.stop()

    try:
        await wait_for_user(event)
    except TimeoutError:
        return "用户未在120秒内回复，请自行判断继续执行。"

    return user_response or "用户未提供有效回复。"


def build_install_tool(installer, work_dir) -> FunctionTool:
    async def handler(event, plugin_name: str, **kwargs) -> str:
        return await _install_handler(
            event, plugin_name, installer=installer, work_dir=work_dir, **kwargs
        )

    return FunctionTool(
        name="codemage_install_plugin",
        parameters={
            "type": "object",
            "properties": {
                "plugin_name": {
                    "type": "string",
                    "description": "插件名称，如 astrbot_plugin_weather",
                }
            },
            "required": ["plugin_name"],
        },
        description="将已生成的插件打包安装到 AstrBot，并自动检查是否有运行时错误。调用前确保所有文件已写入工作目录。",
        handler=handler,
    )


def build_ask_user_tool() -> FunctionTool:
    async def handler(event, question: str, **kwargs) -> str:
        return await _ask_user_handler(event, question, **kwargs)

    return FunctionTool(
        name="codemage_ask_user",
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要问用户的问题",
                }
            },
            "required": ["question"],
        },
        description="向用户提问并等待回复。仅在确实缺少关键信息且无法合理推断时使用。",
        handler=handler,
    )


def build_custom_tools(
    installer, work_dir, allow_ask_user: bool = True
) -> list[FunctionTool]:
    tools = [build_install_tool(installer, work_dir)]
    if allow_ask_user:
        tools.append(build_ask_user_tool())
    return tools
