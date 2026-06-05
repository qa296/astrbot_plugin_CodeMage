"""
CodeMage插件安装器模块
负责通过AstrBot API安装生成的插件
"""

import os
import tempfile
import zipfile
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path
from astrbot.core.utils.io import remove_dir


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
        self.max_retries = config.get("max_retries", 3)
        self._install_timestamp: float | None = None

    def set_install_timestamp(self, timestamp: float | None = None):
        """设置安装参考时间戳，用于时间窗日志过滤

        Args:
            timestamp: Unix时间戳，不传则使用当前时间
        """
        import time

        self._install_timestamp = timestamp or time.time()

    async def login(self) -> bool:
        """登录AstrBot并获取token

        Returns:
            bool: 是否登录成功
        """
        try:
            import aiohttp

            url = f"{self.astrbot_url}/api/auth/login"
            payload = {"username": self.username, "password": self.password_md5}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()

                    if result.get("status") == "ok":
                        self.token = result.get("data", {}).get("token")
                        self.logger.info("✅ AstrBot API登录成功")
                        return True
                    else:
                        self.logger.error(
                            f"❌ AstrBot API登录失败: {result.get('message')}"
                        )
                        return False

        except Exception as e:
            self.logger.error(f"❌ AstrBot API登录请求失败: {str(e)}")
            return False

    async def create_plugin_zip(self, plugin_dir: str) -> str | None:
        """将插件目录打包成zip文件

        Args:
            plugin_dir: 插件目录路径

        Returns:
            Optional[str]: zip文件路径，失败返回None
        """
        try:
            # 创建临时zip文件
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
                zip_path = tmp_file.name

            # 打包插件目录
            plugin_root_name = os.path.basename(os.path.normpath(plugin_dir))
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
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
                        relative_path = os.path.relpath(file_path, plugin_dir).replace(
                            os.sep, "/"
                        )
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

    async def install_plugin(
        self, zip_path: str, plugin_name: str | None = None
    ) -> dict[str, Any]:
        """通过API安装插件

        Args:
            zip_path: 插件zip文件路径
            plugin_name: 可选，期望的插件名称（用于避免后端根据随机上传文件名创建随机目录）

        Returns:
            Dict[str, Any]: 安装结果
        """
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "API登录失败"}

        try:
            import aiohttp

            url = f"{self.astrbot_url}/api/plugin/install-upload"

            if not os.path.exists(zip_path):
                return {"success": False, "error": f"文件不存在: {zip_path}"}

            self.logger.info(f"正在通过API安装插件: {zip_path}")

            async with aiohttp.ClientSession() as session:
                with open(zip_path, "rb") as f:
                    data = aiohttp.FormData()
                    # 一些后端会使用上传文件名作为插件目录名，这里显式指定一个稳定的名称
                    inferred_name = None
                    if not plugin_name:
                        try:
                            with zipfile.ZipFile(zip_path, "r") as zf:
                                top_levels = set()
                                for n in zf.namelist():
                                    if not n:
                                        continue
                                    seg = n.split("/")[0].strip()
                                    if seg:
                                        top_levels.add(seg)
                                if len(top_levels) == 1:
                                    inferred_name = list(top_levels)[0]
                        except Exception:
                            inferred_name = None
                    final_name = plugin_name or inferred_name
                    upload_filename = (
                        f"{final_name}.zip"
                        if final_name
                        else os.path.basename(zip_path)
                    )
                    data.add_field(
                        "file",
                        f,
                        filename=upload_filename,
                        content_type="application/zip",
                    )

                    headers = {"Authorization": f"Bearer {self.token}"}

                    async with session.post(url, data=data, headers=headers) as resp:
                        result = await resp.json()

                        if result.get("status") == "ok":
                            self.logger.info(
                                f"✅ 插件安装成功: {result.get('message')}"
                            )
                            return {
                                "success": True,
                                "plugin_name": result.get("data", {}).get(
                                    "name", "Unknown"
                                ),
                                "plugin_repo": result.get("data", {}).get(
                                    "repo", "N/A"
                                ),
                            }
                        else:
                            self.logger.error(
                                f"❌ 插件安装失败: {result.get('message')}"
                            )
                            return {
                                "success": False,
                                "error": result.get("message", "Unknown error"),
                            }

        except Exception as e:
            self.logger.error(f"❌ 插件安装请求失败: {str(e)}")
            return {"success": False, "error": str(e)}

    async def uninstall_plugin_api(self, plugin_name: str) -> dict[str, Any]:
        """通过API卸载插件

        Args:
            plugin_name: 插件名称

        Returns:
            Dict[str, Any]: 卸载结果
        """
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "API登录失败"}

        try:
            import aiohttp

            url = f"{self.astrbot_url}/api/plugin/uninstall"
            payload = {"name": plugin_name}

            headers = {"Authorization": f"Bearer {self.token}"}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    result = await resp.json()

                    if result.get("status") == "ok":
                        self.logger.info(f"✅ 插件卸载成功: {plugin_name}")
                        return {"success": True, "message": result.get("message")}
                    else:
                        self.logger.error(f"❌ 插件卸载失败: {result.get('message')}")
                        return {
                            "success": False,
                            "error": result.get("message", "Unknown error"),
                        }

        except Exception as e:
            self.logger.error(f"❌ 插件卸载请求失败: {str(e)}")
            return {"success": False, "error": str(e)}

    async def uninstall_plugin_file(self, plugin_name: str) -> dict[str, Any]:
        """通过文件系统删除插件

        Args:
            plugin_name: 插件名称

        Returns:
            Dict[str, Any]: 删除结果
        """
        try:
            # 获取插件目录路径
            plugins_dir = get_astrbot_plugin_path()
            plugin_path = os.path.join(plugins_dir, plugin_name)

            if not os.path.exists(plugin_path):
                return {"success": False, "error": f"插件目录不存在: {plugin_path}"}

            remove_dir(plugin_path)
            self.logger.info(f"✅ 插件文件删除成功: {plugin_path}")
            return {"success": True, "message": f"插件文件已删除: {plugin_path}"}

        except Exception as e:
            self.logger.error(f"❌ 插件文件删除失败: {str(e)}")
            return {"success": False, "error": str(e)}

    async def delete_plugin_folder(self, plugin_name: str) -> dict[str, Any]:
        """删除插件文件夹（混合策略）

        Args:
            plugin_name: 插件名称

        Returns:
            Dict[str, Any]: 删除结果
        """
        # 1. 尝试API卸载
        api_result = await self.uninstall_plugin_api(plugin_name)
        if api_result.get("success"):
            return api_result

        self.logger.warning(f"API卸载失败，尝试文件删除: {api_result.get('error')}")

        # 2. 尝试文件删除
        file_result = await self.uninstall_plugin_file(plugin_name)
        return file_result

    async def _check_plugin_loaded_via_api(self, plugin_name: str) -> dict:
        """通过 AstrBot API 检查插件是否已加载

        Args:
            plugin_name: 插件名称

        Returns:
            dict: {
                "success": bool,      # API调用是否成功
                "loaded": bool,       # 插件是否已加载
                "activated": bool,    # 插件是否已激活（仅在loaded=True时有效）
                "error": str,         # 错误信息（仅在loaded=False时）
            }
        """
        if not self.token:
            if not await self.login():
                return {"success": False, "error": "API登录失败"}

        try:
            import aiohttp

            headers = {"Authorization": f"Bearer {self.token}"}

            # 1. 从已加载插件列表检查
            async with aiohttp.ClientSession() as session:
                url = f"{self.astrbot_url}/api/plugin/get?name={plugin_name}"
                async with session.get(url, headers=headers) as resp:
                    result = await resp.json()
                    if result.get("status") == "ok":
                        plugins = result.get("data", [])
                        if plugins:
                            p = plugins[0]
                            return {
                                "success": True,
                                "loaded": True,
                                "activated": p.get("activated", True),
                                "version": p.get("version", ""),
                                "author": p.get("author", ""),
                                "desc": p.get("desc", ""),
                            }

            # 2. 不在已加载列表 → 检查失败插件列表
            async with aiohttp.ClientSession() as session:
                url = f"{self.astrbot_url}/api/plugin/source/get-failed-plugins"
                async with session.get(url, headers=headers) as resp:
                    result = await resp.json()
                    if result.get("status") == "ok":
                        failed_dict = result.get("data", {})
                        for dir_name, err_info in failed_dict.items():
                            if plugin_name in dir_name or (
                                isinstance(err_info, dict)
                                and plugin_name in str(err_info.get("name", ""))
                            ):
                                err_msg = (
                                    err_info.get("error", str(err_info))
                                    if isinstance(err_info, dict)
                                    else str(err_info)
                                )
                                return {
                                    "success": True,
                                    "loaded": False,
                                    "error": err_msg,
                                }

            # 3. 两处都找不到 → 未加载
            return {
                "success": True,
                "loaded": False,
                "error": f"插件 {plugin_name} 未在 AstrBot 中找到，可能安装后未能正确加载。",
            }

        except Exception as e:
            self.logger.error(f"检查插件加载状态失败: {str(e)}")
            return {"success": False, "error": str(e)}

    async def check_plugin_install_status(self, plugin_name: str) -> dict[str, Any]:
        """检查插件安装状态和运行时错误

        两层检测策略：
        1. 优先使用 API 确认插件是否加载成功（权威检测）
        2. 使用时间窗过滤的日志检测运行时错误

        Args:
            plugin_name: 插件名称

        Returns:
            Dict[str, Any]: 插件状态信息
        """
        # Layer 1: 通过插件列表 API 确认加载状态
        load_check = await self._check_plugin_loaded_via_api(plugin_name)
        if not load_check.get("success"):
            return {
                "success": False,
                "error": load_check.get("error", "API登录失败"),
            }

        result: dict[str, Any] = {
            "success": True,
            "has_errors": False,
            "has_warnings": False,
            "error_logs": [],
            "warning_logs": [],
        }

        if not load_check.get("loaded"):
            result["has_errors"] = True
            result["error_logs"] = [
                f"插件 {plugin_name} 加载失败: {load_check.get('error', '未知错误')}"
            ]
            self.logger.warning(f"插件 {plugin_name} 未加载: {load_check.get('error')}")
            return result

        result["loaded"] = True
        result["activated"] = load_check.get("activated", True)

        if not load_check.get("activated", True):
            self.logger.warning(f"插件 {plugin_name} 已加载但未激活")

        # Layer 2: 时间窗日志检测运行时错误
        if not self._install_timestamp:
            return result

        try:
            import asyncio

            import aiohttp

            await asyncio.sleep(2)

            headers = {"Authorization": f"Bearer {self.token}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.astrbot_url}/api/log-history", headers=headers
                ) as resp:
                    api_result = await resp.json()
                    if api_result.get("status") != "ok":
                        return result

                    logs = api_result.get("data", {}).get("logs", [])
                    error_logs = []
                    warning_logs = []

                    for entry in logs:
                        if not isinstance(entry, dict):
                            continue

                        log_time = entry.get("time", 0)
                        if log_time < self._install_timestamp:
                            continue

                        level = entry.get("level", "").upper()
                        data = entry.get("data", "")

                        if isinstance(data, dict):
                            message = data.get("message", "")
                        else:
                            message = str(data)

                        # 精确插件名匹配
                        # 插件名如 astrbot_plugin_xxx 足够长且唯一，配以时间窗过滤即可精准匹配
                        plugin_matches = plugin_name in message

                        if not plugin_matches:
                            continue

                        if level == "ERROR":
                            error_logs.append(message)
                        elif level == "WARNING":
                            warning_logs.append(message)

                    result["has_errors"] = len(error_logs) > 0
                    result["has_warnings"] = len(warning_logs) > 0
                    result["error_logs"] = error_logs[:5]
                    result["warning_logs"] = warning_logs[:5]

        except Exception as e:
            self.logger.warning(f"日志检查失败（非关键）: {str(e)}")

        return result
