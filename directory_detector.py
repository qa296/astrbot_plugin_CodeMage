"""
CodeMage目录检测器模块
负责检测AstrBot安装目录和插件目录
"""

import os
from pathlib import Path
from typing import Any


class DirectoryDetector:
    """目录检测器类"""

    def __init__(self):
        self.astrbot_root = None
        self.plugins_dir = None
        self.data_dir = None

    def detect_astrbot_installation(self) -> str | None:
        """检测AstrBot安装目录

        Returns:
            Optional[str]: AstrBot根目录路径，未找到返回None
        """
        if self.astrbot_root:
            return self.astrbot_root

        # 从当前插件目录开始向上搜索AstrBot根目录
        current_dir = Path(__file__).parent.absolute()

        # 如果当前目录是插件目录（包含main.py），则从父目录开始搜索
        if (
            current_dir.parent / "main.py"
        ).exists() and "astrbot_plugin_" in current_dir.name:
            current_dir = current_dir.parent

        # 向上搜索AstrBot根目录
        for _ in range(10):  # 最多向上搜索10级目录
            if self._is_astrbot_root(str(current_dir)):
                self.astrbot_root = str(current_dir)
                return self.astrbot_root
            if current_dir.parent == current_dir:  # 已经到达根目录
                break
            current_dir = current_dir.parent

        return None

    def _is_astrbot_root(self, path: str) -> bool:
        """检查是否为AstrBot根目录

        Args:
            path: 目录路径

        Returns:
            bool: 是否为AstrBot根目录
        """
        # 检查关键文件
        if not os.path.exists(os.path.join(path, "main.py")):
            return False

        # 检查main.py文件内容是否包含AstrBot相关标识
        main_py_path = os.path.join(path, "main.py")
        try:
            with open(main_py_path, encoding="utf-8") as f:
                content = f.read(1000)  # 读取前1000个字符
                if "AstrBot" in content:
                    # 进一步检查是否存在data/plugins目录结构
                    data_plugins_path = os.path.join(path, "data", "plugins")
                    if os.path.exists(data_plugins_path):
                        return True
        except:
            pass

        return False

    def get_plugins_directory(self) -> str | None:
        """获取插件目录

        Returns:
            Optional[str]: 插件目录路径，未找到返回None
        """
        if self.plugins_dir:
            return self.plugins_dir

        try:
            # 获取当前插件目录
            current_plugin_dir = Path(__file__).parent.absolute()

            # 如果当前目录是插件目录（包含main.py），则从父目录开始搜索
            if (
                current_plugin_dir.parent / "main.py"
            ).exists() and "astrbot_plugin_" in current_plugin_dir.name:
                plugins_dir = current_plugin_dir.parent
                if plugins_dir.name == "plugins":
                    self.plugins_dir = str(plugins_dir)
                    return self.plugins_dir

            # 尝试获取AstrBot数据目录
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(str(current_plugin_dir))), "data"
            )
            if os.path.exists(data_dir):
                plugins_dir = os.path.join(data_dir, "plugins")
                if os.path.exists(plugins_dir):
                    self.plugins_dir = plugins_dir
                    return plugins_dir

            # 如果以上方法都失败，尝试使用标准路径
            # 假设当前目录结构为: data/plugins/插件名/
            if "astrbot_plugin_" in current_plugin_dir.name:
                plugins_dir = current_plugin_dir.parent
                if plugins_dir.name == "plugins":
                    self.plugins_dir = str(plugins_dir)
                    return self.plugins_dir

        except Exception as e:
            # 使用print代替logger，因为logger未定义
            print(f"获取插件目录时发生错误: {str(e)}")

        return None

    def get_data_directory(self) -> str | None:
        """获取数据目录

        Returns:
            Optional[str]: 数据目录路径，未找到返回None
        """
        if self.data_dir:
            return self.data_dir

        try:
            # 获取当前插件目录
            current_plugin_dir = Path(__file__).parent.absolute()

            # 如果当前目录是插件目录（包含main.py），则从父目录开始搜索
            if (
                current_plugin_dir.parent / "main.py"
            ).exists() and "astrbot_plugin_" in current_plugin_dir.name:
                plugins_dir = current_plugin_dir.parent
                if plugins_dir.name == "plugins":
                    data_dir = plugins_dir.parent
                    if data_dir.name == "data":
                        self.data_dir = str(data_dir)
                        return self.data_dir

            # 尝试基于当前插件位置推断数据目录
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(str(current_plugin_dir))), "data"
            )
            if os.path.exists(data_dir):
                self.data_dir = data_dir
                return data_dir

            # 如果以上方法都失败，尝试使用标准路径
            # 假设当前目录结构为: data/plugins/插件名/
            if "astrbot_plugin_" in current_plugin_dir.name:
                plugins_dir = current_plugin_dir.parent
                if plugins_dir.name == "plugins":
                    data_dir = plugins_dir.parent
                    if data_dir.name == "data":
                        self.data_dir = str(data_dir)
                        return self.data_dir

        except Exception as e:
            # 使用print代替logger，因为logger未定义
            print(f"获取数据目录时发生错误: {str(e)}")

        return None

    def validate_directory_structure(self) -> dict[str, Any]:
        """验证目录结构

        Returns:
            Dict[str, Any]: 验证结果
        """
        result = {
            "valid": False,
            "astrbot_root": None,
            "plugins_dir": None,
            "data_dir": None,
            "issues": [],
        }

        # 检测AstrBot根目录
        astrbot_root = self.detect_astrbot_installation()
        if not astrbot_root:
            # 基于当前插件文件位置验证目录结构
            # 当前插件文件在 data/plugins/插件名/ 下
            current_plugin_dir = Path(__file__).parent.absolute()
            if "astrbot_plugin_" in current_plugin_dir.name:
                # 检查是否在标准的 data/plugins/ 结构中
                plugins_dir = current_plugin_dir.parent
                data_dir = plugins_dir.parent

                if (
                    plugins_dir.name == "plugins"
                    and data_dir.name == "data"
                    and data_dir.parent.name != ""
                ):  # 确保不是根目录
                    result["valid"] = True
                    result["plugins_dir"] = str(plugins_dir)
                    result["data_dir"] = str(data_dir)
                    return result

            result["issues"].append("未找到AstrBot安装目录")
        else:
            result["astrbot_root"] = astrbot_root

            # 检查插件目录
            plugins_dir = self.get_plugins_directory()
            if not plugins_dir:
                result["issues"].append("未找到插件目录")
            else:
                result["plugins_dir"] = plugins_dir

            # 检查数据目录
            data_dir = self.get_data_directory()
            if not data_dir:
                result["issues"].append("未找到数据目录")
            else:
                result["data_dir"] = data_dir

        # 如果没有关键问题，则认为结构有效
        if not result["issues"]:
            result["valid"] = True

        return result

    def check_plugin_exists(self, plugin_name: str) -> bool:
        """检查插件是否已存在

        Args:
            plugin_name: 插件名称

        Returns:
            bool: 是否存在
        """
        plugins_dir = self.get_plugins_directory()
        if not plugins_dir:
            return False

        # 标准化插件名称
        if not plugin_name.startswith("astrbot_plugin_"):
            plugin_name = f"astrbot_plugin_{plugin_name}"

        plugin_path = os.path.join(plugins_dir, plugin_name)
        return os.path.exists(plugin_path)

    def get_plugin_path(self, plugin_name: str) -> str | None:
        """获取插件路径

        Args:
            plugin_name: 插件名称

        Returns:
            Optional[str]: 插件路径，不存在返回None
        """
        plugins_dir = self.get_plugins_directory()
        if not plugins_dir:
            return None

        # 标准化插件名称
        if not plugin_name.startswith("astrbot_plugin_"):
            plugin_name = f"astrbot_plugin_{plugin_name}"

        plugin_path = os.path.join(plugins_dir, plugin_name)
        if os.path.exists(plugin_path):
            return plugin_path

        return None
