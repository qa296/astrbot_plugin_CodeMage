"""
CodeMage - AI驱动的AstrBot插件生成器
根据用户描述自动生成AstrBot插件
"""

import os
import json
import asyncio
import hashlib
from typing import Optional, Dict, Any
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController

from .llm_handler import LLMHandler
from .plugin_generator import PluginGenerator
from .directory_detector import DirectoryDetector
from .installer import PluginInstaller
from .utils import validate_plugin_description, format_plugin_info


@register(
    "astrbot_plugin_codemage",
    "qa296",
    "AI驱动的AstrBot插件生成器",
    "1.0.0",
    "https://github.com/qa296/astrbot_plugin_codemage",
)
class CodeMagePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.llm_handler = LLMHandler(context, config)
        self.installer = PluginInstaller(config)
        self.plugin_generator = PluginGenerator(context, config, self.installer, star=self)
        self.directory_detector = DirectoryDetector()

        # 初始化logger
        self.logger = logger

        # 验证配置
        self._validate_config()

    def _validate_config(self):
        """验证配置文件"""
        if not self.config.get("llm_provider_id"):
            self.logger.warning("未配置LLM提供商ID，请检查配置")

    def _get_message_after_command(self, event: AstrMessageEvent) -> str:
        """获取指令后的完整文本，包含空格

        Args:
            event: 消息事件
        Returns:
            str: 指令后的完整文本（去除指令本身与前后空白）
        """
        try:
            msg = getattr(event, "message_str", "") or ""
            msg = str(msg)
        except Exception:
            msg = ""
        msg = msg.strip()
        if not msg:
            return ""
        # 按第一个空白分割，后面的原样保留
        # 例如："/生成插件 创建 一个 天气 插件" -> "创建 一个 天气 插件"
        parts = msg.split(maxsplit=1)
        if len(parts) < 2:
            return ""
        return parts[1].strip()

    def _check_admin_permission(self, event: AstrMessageEvent) -> bool:
        """检查管理员权限

        Args:
            event: 消息事件

        Returns:
            bool: 是否有管理员权限
        """
        if not self.config.get("admin_only", True):
            return True

        # 优先使用 AstrBot 事件自身提供的管理员判定
        try:
            # 标准方法：event.is_admin()
            if hasattr(event, "is_admin"):
                is_admin_attr = getattr(event, "is_admin")
                if callable(is_admin_attr):
                    if is_admin_attr():
                        return True
                else:
                    # 某些实现可能将其作为布尔属性暴露
                    if bool(is_admin_attr):
                        return True
 
            # 兼容属性：event.role == "admin"
            role = getattr(event, "role", None)
            if isinstance(role, str) and role.lower() == "admin":
                return True
        except Exception as e:
            self.logger.warning(f"检查管理员权限时发生错误: {str(e)}")

        # 兼容性兜底：从 AstrBot 配置里匹配可能的管理员 ID 列表
        try:
            sender_id = str(event.get_sender_id())
            astrbot_config = self.context.get_config()
            for key in ("admins", "admin_ids", "admin_list", "superusers", "super_users"):
                ids = astrbot_config.get(key, [])
                if isinstance(ids, (list, tuple, set)):
                    if sender_id in {str(i) for i in ids}:
                        return True
        except Exception:
            # 忽略兜底检查中的异常
            pass
 
        # 默认拒绝
        return False

    @filter.command("生成插件", alias={"create_plugin", "new_plugin"})
    async def generate_plugin_command(self, event: AstrMessageEvent):
        """生成AstrBot插件指令

        使用完整消息解析，支持空格
        """
        # 检查管理员权限
        if not self._check_admin_permission(event):
            yield event.plain_result("⚠️ 仅管理员可以使用此功能")
            return

        # 从完整消息中提取描述，避免空格被截断
        plugin_description = self._get_message_after_command(event)

        if not plugin_description:
            yield event.plain_result(
                "请提供插件描述，例如：/生成插件 创建一个天气查询插件"
            )
            return

        # 验证描述
        if not validate_plugin_description(plugin_description):
            yield event.plain_result("插件描述不合适，请重新描述")
            return

        # 开始生成流程
        try:
            yield event.plain_result("开始生成插件，请稍候...")
            result = await self.plugin_generator.generate_plugin_flow(
                plugin_description, event
            )

            if result["success"]:
                message = f"插件生成成功！\n插件名称：{result['plugin_name']}\n插件路径：{result['plugin_path']}"
                if result.get("installed"):
                    message += f"\n安装状态：{'✅ 已安装' if result.get('install_success') else '❌ 安装失败'}"
                    if not result.get("install_success"):
                        message += (
                            f"\n安装错误：{result.get('install_error', '未知错误')}"
                        )
                yield event.plain_result(message)
            else:
                # 检查是否是等待用户确认的情况
                if result.get("pending_confirmation"):
                    # 不显示"插件生成失败"消息，因为这是正常的等待确认流程
                    pass
                else:
                    yield event.plain_result(f"插件生成失败：{result['error']}")

        except Exception as e:
            self.logger.error(f"插件生成过程中发生错误: {str(e)}")
            yield event.plain_result(f"插件生成失败：{str(e)}")

    @filter.command("插件生成状态", alias={"plugin_status"})
    async def plugin_status(self, event: AstrMessageEvent):
        """查看插件生成器状态"""
        # 获取当前生成状态
        current_status = self.plugin_generator.get_current_status()

        # 当前生成步骤信息
        if current_status["is_generating"]:
            status_info = f"""
当前插件生成状态：
- 正在生成：{"是" if current_status["is_generating"] else "否"}
- 当前步骤：{current_status["current_step"]}
- 总步骤：{current_status["total_steps"]}
- 进度：{current_status["progress_percentage"]}%
- 插件名称：{current_status.get("plugin_name", "未知")}
- 开始时间：{current_status.get("start_time", "未知")}
            """.strip()
        else:
            status_info = "当前没有正在进行的插件生成任务"

        yield event.plain_result(status_info)

    @filter.llm_tool(name="generate_plugin")
    async def generate_plugin_tool(
        self, event: AstrMessageEvent, plugin_description: str
    ) -> Dict[str, Any]:
        """通过函数调用生成插件

        Args:
            plugin_description(string): 插件功能描述

        Returns:
            dict: 生成结果
        """
        if not self.config.get("enable_function_call", True):
            return {"error": "函数调用未启用"}

        # 检查管理员权限
        if not self._check_admin_permission(event):
            return {"error": "仅管理员可以使用此功能"}

        try:
            result = await self.plugin_generator.generate_plugin_flow(
                plugin_description, event
            )
            return result
        except Exception as e:
            self.logger.error(f"函数调用生成插件失败: {str(e)}")
            return {"error": str(e)}

    @filter.command("密码转md5")
    async def md5_convert(self, event: AstrMessageEvent, password: str = ""):
        """将明文密码转换为MD5加密密码

        Args:
            password(string): 明文密码
        """
        if not password:
            yield event.plain_result("请提供要转换的密码，例如：/密码转md5 astrbot")
            return

        try:
            md5_password = hashlib.md5(password.encode()).hexdigest()
            result_message = f"MD5转换结果：\n明文密码：{password}\nMD5密码：{md5_password}\n\n请将MD5密码复制到插件配置中的 api_password_md5 字段"
            yield event.plain_result(result_message)
        except Exception as e:
            self.logger.error(f"MD5转换失败: {str(e)}")
            yield event.plain_result(f"MD5转换失败：{str(e)}")

    @filter.command("同意生成", alias={"approve", "confirm"})
    async def approve_generation(self, event: AstrMessageEvent, feedback: str = ""):
        """同意插件生成指令
        
        Args:
            feedback(string): 可选的修改反馈
        """
        # 检查管理员权限
        if not self._check_admin_permission(event):
            yield event.plain_result("⚠️ 仅管理员可以使用此功能")
            return
            
        # 获取待确认的任务
        pending = self.plugin_generator.get_pending_generation()
        if not pending["active"]:
            yield event.plain_result("当前没有待确认的插件生成任务")
            return
            
        # 继续插件生成流程
        try:
            yield event.plain_result("正在继续插件生成流程...")
            result = await self.plugin_generator.continue_plugin_generation(True, feedback, event)
            
            if result["success"]:
                message = f"插件生成成功！\n插件名称：{result['plugin_name']}\n插件路径：{result['plugin_path']}"
                if result.get("installed"):
                    message += f"\n安装状态：{'✅ 已安装' if result.get('install_success') else '❌ 安装失败'}"
                    if not result.get("install_success"):
                        message += (
                            f"\n安装错误：{result.get('install_error', '未知错误')}"
                        )
                yield event.plain_result(message)
            else:
                if not result.get("pending_confirmation"):
                    yield event.plain_result(f"插件生成失败：{result['error']}")
                # 如果是pending_confirmation状态，不显示错误消息，因为这是正常的等待确认流程
        except Exception as e:
            self.logger.error(f"同意插件生成过程中发生错误: {str(e)}")
            yield event.plain_result(f"插件生成失败：{str(e)}")

    @filter.command("拒绝生成", alias={"reject", "cancel"})
    async def reject_generation(self, event: AstrMessageEvent):
        """拒绝插件生成指令
        
        Args:
            无参数
        """
        # 检查管理员权限
        if not self._check_admin_permission(event):
            yield event.plain_result("⚠️ 仅管理员可以使用此功能")
            return
            
        # 获取待确认的任务
        pending = self.plugin_generator.get_pending_generation()
        if not pending["active"]:
            yield event.plain_result("当前没有待确认的插件生成任务")
            return
            
        # 取消插件生成流程
        try:
            result = await self.plugin_generator.continue_plugin_generation(False, event=event)
            yield event.plain_result("已完全停止插件生成")
        except Exception as e:
            self.logger.error(f"拒绝插件生成过程中发生错误: {str(e)}")
            yield event.plain_result(f"停止插件生成失败：{str(e)}")

    @filter.command("插件内容修改", alias={"modify_plugin", "modify"})
    async def modify_plugin_content(self, event: AstrMessageEvent):
        """选择性修改插件内容指令
        
        通过完整消息解析，支持空格。
        用法：/插件内容修改 修改内容 [配置文件|文档|元数据|全部]
        如果未指定类型，默认为“全部”。
        """
        # 检查管理员权限
        if not self._check_admin_permission(event):
            yield event.plain_result("⚠️ 仅管理员可以使用此功能")
            return
            
        # 获取待确认的任务
        pending = self.plugin_generator.get_pending_generation()
        if not pending["active"]:
            yield event.plain_result("当前没有待确认的插件生成任务")
            return
        
        # 从完整消息中提取参数文本
        args_text = self._get_message_after_command(event)
        if not args_text:
            yield event.plain_result("请提供修改内容，例如：/插件内容修改 增加一个用户名配置项 配置文件")
            return
        
        # 解析修改类型（若最后一个独立词为合法类型，则作为类型；否则默认为“全部”）
        valid_types = {"配置文件", "文档", "元数据", "全部"}
        modification_type = "全部"
        feedback = args_text.strip()
        parts = args_text.rsplit(None, 1)
        if len(parts) == 2 and parts[1] in valid_types:
            feedback = parts[0].strip()
            modification_type = parts[1]
        
        if not feedback:
            yield event.plain_result("请提供修改内容，例如：/插件内容修改 增加一个用户名配置项 配置文件")
            return
            
        # 执行修改
        try:
            yield event.plain_result(f"正在修改{modification_type}...")
            result = await self.plugin_generator.modify_plugin_content(modification_type, feedback, event)
            
            if result["success"]:
                pass  # 消息已在modify_plugin_content方法中发送
            else:
                yield event.plain_result(f"修改失败：{result.get('error', '未知错误')}")
        except Exception as e:
            self.logger.error(f"修改插件内容过程中发生错误: {str(e)}")
            yield event.plain_result(f"修改失败：{str(e)}")

    async def terminate(self):
        """插件卸载时调用"""
        self.logger.info("CodeMage插件已卸载")
