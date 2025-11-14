'''
CodeMage插件生成器模块
负责协调整个插件生成流程
'''

import os
import json
import time
import shutil
from typing import Dict, Any, Optional, List, Tuple
from astrbot.api import logger
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent

from .llm_handler import LLMHandler
from .directory_detector import DirectoryDetector
from .utils import (
    sanitize_plugin_name, 
    create_plugin_directory,
    format_time
)


class PluginGenerator:
    '''插件生成器类'''
    
    def __init__(self, context: Context, config: AstrBotConfig, installer=None, star: Optional[Star] = None):
        self.context = context
        self.config = config
        self.llm_handler = LLMHandler(context, config)
        self.directory_detector = DirectoryDetector()
        self.installer = installer
        self.logger = logger
        self.star = star
        
        # 生成状态
        self.generation_status = {
            "is_generating": False,
            "current_step": 0,
            "total_steps": 6,
            "progress_percentage": 0,
            "plugin_name": "",
            "start_time": "",
            "step_descriptions": [
                "生成插件元数据",
                "生成插件文档",
                "生成配置文件",
                "生成插件代码",
                "代码审查与修复",
                "打包并安装插件"
            ]
        }
        
        # 待确认的插件生成任务
        self.pending_generation = {
            "active": False,
            "metadata": {},
            "markdown": "",
            "config_schema": "",
            "description": "",
            "event": None,
            "umo": "",
            "timestamp": "",
            "awaiting_confirmation": False,
            "modification_history": []
        }

        # 初始化时尝试加载持久化的待确认任务
        try:
            self._load_pending_state()
        except Exception:
            pass
        
    def get_current_status(self) -> Dict[str, Any]:
        '''获取当前生成状态

        Returns:
            Dict[str, Any]: 当前状态
        '''
        return self.generation_status.copy()

    # ---- 待确认任务持久化 ----
    def _get_state_dir(self) -> Optional[str]:
        """获取状态文件目录(data/codemage)，若不存在则尝试创建"""
        data_dir = self.directory_detector.get_data_directory()
        if not data_dir:
            return None
        state_dir = os.path.join(data_dir, "codemage")
        try:
            os.makedirs(state_dir, exist_ok=True)
        except Exception:
            pass
        return state_dir

    def _get_state_file_path(self) -> Optional[str]:
        """获取持久化状态文件路径"""
        state_dir = self._get_state_dir()
        if not state_dir:
            return None
        return os.path.join(state_dir, "pending_generation.json")

    def _save_pending_state(self):
        """将待确认任务持久化到文件（不保存 event 对象）"""
        try:
            path = self._get_state_file_path()
            if not path:
                return
            # 仅保存可序列化字段
            data = {
                "active": self.pending_generation.get("active", False),
                "metadata": self.pending_generation.get("metadata", {}),
                "markdown": self.pending_generation.get("markdown", ""),
                "config_schema": self.pending_generation.get("config_schema", ""),
                "description": self.pending_generation.get("description", ""),
                "umo": self.pending_generation.get("umo", ""),
                "timestamp": self.pending_generation.get("timestamp", ""),
                "awaiting_confirmation": self.pending_generation.get("awaiting_confirmation", False),
                "modification_history": self.pending_generation.get("modification_history", []),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.warning(f"保存待确认状态失败: {str(e)}")

    def _load_pending_state(self):
        """从文件加载待确认任务（不会恢复 event 对象）"""
        try:
            path = self._get_state_file_path()
            if not path or not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 合并状态
            self.pending_generation.update({
                "active": data.get("active", False),
                "metadata": data.get("metadata", {}),
                "markdown": data.get("markdown", ""),
                "config_schema": data.get("config_schema", ""),
                "description": data.get("description", ""),
                "umo": data.get("umo", ""),
                "timestamp": data.get("timestamp", ""),
                "awaiting_confirmation": data.get("awaiting_confirmation", False),
                "modification_history": data.get("modification_history", []),
            })
        except Exception as e:
            self.logger.warning(f"加载待确认状态失败: {str(e)}")

    def _delete_pending_state(self):
        """删除持久化的待确认任务文件"""
        try:
            path = self._get_state_file_path()
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            self.logger.warning(f"删除待确认状态文件失败: {str(e)}")

    def _update_status(self, step: int, plugin_name: str = ""):
        '''更新生成状态

        Args:
            step: 当前步骤
            plugin_name: 插件名称
        '''
        self.generation_status["current_step"] = step
        self.generation_status["progress_percentage"] = int((step / self.generation_status["total_steps"]) * 100)
        if plugin_name:
            self.generation_status["plugin_name"] = plugin_name

    def _build_step_message(self) -> str:
        '''构建当前步骤提示信息'''
        current_step = self.generation_status.get("current_step", 0)
        total_steps = self.generation_status.get("total_steps", 0)
        if not current_step:
            return ""
        descriptions = self.generation_status.get("step_descriptions", [])
        index = max(0, min(current_step - 1, len(descriptions) - 1))
        description = descriptions[index] if descriptions else ""
        return f"步骤{current_step}/{total_steps}：{description}"

    def _build_preview_text(self, meta: Dict[str, Any], markdown: str, config_schema: str) -> str:
        '''构建插件方案预览文本（不截断，不添加省略号）'''
        lines = [
            f"插件名称：{meta.get('name', '未知')}",
            f"作者：{meta.get('author', '未知')}",
            f"描述：{meta.get('description', '无描述')}",
            f"版本：{meta.get('version', '1.0.0')}"
        ]
        commands = meta.get("commands", [])
        if isinstance(commands, list) and commands:
            lines.append("指令预览：")
            for cmd in commands[:5]:
                if isinstance(cmd, dict):
                    cmd_name = cmd.get("command") or cmd.get("name") or cmd.get("title") or "未知指令"
                    cmd_desc = cmd.get("description") or cmd.get("desc") or ""
                    lines.append(f"  - {cmd_name}: {cmd_desc}")
                else:
                    lines.append(f"  - {cmd}")
        # 文档和配置均以图片形式发送，避免文本被截断
        if (markdown or '').strip():
            lines.append("文档：已转换为图片发送")
        if (config_schema or '').strip():
            lines.append("配置：已转换为图片发送")
        return "\n".join(lines)

    def _normalize_config_schema(self, config_schema: str) -> str:
        '''规范化配置文件内容'''
        if not config_schema or not config_schema.strip():
            return ""
        try:
            parsed = json.loads(config_schema)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return config_schema

    def _format_default_value(self, item_schema: Dict[str, Any]) -> str:
        """将默认值格式化为可读字符串（布尔值显示为[x]/[ ]）"""
        default = item_schema.get("default", None)
        t = (item_schema.get("type") or "").lower()
        if default is None:
            if t == "int":
                default = 0
            elif t == "float":
                default = 0.0
            elif t == "bool":
                default = False
            elif t == "object":
                default = {}
            elif t == "list":
                default = []
            else:
                default = ""
        if t == "bool":
            return "[x]" if bool(default) else "[ ]"
        try:
            return json.dumps(default, ensure_ascii=False)
        except Exception:
            return str(default)

    def _build_config_rows(self, schema: Dict[str, Any]) -> List[Dict[str, str]]:
        """从 _conf_schema.json 的 schema 构建人类可读的表格行"""
        rows: List[Dict[str, str]] = []

        def walk(item_key: str, item: Dict[str, Any], parent_label: Optional[str] = None):
            desc = item.get("description") or item_key
            name_label = f"{parent_label} > {desc}" if parent_label else desc
            hint = item.get("hint")
            t = item.get("type", "")
            options = item.get("options")
            detail_parts: List[str] = []
            if desc:
                detail_parts.append(str(desc))
            if hint:
                detail_parts.append(str(hint))
            if t:
                detail_parts.append(f"类型: {t}")
            if options and isinstance(options, list) and options:
                try:
                    opts = ", ".join([str(o) for o in options])
                except Exception:
                    opts = str(options)
                detail_parts.append(f"可选项: {opts}")
            default_str = self._format_default_value(item)
            rows.append({
                "name": name_label,
                "detail": "\n".join(detail_parts) if detail_parts else "",
                "default": default_str
            })
            if (item.get("type") == "object") and isinstance(item.get("items"), dict):
                for sub_key, sub_item in item.get("items").items():
                    if isinstance(sub_item, dict):
                        parent_name = item.get("description") or item_key
                        walk(sub_key, sub_item, parent_label=parent_name)

        for key, item in (schema or {}).items():
            if isinstance(item, dict):
                walk(key, item, parent_label=None)
        return rows

    def _normalize_review_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """规范化LLM审查结果结构"""
        normalized: Dict[str, Any] = {}
        if isinstance(result, dict):
            normalized.update(result)
        else:
            normalized["reason"] = str(result)
        approved = normalized.get("approved")
        if approved is None:
            approved = normalized.get("是否同意") or normalized.get("agree")
        if isinstance(approved, str):
            approved = approved.strip().lower() in {"true", "yes", "同意", "通过", "approved"}
        normalized["approved"] = bool(approved)
        satisfaction = normalized.get("satisfaction_score")
        if satisfaction is None:
            satisfaction = normalized.get("满意分数") or normalized.get("score")
        try:
            satisfaction = int(float(satisfaction))
        except (TypeError, ValueError):
            satisfaction = 0
        normalized["satisfaction_score"] = satisfaction
        reason = normalized.get("reason") or normalized.get("理由") or ""
        normalized["reason"] = reason
        issues = normalized.get("issues") or normalized.get("问题") or []
        if isinstance(issues, str):
            issues = [issues]
        if not isinstance(issues, list):
            issues = [str(issues)]
        if not issues and reason:
            issues = [reason]
        normalized["issues"] = issues
        suggestions = normalized.get("suggestions") or normalized.get("建议") or []
        if isinstance(suggestions, str):
            suggestions = [suggestions]
        if not isinstance(suggestions, list):
            suggestions = [str(suggestions)]
        if not suggestions and reason:
            suggestions = ["请根据以下理由修复问题：" + reason]
        normalized["suggestions"] = suggestions
        return normalized

    async def _ensure_code_review_passed(
        self,
        code: str,
        metadata: Dict[str, Any],
        markdown_doc: str,
        event: AstrMessageEvent,
        satisfaction_threshold: int,
        strict_review: bool,
        max_retries: int,
        unlimited_retry: bool,
    ) -> Tuple[str, Dict[str, Any], bool]:
        """确保代码审查通过，如有需要自动调用LLM修复"""
        review_result = self._normalize_review_result(
            await self._review_code_with_retry(code, metadata, markdown_doc)
        )
        attempt = 0
        while ((review_result["satisfaction_score"] < satisfaction_threshold) or (not review_result["approved"])):
            if not unlimited_retry and attempt >= max_retries:
                break
            attempt += 1
            if strict_review and not review_result["approved"]:
                await event.send(event.plain_result(f"代码审查未通过，正在修复（第{attempt}次重试）..."))
            else:
                await event.send(event.plain_result(f"代码满意度不足（{review_result['satisfaction_score']}分），正在优化（第{attempt}次重试）..."))
            issues = review_result.get("issues") or []
            if not issues:
                issues = [review_result.get("reason", "代码审查未通过")]
            suggestions = review_result.get("suggestions") or []
            if not suggestions:
                suggestions = ["请根据上述问题修复插件代码"]
            try:
                code = await self.llm_handler.fix_plugin_code(code, issues, suggestions)
            except Exception as fix_err:
                self.logger.error(f"修复插件代码失败：{str(fix_err)}")
                raise
            review_result = self._normalize_review_result(
                await self.llm_handler.review_plugin_code(code, metadata, markdown_doc)
            )
        passed = bool(review_result.get("approved")) and review_result.get("satisfaction_score", 0) >= satisfaction_threshold
        return code, review_result, passed

    async def _install_via_api(
        self,
        plugin_name: str,
        metadata: Dict[str, Any],
        code: str,
        markdown_doc: str,
        config_schema: str,
    ) -> Dict[str, Any]:
        """通过 AstrBot API 安装插件并进行错误检测"""
        import tempfile

        outcome: Dict[str, Any] = {
            "success": False,
            "installed": False,
            "error": "",
            "issues": [],
            "cleanup": True,
            "status_check": None,
            "status_check_success": None,
            "status_check_error": None,
            "post_install_errors": False,
            "warnings": [],
        }
        if not self.installer or not self.config.get("api_password_md5"):
            outcome["error"] = "未配置API安装"
            outcome["cleanup"] = False
            return outcome

        temp_dir = tempfile.mkdtemp(prefix="codemage_plugin_")
        zip_path: Optional[str] = None
        try:
            plugin_path = await self._create_plugin_files(
                plugin_name, metadata, code, markdown_doc, config_schema, base_dir=temp_dir
            )
            self.logger.info(f"插件已在临时目录生成: {plugin_name} -> {plugin_path}")

            zip_path = await self.installer.create_plugin_zip(plugin_path)
            if not zip_path:
                outcome["error"] = "插件打包失败"
                outcome["issues"] = ["插件打包失败"]
                return outcome

            install_result = await self.installer.install_plugin(zip_path, plugin_name=plugin_name)
            outcome["installed"] = bool(install_result.get("success"))
            if not install_result.get("success"):
                err_msg = install_result.get("error", "未知错误")
                outcome["error"] = err_msg
                outcome["issues"] = [err_msg]
                return outcome

            status_check = await self.installer.check_plugin_install_status(plugin_name)
            outcome["status_check"] = status_check
            outcome["status_check_success"] = status_check.get("success")

            if not status_check.get("success"):
                outcome["status_check_error"] = status_check.get("error")
                outcome["success"] = True
                outcome["cleanup"] = False
                return outcome

            if status_check.get("has_errors"):
                error_logs = status_check.get("error_logs", [])
                message = "\n".join(error_logs) if error_logs else status_check.get("error") or "插件安装后检测到错误"
                outcome["error"] = message
                outcome["issues"] = error_logs or [message]
                outcome["post_install_errors"] = True
                return outcome

            if status_check.get("has_warnings"):
                outcome["warnings"] = status_check.get("warning_logs", [])

            outcome["success"] = True
            outcome["cleanup"] = False
            return outcome
        except Exception as api_err:
            error_text = str(api_err)
            self.logger.error(f"API安装过程中发生异常: {error_text}")
            outcome["error"] = error_text
            outcome["issues"] = [error_text]
            return outcome
        finally:
            if zip_path and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _install_via_file(
        self,
        plugin_name: str,
        metadata: Dict[str, Any],
        code: str,
        markdown_doc: str,
        config_schema: str,
    ) -> Dict[str, Any]:
        """通过文件方式安装插件"""
        outcome: Dict[str, Any] = {"success": False, "plugin_path": "", "deletion": None}

        deletion_result = self._delete_plugin_files(plugin_name)
        outcome["deletion"] = deletion_result
        if deletion_result.get("success") is False:
            outcome["error"] = deletion_result.get("error", "插件目录删除失败")
            return outcome

        try:
            plugin_path = await self._create_plugin_files(
                plugin_name, metadata, code, markdown_doc, config_schema
            )
            self.logger.info(f"插件生成成功: {plugin_name} -> {plugin_path}")
            outcome["success"] = True
            outcome["plugin_path"] = plugin_path
            return outcome
        except Exception as file_err:
            error_text = str(file_err)
            self.logger.error(f"本地创建插件文件失败: {error_text}")
            outcome["error"] = error_text
            return outcome

    def _delete_plugin_files(self, plugin_name: str) -> Dict[str, Any]:
        """删除插件目录"""
        plugin_path = self.directory_detector.get_plugin_path(plugin_name)
        if not plugin_path or not os.path.exists(plugin_path):
            return {"success": True, "skipped": True}
        try:
            shutil.rmtree(plugin_path)
            self.logger.info(f"已删除插件目录: {plugin_path}")
            return {"success": True, "path": plugin_path}
        except Exception as remove_err:
            error_text = str(remove_err)
            self.logger.error(f"删除插件目录失败: {error_text}")
            return {"success": False, "error": error_text, "path": plugin_path}

    async def _cleanup_plugin_installation(self, plugin_name: str) -> Dict[str, Any]:
        """在安装失败后清理插件"""
        cleanup_info: Dict[str, Any] = {"api": None, "file": None}
        api_success = False

        if self.installer and self.config.get("api_password_md5"):
            try:
                api_result = await self.installer.uninstall_plugin(plugin_name)
            except Exception as api_err:
                api_result = {"success": False, "error": str(api_err)}
            cleanup_info["api"] = api_result
            api_success = bool(api_result.get("success"))

        if not api_success:
            cleanup_info["file"] = self._delete_plugin_files(plugin_name)
        else:
            cleanup_info["file"] = {"success": True, "skipped": True}

        return cleanup_info

    async def _send_doc_and_config_images(self, event: AstrMessageEvent, metadata: Dict[str, Any], markdown: str, config_schema: str):
        """使用 AstrBot 的 t2i 将文档与配置以图片形式发送，并将配置转成可读表格"""
        if not self.star:
            return
        # 发送文档图片
        doc_text = (markdown or "").strip()
        if doc_text:
            try:
                DOC_TMPL = '''
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; font-size: 14px; color: #222; padding: 16px;">
  <h2 style="margin:0 0 12px;">{{ title }}</h2>
  <div style="white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; line-height: 1.6;">{{ content }}</div>
</div>
'''
                title = f"{metadata.get('name', '插件')} 文档"
                url = await self.star.html_render(DOC_TMPL, {"title": title, "content": doc_text})
                await event.send(event.image_result(url))
            except Exception as e:
                # 回退到简单的文本转图
                try:
                    url = await self.star.text_to_image(f"{metadata.get('name', '插件')} 文档\n\n{doc_text}")
                    await event.send(event.image_result(url))
                except Exception:
                    await event.send(event.plain_result(doc_text[:1800]))
        # 发送配置图片
        cfg_text = (config_schema or "").strip()
        if cfg_text:
            try:
                schema_obj = json.loads(cfg_text)
            except Exception:
                schema_obj = None
            if isinstance(schema_obj, dict):
                rows = self._build_config_rows(schema_obj)
                try:
                    CONFIG_TMPL = '''
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; font-size: 14px; color: #222; padding: 16px;">
  <h2 style="margin:0 0 12px;">{{ title }}</h2>
  <table style="border-collapse: collapse; width: 100%; table-layout: fixed;">
    <thead>
      <tr>
        <th style="border:1px solid #ddd; padding:8px; width:28%;">选项</th>
        <th style="border:1px solid #ddd; padding:8px;">详细内容</th>
        <th style="border:1px solid #ddd; padding:8px; width:20%;">默认值</th>
      </tr>
    </thead>
    <tbody>
    {% for row in rows %}
      <tr>
        <td style="border:1px solid #ddd; padding:8px; word-break: break-all;">{{ row.name }}</td>
        <td style="border:1px solid #ddd; padding:8px; word-break: break-word; white-space: pre-wrap;">{{ row.detail }}</td>
        <td style="border:1px solid #ddd; padding:8px; word-break: break-all;">{{ row.default }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</div>
'''
                    title = f"{metadata.get('name', '插件')} 配置"
                    url = await self.star.html_render(CONFIG_TMPL, {"title": title, "rows": rows})
                    await event.send(event.image_result(url))
                except Exception as e:
                    # 回退到文本转图
                    try:
                        lines = ["选项  详细内容  默认值"]
                        for r in rows:
                            lines.append(f"{r['name']}  {r['detail']}  {r['default']}")
                        url = await self.star.text_to_image("\n".join(lines))
                        await event.send(event.image_result(url))
                    except Exception:
                        await event.send(event.plain_result("\n".join([json.dumps(schema_obj, ensure_ascii=False)[:1800]])))
            else:
                # 如果不是有效的JSON，直接转图发送原始文本
                try:
                    url = await self.star.text_to_image(cfg_text)
                    await event.send(event.image_result(url))
                except Exception:
                    await event.send(event.plain_result(cfg_text[:1800]))

    async def generate_plugin_flow(self, description: str, event: AstrMessageEvent) -> Dict[str, Any]:
        '''执行完整的插件生成流程
        Args:
            description: 插件描述
            event: 消息事件
            
        Returns:
            Dict[str, Any]: 生成结果
        '''
        # 检查是否正在生成
        if self.generation_status["is_generating"]:
            return {
                "success": False,
                "error": "已有插件正在生成中，请稍后再试"
            }
            
        # 设置生成状态
        self.generation_status["is_generating"] = True
        self.generation_status["start_time"] = format_time(time.time())
        

        try:
            # 验证目录结构（根据配置选择安装方式）
            install_method = self.config.get("install_method", "auto")
            restore_api_pwd = False
            saved_api_pwd = None
            if install_method == "api":
                use_api_install = True
                if not self.config.get("api_password_md5"):
                    await event.send(event.plain_result("已选择API安装，但未配置API密码(MD5)，将改为本地文件安装"))
                    use_api_install = False
                    # 确保后续不走API安装分支
                    saved_api_pwd = self.config.get("api_password_md5")
                    self.config["api_password_md5"] = ""
                    restore_api_pwd = True
            elif install_method == "file":
                use_api_install = False
                # 显式选择文件安装，避免误触发API安装
                saved_api_pwd = self.config.get("api_password_md5")
                if saved_api_pwd:
                    self.config["api_password_md5"] = ""
                    restore_api_pwd = True
            else:
                # auto 模式：如果配置了API密码则走API，否则走本地文件
                use_api_install = bool(self.installer and self.config.get("api_password_md5"))

            dir_validation = self.directory_detector.validate_directory_structure()
            if not dir_validation["valid"]:
                if use_api_install:
                    warn_msg = f"未检测到本地AstrBot安装目录，将使用API安装。{'; '.join(dir_validation['issues'])}"
                    await event.send(event.plain_result("未检测到本地AstrBot安装目录，将使用API安装插件"))
                    self.logger.warning(warn_msg)
                else:
                    message = f"目录结构验证失败：{'; '.join(dir_validation['issues'])}"
                    await event.send(event.plain_result(message))
                    self.logger.error(message)
                    return {
                        "success": False,
                        "error": message
                    }
                    
            step_by_step = self.config.get("step_by_step", True)
            metadata: Dict[str, Any] = {}
            markdown_doc = ""
            config_schema = ""
            
            # 步骤1：生成插件元数据
            self._update_status(1)
            await event.send(event.plain_result(self._build_step_message()))
            try:
                if step_by_step:
                    metadata = await self.llm_handler.generate_metadata_structure(description)
                else:
                    metadata = await self.llm_handler.generate_plugin_metadata(description)
                    markdown_doc = metadata.get("markdown", "")
            except Exception as generate_err:
                error_msg = f"生成插件元数据失败：{str(generate_err)}"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            
            if not isinstance(metadata, dict):
                error_msg = "LLM返回的插件元数据格式不正确"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            
            metadata.setdefault("metadata", {})
            metadata.setdefault("commands", [])
            plugin_name = sanitize_plugin_name(metadata.get("name", "astrbot_plugin_generated"))
            if not plugin_name.startswith("astrbot_plugin_"):
                plugin_name = f"astrbot_plugin_{plugin_name}"
            metadata["name"] = plugin_name
            self._update_status(1, plugin_name)
            
            # 检查插件是否已存在
            if self.directory_detector.check_plugin_exists(plugin_name):
                message = f"插件 '{plugin_name}' 已存在"
                await event.send(event.plain_result(message))
                self.logger.warning(message)
                return {
                    "success": False,
                    "error": message
                }
                
            # 步骤2：生成插件文档
            self._update_status(2, plugin_name)
            await event.send(event.plain_result(self._build_step_message()))
            try:
                if step_by_step or not markdown_doc:
                    markdown_doc = await self.llm_handler.generate_markdown_document(metadata, description)
            except Exception as doc_err:
                error_msg = f"生成插件文档失败：{str(doc_err)}"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            metadata["markdown"] = markdown_doc
            
            # 步骤3：生成配置文件
            self._update_status(3, plugin_name)
            await event.send(event.plain_result(self._build_step_message()))
            try:
                config_schema = await self.llm_handler.generate_config_schema(metadata, description)
                config_schema = self._normalize_config_schema(config_schema)
            except Exception as config_err:
                error_msg = f"生成配置文件失败：{str(config_err)}"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            
            # 显示初步生成的插件方案（仅元数据信息）
            await event.send(event.plain_result(f"初步生成的插件方案：\n\n{self._build_preview_text(metadata, '', '')}"))
            # 文档与配置以图片形式发送
            await self._send_doc_and_config_images(event, metadata, markdown_doc, config_schema)
            
            # 用户确认 - 修改为指令方式
            if not self.config.get("auto_approve", False):
                # 保存待确认的任务信息
                self.pending_generation = {
                    "active": True,
                    "metadata": metadata,
                    "markdown": markdown_doc,
                    "config_schema": config_schema,
                    "description": description,
                    "event": event,
                    "umo": getattr(event, "unified_msg_origin", ""),
                    "timestamp": format_time(time.time()),
                    "awaiting_confirmation": True,
                    "modification_history": []
                }
                # 持久化待确认任务，防止插件重载导致状态丢失
                self._save_pending_state()
                
                await event.send(event.plain_result("请使用指令 '/同意生成' 确认生成，或 '/拒绝生成' 取消生成，或 '/插件内容修改 <修改内容> [配置文件/文档/元数据/全部]' 进行修改。"))
                return {
                    "success": False,
                    "error": "等待用户确认",
                    "pending_confirmation": True
                }
            else:
                await event.send(event.plain_result("根据配置已自动批准插件方案。"))
            
            # 步骤4：生成插件代码
            self._update_status(4, plugin_name)
            await event.send(event.plain_result(self._build_step_message()))
            self.logger.info(f"开始生成插件代码: {plugin_name}")
            try:
                code = await self.llm_handler.generate_plugin_code(metadata, markdown_doc, config_schema)
            except Exception as code_err:
                error_msg = f"生成插件代码失败：{str(code_err)}"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            

        except Exception as e:
            self.logger.error(f"插件生成流程失败：{str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # 恢复API密码配置（如有临时修改）
            try:
                if restore_api_pwd:
                    self.config["api_password_md5"] = saved_api_pwd
            except Exception:
                pass
            self.generation_status["is_generating"] = False
            self.generation_status["current_step"] = 0
            self.generation_status["progress_percentage"] = 0
            self.generation_status["plugin_name"] = ""
            
    def get_pending_generation(self) -> Dict[str, Any]:
        '''获取待确认的插件生成任务
        
        Returns:
            Dict[str, Any]: 待确认任务信息
        '''
        # 如内存中不存在，尝试从文件恢复
        if not self.pending_generation.get("active"):
            try:
                self._load_pending_state()
            except Exception:
                pass
        return self.pending_generation.copy()
        
    def clear_pending_generation(self):
        '''清除待确认的插件生成任务'''
        # 删除持久化的状态文件
        try:
            self._delete_pending_state()
        except Exception:
            pass
        self.pending_generation = {
            "active": False,
            "metadata": {},
            "markdown": "",
            "config_schema": "",
            "description": "",
            "event": None,
            "umo": "",
            "timestamp": "",
            "awaiting_confirmation": False,
            "modification_history": []
        }
        
    async def continue_plugin_generation(self, approved: bool, feedback: str = "", event: Optional[AstrMessageEvent] = None) -> Dict[str, Any]:
        '''继续插件生成流程(用于指令确认)
        
        Args:
            approved: 是否同意生成
            feedback: 用户反馈(如果有)
            event: 当前消息事件，用于在继续流程时发送提示信息
            
        Returns:
            Dict[str, Any]: 生成结果
        '''
        if not self.pending_generation["active"]:
            # 尝试从文件恢复
            try:
                self._load_pending_state()
            except Exception:
                pass
        if not self.pending_generation["active"]:
            return {
                "success": False,
                "error": "没有待确认的插件生成任务"
            }
            
        # 获取当前任务信息
        metadata = self.pending_generation["metadata"]
        markdown_doc = self.pending_generation["markdown"]
        config_schema = self.pending_generation.get("config_schema", "")
        description = self.pending_generation["description"]
        if event is None:
            event = self.pending_generation["event"]
        else:
            self.pending_generation["event"] = event
        
        if not approved:
            await event.send(event.plain_result("用户拒绝，插件生成已完全停止"))
            return {
                "success": False,
                "error": "用户拒绝了插件生成"
            }
            
        # 如果有反馈，先优化插件方案
        if feedback:
            await event.send(event.plain_result("正在根据您的反馈优化插件方案..."))
            self.logger.info(f"根据用户反馈优化插件设计: {feedback}")
            try:
                metadata = await self.llm_handler.optimize_plugin_metadata(metadata, feedback)
                if not isinstance(metadata, dict):
                    raise ValueError("LLM返回的优化结果格式不正确")
                metadata.setdefault("metadata", {})
                metadata.setdefault("commands", [])
                markdown_doc = metadata.get("markdown", markdown_doc)
                plugin_name = sanitize_plugin_name(metadata.get("name", metadata.get("name", "generated_plugin")))
                if not plugin_name.startswith("astrbot_plugin_"):
                    plugin_name = f"astrbot_plugin_{plugin_name}"
                metadata["name"] = plugin_name
                metadata["markdown"] = markdown_doc

                combined_description = description
                if feedback:
                    combined_description = f"{description}\n\n用户反馈：{feedback}"
                config_schema = await self.llm_handler.generate_config_schema(metadata, combined_description)

                # 检查插件是否已存在
                if self.directory_detector.check_plugin_exists(plugin_name):
                    message = f"插件 '{plugin_name}' 已存在"
                    await event.send(event.plain_result(message))
                    self.logger.warning(message)
                    return {
                        "success": False,
                        "error": message
                    }

                # 显示优化后的方案（仅元数据信息）
                await event.send(event.plain_result(f"优化后的插件方案：\n\n{self._build_preview_text(metadata, '', '')}"))
                await self._send_doc_and_config_images(event, metadata, markdown_doc, config_schema)
            except Exception as e:
                self.logger.error(f"优化插件方案失败: {str(e)}")
                return {
                    "success": False,
                    "error": f"优化插件方案失败：{str(e)}"
                }
        
        # 继续执行生成流程的剩余步骤
        try:
            # 设置生成状态
            self.generation_status["is_generating"] = True
            self.generation_status["start_time"] = format_time(time.time())
            
            plugin_name = sanitize_plugin_name(metadata.get("name", "astrbot_plugin_generated"))
            if not plugin_name.startswith("astrbot_plugin_"):
                plugin_name = f"astrbot_plugin_{plugin_name}"
            metadata["name"] = plugin_name
            self._update_status(4, plugin_name)
            

            # 步骤4：生成插件代码
            await event.send(event.plain_result(self._build_step_message()))
            self.logger.info(f"开始生成插件代码: {plugin_name}")
            try:
                code = await self.llm_handler.generate_plugin_code(metadata, markdown_doc, config_schema)
            except Exception as code_err:
                error_msg = f"生成插件代码失败：{str(code_err)}"
                self.logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }
            
            # 步骤5：代码审查与修复
            self._update_status(5, plugin_name)
            await event.send(event.plain_result(self._build_step_message()))
            self.logger.info(f"开始代码审查: {plugin_name}")

            satisfaction_threshold = self.config.get("satisfaction_threshold", 80)
            strict_review = self.config.get("strict_review", True)
            max_retries = self.config.get("max_retries", 3)
            unlimited_retry = max_retries == -1

            try:
                code, review_result, review_passed = await self._ensure_code_review_passed(
                    code=code,
                    metadata=metadata,
                    markdown_doc=markdown_doc,
                    event=event,
                    satisfaction_threshold=satisfaction_threshold,
                    strict_review=strict_review,
                    max_retries=max_retries,
                    unlimited_retry=unlimited_retry,
                )
            except Exception as review_err:
                self.logger.error(f"代码审查流程失败: {str(review_err)}")
                return {
                    "success": False,
                    "error": f"代码审查流程失败：{str(review_err)}"
                }

            if not review_passed:
                reason = review_result.get("reason", "代码审查未通过")
                return {
                    "success": False,
                    "error": f"代码审查未通过：{reason}"
                }

            await event.send(event.plain_result(f"代码审查通过，满意度得分：{review_result['satisfaction_score']}分"))

            # 步骤6：生成最终插件并安装
            self._update_status(6, plugin_name)
            await event.send(event.plain_result(self._build_step_message()))

            result = {
                "success": True,
                "plugin_name": plugin_name,
                "plugin_path": "",
                "satisfaction_score": review_result["satisfaction_score"],
                "installed": False
            }

            api_enabled = bool(self.installer and self.config.get("api_password_md5"))
            install_retry_count = 0
            last_install_error = ""
            last_install_issues: List[str] = []
            api_install_success = False

            if api_enabled and install_method in ("api", "auto"):
                while True:
                    await event.send(event.plain_result("正在通过API安装插件..."))
                    api_outcome = await self._install_via_api(plugin_name, metadata, code, markdown_doc, config_schema)

                    if api_outcome.get("success"):
                        api_install_success = True
                        result["installed"] = True
                        result["install_success"] = True
                        result["install_method"] = "api"
                        await event.send(event.plain_result("✅ 插件已通过API安装"))
                        status_check_error = api_outcome.get("status_check_error")
                        if status_check_error:
                            await event.send(event.plain_result(f"⚠️ 插件安装成功，但无法获取日志信息：{status_check_error}"))
                        warnings = api_outcome.get("warnings") or []
                        if warnings:
                            preview = "\n".join(warnings[:3])
                            await event.send(event.plain_result(f"⚠️ 插件安装完成，但存在警告日志：\n{preview}"))
                        break

                    last_install_error = api_outcome.get("error") or "插件通过API安装失败"
                    last_install_issues = api_outcome.get("issues") or [last_install_error]
                    heading = "⚠️ 插件通过API安装失败：" if not api_outcome.get("post_install_errors") else "⚠️ 插件安装后检测到错误："
                    preview = "\n".join(last_install_issues[:5])
                    details = preview or last_install_error
                    if details:
                        await event.send(event.plain_result(f"{heading}\n{details}"))
                    else:
                        await event.send(event.plain_result(heading))
                    cleanup_info = await self._cleanup_plugin_installation(plugin_name)
                    cleanup_api = cleanup_info.get("api")
                    if cleanup_api and not cleanup_api.get("success"):
                        api_cleanup_msg = cleanup_api.get("error") or cleanup_api.get("message")
                        if api_cleanup_msg:
                            await event.send(event.plain_result(f"⚠️ 通过API删除插件失败：{api_cleanup_msg}"))
                    cleanup_file = cleanup_info.get("file")
                    if cleanup_file and cleanup_file.get("success") is False:
                        await event.send(event.plain_result(f"⚠️ 删除插件目录失败：{cleanup_file.get('error')}"))

                    if not unlimited_retry and install_retry_count >= max_retries:
                        break

                    install_retry_count += 1
                    await event.send(event.plain_result(f"正在回退到审查步骤并尝试自动修复（第{install_retry_count}次重试）..."))

                    suggestions = last_install_issues.copy()
                    suggestions.append("请根据这些安装错误修复插件代码并确保插件能够成功加载。")
                    code = await self.llm_handler.fix_plugin_code(code, last_install_issues, suggestions)
                    code, review_result, review_passed = await self._ensure_code_review_passed(
                        code=code,
                        metadata=metadata,
                        markdown_doc=markdown_doc,
                        event=event,
                        satisfaction_threshold=satisfaction_threshold,
                        strict_review=strict_review,
                        max_retries=max_retries,
                        unlimited_retry=unlimited_retry,
                    )
                    if not review_passed:
                        reason = review_result.get("reason", "代码审查未通过")
                        return {
                            "success": False,
                            "error": f"代码审查未通过：{reason}"
                        }
                    result["satisfaction_score"] = review_result["satisfaction_score"]
                    await event.send(event.plain_result(f"修复后的代码审查通过，满意度得分：{review_result['satisfaction_score']}分"))

                if not api_install_success and install_method == "api":
                    error_message = last_install_error or "插件通过API安装失败"
                    if not unlimited_retry and install_retry_count >= max_retries:
                        await event.send(event.plain_result("❌ 插件API安装失败，已达到配置的最大重试次数。"))
                    return {
                        "success": False,
                        "error": f"插件API安装失败：{error_message}"
                    }

            if api_install_success:
                return result

            if last_install_error:
                result["install_error"] = last_install_error

            if api_enabled and install_method == "auto":
                if not unlimited_retry and install_retry_count >= max_retries:
                    await event.send(event.plain_result("⚠️ API 安装未成功且已达到最大重试次数，改为文件方式安装，请稍候并在完成后重启AstrBot以加载插件。"))
                else:
                    await event.send(event.plain_result("⚠️ API 安装未成功，改为文件方式安装，请稍候并在完成后重启AstrBot以加载插件。"))

            file_outcome = await self._install_via_file(plugin_name, metadata, code, markdown_doc, config_schema)
            if not file_outcome.get("success"):
                error_message = file_outcome.get("error", "插件文件安装失败")
                return {
                    "success": False,
                    "error": f"插件文件安装失败：{error_message}"
                }

            plugin_path = file_outcome.get("plugin_path", "")
            result["plugin_path"] = plugin_path
            result["installed"] = True
            result["install_success"] = True
            result["install_method"] = "file"
            await event.send(event.plain_result(f"插件已在本地创建: {plugin_path}\n请手动重启AstrBot以加载插件"))
            
            return result
            
        except Exception as e:
            self.logger.error(f"插件生成流程失败：{str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        finally:
            # 恢复API密码配置（如有临时修改）
            try:
                if restore_api_pwd:
                    self.config["api_password_md5"] = saved_api_pwd
            except Exception:
                pass
            self.generation_status["is_generating"] = False
            self.generation_status["current_step"] = 0
            self.generation_status["progress_percentage"] = 0
            self.generation_status["plugin_name"] = ""
        
    async def _review_code_with_retry(self, code: str, metadata: Dict[str, Any],
                                    markdown: str,
                                    max_retries: int = 3) -> Dict[str, Any]:
        '''带重试的代码审查
        
        Args:
            code: 插件代码
            metadata: 插件元数据
            markdown: 插件Markdown文档
            max_retries: 最大重试次数
            
        Returns:
            Dict[str, Any]: 审查结果
        '''
        for attempt in range(max_retries):
            try:
                return await self.llm_handler.review_plugin_code(code, metadata, markdown)
            except Exception as e:
                self.logger.error(f"代码审查失败（尝试 {attempt + 1}/{max_retries}）：{str(e)}")
                if attempt == max_retries - 1:
                    # 返回一个默认的失败结果
                    return {
                        "approved": False,
                        "satisfaction_score": 0,
                        "reason": f"代码审查失败：{str(e)}",
                        "issues": ["代码审查失败"],
                        "suggestions": ["请检查代码并重试"]
                    }
                    
        return {
            "approved": False,
            "satisfaction_score": 0,
            "reason": "代码审查失败",
            "issues": ["代码审查失败"],
            "suggestions": ["请检查代码并重试"]
        }
        
    async def _create_plugin_files(self, plugin_name: str, metadata: Dict[str, Any], code: str, markdown: str, config_schema: str = "", base_dir: Optional[str] = None) -> str:
        '''创建插件文件
        
        Args:
            plugin_name: 插件名称
            metadata: 插件元数据
            code: 插件代码
            markdown: Markdown文档
            config_schema: 配置文件内容
            base_dir: 基础目录路径（可选）。如果提供，则在此目录下创建，否则在plugins目录创建
            
        Returns:
            str: 插件路径
        '''
        # 获取插件目录
        if base_dir:
            plugins_dir = base_dir
        else:
            plugins_dir = self.directory_detector.get_plugins_directory()
            if not plugins_dir:
                raise ValueError("无法获取插件目录")
            
        # 创建插件目录
        plugin_dir = create_plugin_directory(plugins_dir, plugin_name)
        
        # 创建main.py
        main_py_path = os.path.join(plugin_dir, "main.py")
        with open(main_py_path, 'w', encoding='utf-8') as f:
            f.write(code)
            
        # 创建metadata.yaml
        metadata_yaml_path = os.path.join(plugin_dir, "metadata.yaml")
        metadata_content = metadata.get('metadata', {}) if isinstance(metadata.get('metadata'), dict) else {}
        yaml_content = f"name: {metadata.get('name', plugin_name)}\n"
        yaml_content += f"author: {metadata.get('author', 'CodeMage')}\n"
        yaml_content += f"description: {metadata.get('description', '由CodeMage生成的插件')}\n"
        yaml_content += f"version: {metadata.get('version', '1.0.0')}\n"
        yaml_content += f"repo: {metadata_content.get('repo_url', '')}\n"
        with open(metadata_yaml_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
            
        # 创建requirements.txt（如果有依赖）
        dependencies = metadata_content.get('dependencies', []) if isinstance(metadata_content, dict) else []
        if dependencies and self.config.get('allow_dependencies', True):
            requirements_path = os.path.join(plugin_dir, "requirements.txt")
            with open(requirements_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(dependencies))
            self.logger.info(f"已创建requirements.txt文件，包含{len(dependencies)}个依赖")
        else:
            self.logger.info("未创建requirements.txt文件（无依赖或依赖生成被禁用）")
                
        # 创建README.md
        readme_path = os.path.join(plugin_dir, "README.md")
        readme_content = markdown if markdown.strip() else f"# {metadata.get('name', plugin_name)}\n\n由CodeMage生成的插件"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        # 创建_conf_schema.json（如果有配置）
        if config_schema and config_schema.strip():
            config_path = os.path.join(plugin_dir, "_conf_schema.json")
            try:
                parsed_config = json.loads(config_schema)
                formatted_config = json.dumps(parsed_config, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                formatted_config = config_schema
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(formatted_config)
            self.logger.info(f"已创建_conf_schema.json配置文件")
            
        return plugin_dir
    
    async def modify_plugin_content(self, modification_type: str, feedback: str = "", event: Optional[AstrMessageEvent] = None) -> Dict[str, Any]:
        '''修改插件内容
        
        Args:
            modification_type: 修改类型(配置文件/文档/元数据/全部)
            feedback: 用户反馈
            
        Returns:
            Dict[str, Any]: 修改结果
        '''
        if not self.pending_generation["active"]:
            try:
                self._load_pending_state()
            except Exception:
                pass
        if not self.pending_generation["active"]:
            return {
                "success": False,
                "error": "没有待确认的插件生成任务"
            }
            
        # 获取当前任务信息
        metadata = self.pending_generation["metadata"]
        markdown_doc = self.pending_generation["markdown"]
        config_schema = self.pending_generation.get("config_schema", "")
        description = self.pending_generation["description"]
        if event is None:
            event = self.pending_generation["event"]
        else:
            self.pending_generation["event"] = event
        
        try:
            # 根据修改类型进行不同的处理
            if modification_type == "配置文件":
                await event.send(event.plain_result("正在重新生成配置文件..."))
                self.logger.info(f"重新生成配置文件，用户反馈: {feedback}")
                config_schema = await self.llm_handler.modify_config_schema(config_schema, metadata, feedback)
                config_schema = self._normalize_config_schema(config_schema)
                await event.send(event.plain_result("配置文件已重新生成"))
                
            elif modification_type == "文档":
                await event.send(event.plain_result("正在重新生成文档..."))
                self.logger.info(f"重新生成文档，用户反馈: {feedback}")
                markdown_doc = await self.llm_handler.modify_markdown_document(markdown_doc, metadata, feedback)
                metadata["markdown"] = markdown_doc
                await event.send(event.plain_result("文档已重新生成"))
                
            elif modification_type == "元数据":
                await event.send(event.plain_result("正在重新生成元数据..."))
                self.logger.info(f"重新生成元数据，用户反馈: {feedback}")
                metadata = await self.llm_handler.modify_plugin_metadata(metadata, feedback)
                metadata.setdefault("metadata", {})
                metadata.setdefault("commands", [])
                plugin_name = sanitize_plugin_name(metadata.get("name", "astrbot_plugin_generated"))
                if not plugin_name.startswith("astrbot_plugin_"):
                    plugin_name = f"astrbot_plugin_{plugin_name}"
                metadata["name"] = plugin_name
                
                # 检查插件是否已存在
                if self.directory_detector.check_plugin_exists(plugin_name):
                    return {
                        "success": False,
                        "error": f"插件 '{plugin_name}' 已存在"
                    }
                await event.send(event.plain_result("元数据已重新生成"))
                
            elif modification_type == "全部" or not modification_type:
                await event.send(event.plain_result("正在重新生成整个插件方案..."))
                self.logger.info(f"重新生成整个方案，用户反馈: {feedback}")
                
                # 重新生成元数据
                combined_description = description
                if feedback:
                    combined_description = f"{description}\n\n用户修改要求：{feedback}"
                step_by_step = self.config.get("step_by_step", True)
                if step_by_step:
                    metadata = await self.llm_handler.generate_metadata_structure(combined_description)
                    metadata.setdefault("metadata", {})
                    metadata.setdefault("commands", [])
                    markdown_doc = await self.llm_handler.generate_markdown_document(metadata, combined_description)
                else:
                    metadata = await self.llm_handler.generate_plugin_metadata(combined_description)
                    metadata.setdefault("metadata", {})
                    metadata.setdefault("commands", [])
                    markdown_doc = metadata.get("markdown", "")
                plugin_name = sanitize_plugin_name(metadata.get("name", "astrbot_plugin_generated"))
                if not plugin_name.startswith("astrbot_plugin_"):
                    plugin_name = f"astrbot_plugin_{plugin_name}"
                metadata["name"] = plugin_name
                metadata["markdown"] = markdown_doc
                
                # 检查插件是否已存在
                if self.directory_detector.check_plugin_exists(plugin_name):
                    return {
                        "success": False,
                        "error": f"插件 '{plugin_name}' 已存在"
                    }
                
                # 重新生成配置
                config_schema = await self.llm_handler.generate_config_schema(metadata, combined_description)
                config_schema = self._normalize_config_schema(config_schema)
                
                await event.send(event.plain_result("整个插件方案已重新生成"))
            else:
                return {
                    "success": False,
                    "error": f"不支持的修改类型：{modification_type}"
                }
            
            # 更新待确认任务
            self.pending_generation.update({
                "metadata": metadata,
                "markdown": markdown_doc,
                "config_schema": config_schema,
                "awaiting_confirmation": True
            })
            # 持久化更新后的任务状态
            try:
                self._save_pending_state()
            except Exception:
                pass
            
            # 显示更新后的方案（仅元数据信息），并以图片发送文档与配置
            await event.send(event.plain_result(f"更新后的插件方案：\n\n{self._build_preview_text(metadata, '', '')}"))
            await self._send_doc_and_config_images(event, metadata, markdown_doc, config_schema)
            await event.send(event.plain_result("请使用指令 '/同意生成' 确认生成，或 '/拒绝生成' 取消生成，或继续使用 '/插件内容修改' 进行修改。"))
            
            return {
                "success": True,
                "message": f"{modification_type}已重新生成"
            }
            
        except Exception as e:
            self.logger.error(f"修改插件内容失败: {str(e)}")
            return {
                "success": False,
                "error": f"修改插件内容失败：{str(e)}"
            }