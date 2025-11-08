"""
CodeMage插件安装器模块
负责通过AstrBot API安装生成的插件
"""

import os
import zipfile
import tempfile
import shutil
from typing import Dict, Any, Optional
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from .directory_detector import DirectoryDetector


class PluginInstaller:
    """插件安装器类"""
    
    def __init__(self, config: AstrBotConfig):
        self.config = config
        self.logger = logger
        self.astrbot_url = config.get("astrbot_url", "http://localhost:6185")
        self.username = config.get("api_username", "astrbot")
        # 配置文件中存储的是MD5加密后的密码
        self.password_md5 = config.get("api_password_md5", "")
        self.token = None
        
    async def login(self) -> bool:
        """登录AstrBot并获取token
        
        Returns:
            bool: 是否登录成功
        """
        try:
            import aiohttp
            
            url = f"{self.astrbot_url}/api/auth/login"
            payload = {
                "username": self.username,
                "password": self.password_md5
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()
                    
                    if result.get("status") == "ok":
                        self.token = result.get("data", {}).get("token")
                        self.logger.info(f"✅ AstrBot API登录成功")
                        return True
                    else:
                        self.logger.error(f"❌ AstrBot API登录失败: {result.get('message')}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"❌ AstrBot API登录请求失败: {str(e)}")
            return False
            
    async def create_plugin_zip(self, plugin_dir: str) -> Optional[str]:
        """将插件目录打包成zip文件
        
        Args:
            plugin_dir: 插件目录路径
            
        Returns:
            Optional[str]: zip文件路径，失败返回None
        """
        try:
            # 创建临时zip文件
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                zip_path = tmp_file.name
                
            # 打包插件目录
            plugin_root_name = os.path.basename(os.path.normpath(plugin_dir))
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 显式写入顶层插件目录，确保ZIP中存在目录项，避免某些安装器误判为文件路径
                if plugin_root_name:
                    try:
                        dir_info = zipfile.ZipInfo(f"{plugin_root_name}/")
                        # 设置目录属性（在大多数解压器上不是必须，但更稳妥）
                        dir_info.create_system = 3  # 标记为Unix以使 external_attr 生效
                        dir_info.external_attr = 0o40775 << 16  # drwxrwxr-x
                        zipf.writestr(dir_info, b"")
                    except Exception:
                        # 兼容性兜底：至少写入一个以/结尾的空目录名
                        zipf.writestr(f"{plugin_root_name}/", b"")
                
                for root, dirs, files in os.walk(plugin_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # AstrBot 需要 zip 顶层保留插件目录（plugin_name/main.py 等）
                        relative_path = os.path.relpath(file_path, plugin_dir).replace(os.sep, '/')
                        if plugin_root_name:
                            arcname = f"{plugin_root_name}/{relative_path}"
                        else:
                            arcname = relative_path
                        zipf.write(file_path, arcname)
                        
            structure_hint = f"{plugin_root_name}/..." if plugin_root_name else "根目录"
            self.logger.info(f"插件打包成功: {zip_path}，ZIP结构: {structure_hint}")
            return zip_path
            
        except Exception as e:
            self.logger.error(f"插件打包失败: {str(e)}")
            return None
            
    async def install_plugin(self, zip_path: str, plugin_name: Optional[str] = None) -> Dict[str, Any]:
        """通过API安装插件
        
        Args:
            zip_path: 插件zip文件路径
            plugin_name: 可选，期望的插件名称（用于避免后端根据随机上传文件名创建随机目录）
            
        Returns:
            Dict[str, Any]: 安装结果
        """
        if not self.token:
            if not await self.login():
                return {
                    "success": False,
                    "error": "API登录失败"
                }
                
        try:
            import aiohttp
            
            url = f"{self.astrbot_url}/api/plugin/install-upload"
            
            if not os.path.exists(zip_path):
                return {
                    "success": False,
                    "error": f"文件不存在: {zip_path}"
                }
                
            self.logger.info(f"正在通过API安装插件: {zip_path}")
            
            async with aiohttp.ClientSession() as session:
                with open(zip_path, 'rb') as f:
                    data = aiohttp.FormData()
                    # 一些后端会使用上传文件名作为插件目录名，这里显式指定一个稳定的名称
                    inferred_name = None
                    if not plugin_name:
                        try:
                            with zipfile.ZipFile(zip_path, 'r') as zf:
                                top_levels = set()
                                for n in zf.namelist():
                                    if not n:
                                        continue
                                    seg = n.split('/')[0].strip()
                                    if seg:
                                        top_levels.add(seg)
                                if len(top_levels) == 1:
                                    inferred_name = list(top_levels)[0]
                        except Exception:
                            inferred_name = None
                    final_name = plugin_name or inferred_name
                    upload_filename = f"{final_name}.zip" if final_name else os.path.basename(zip_path)
                    data.add_field('file', 
                                 f,
                                 filename=upload_filename,
                                 content_type='application/zip')
                    
                    headers = {
                        "Authorization": f"Bearer {self.token}"
                    }
                    
                    async with session.post(url, data=data, headers=headers) as resp:
                        result = await resp.json()
                        
                        if result.get("status") == "ok":
                            self.logger.info(f"✅ 插件安装成功: {result.get('message')}")
                            return {
                                "success": True,
                                "plugin_name": result.get('data', {}).get('name', 'Unknown'),
                                "plugin_repo": result.get('data', {}).get('repo', 'N/A')
                            }
                        else:
                            self.logger.error(f"❌ 插件安装失败: {result.get('message')}")
                            return {
                                "success": False,
                                "error": result.get('message', 'Unknown error')
                            }
                            
        except Exception as e:
            self.logger.error(f"❌ 插件安装请求失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
            
    async def check_plugin_install_status(self, plugin_name: str) -> Dict[str, Any]:
        """检查插件安装状态和错误日志
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            Dict[str, Any]: 插件状态信息
        """
        if not self.token:
            if not await self.login():
                return {
                    "success": False,
                    "error": "API登录失败"
                }
                
        try:
            import aiohttp
            import asyncio
            
            # 等待插件加载
            await asyncio.sleep(3)
            
            # 获取日志历史
            url = f"{self.astrbot_url}/api/log-history?limit=200"
            headers = {
                "Authorization": f"Bearer {self.token}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    result = await resp.json()
                    
                    if result.get("status") == "ok":
                        logs = result.get('data', {}).get('logs', [])
                        
                        # 查找插件相关的错误和警告
                        error_logs = []
                        warning_logs = []
                        
                        for log_entry in logs:
                            if not isinstance(log_entry, dict):
                                continue
                                
                            data = log_entry.get('data', {})
                            if isinstance(data, str):
                                message = data
                                level = log_entry.get('level', '').upper()
                                module = ''
                            else:
                                level = data.get('level', log_entry.get('level', '')).upper()
                                message = data.get('message', '')
                                module = data.get('module', data.get('name', ''))
                                
                            # 检查是否与插件相关
                            is_plugin_related = (
                                'plugin' in module.lower() or 
                                'star' in module.lower() or
                                plugin_name.lower() in message.lower() or
                                plugin_name.lower() in module.lower()
                            )
                            
                            if is_plugin_related:
                                if level in ['ERROR', 'ERRO'] or 'error' in message.lower() or '失败' in message:
                                    error_logs.append(message)
                                elif level == 'WARN' or 'warn' in message.lower():
                                    warning_logs.append(message)
                                    
                        return {
                            "success": True,
                            "has_errors": len(error_logs) > 0,
                            "has_warnings": len(warning_logs) > 0,
                            "error_logs": error_logs[:5],  # 最多返回5条
                            "warning_logs": warning_logs[:5]
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"获取日志失败: {result.get('message')}"
                        }
                        
        except Exception as e:
            self.logger.error(f"检查插件状态失败: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def uninstall_plugin_api(self, plugin_name: str) -> Dict[str, Any]:
        """通过 API 卸载/删除已安装的插件
        
        会尝试多种可能的端点，适配不同版本的 AstrBot 后端。
        """
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "API登录失败"}
        try:
            import aiohttp
            headers = {"Authorization": f"Bearer {self.token}"}
            candidates = [
                f"{self.astrbot_url}/api/plugin/uninstall",
                f"{self.astrbot_url}/api/plugin/delete",
                f"{self.astrbot_url}/api/plugin/remove",
            ]
            last_error = None
            async with aiohttp.ClientSession() as session:
                for url in candidates:
                    try:
                        async with session.post(url, json={"name": plugin_name}, headers=headers) as resp:
                            data = await resp.json()
                            if data.get("status") == "ok":
                                self.logger.info(f"✅ 通过API卸载插件成功: {plugin_name}")
                                return {"success": True}
                            else:
                                last_error = data.get("message") or f"HTTP {resp.status}"
                    except Exception as e:
                        last_error = str(e)
                        continue
            return {"success": False, "error": last_error or "未知的API卸载错误"}
        except Exception as e:
            self.logger.error(f"卸载插件API请求失败: {str(e)}")
            return {"success": False, "error": str(e)}

    async def delete_plugin_files(self, plugin_name: str) -> Dict[str, Any]:
        """从本地文件系统删除插件目录"""
        try:
            detector = DirectoryDetector()
            plugin_path = detector.get_plugin_path(plugin_name)
            if not plugin_path:
                return {"success": True, "skipped": True, "message": "未发现本地插件目录"}
            if os.path.exists(plugin_path):
                try:
                    shutil.rmtree(plugin_path)
                    self.logger.info(f"🧹 已删除本地插件目录: {plugin_path}")
                    return {"success": True, "path": plugin_path}
                except Exception as e:
                    self.logger.error(f"删除本地插件目录失败: {plugin_path}, 错误: {e}")
                    return {"success": False, "error": str(e), "path": plugin_path}
            return {"success": True, "skipped": True, "message": "插件目录不存在"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cleanup_plugin(self, plugin_name: str) -> Dict[str, Any]:
        """混合清理：优先通过 API 卸载，失败后尝试删除本地目录"""
        api_res = await self.uninstall_plugin_api(plugin_name)
        file_res = {"success": False}
        # API 卸载失败或不确定时，尝试文件删除
        if not api_res.get("success"):
            file_res = await self.delete_plugin_files(plugin_name)
        else:
            # 即使 API 成功，也尝试清理本地残留（不影响结果）
            try:
                await self.delete_plugin_files(plugin_name)
            except Exception:
                pass
        return {
            "success": bool(api_res.get("success") or file_res.get("success")),
            "api_deleted": api_res.get("success", False),
            "file_deleted": file_res.get("success", False)
        }
