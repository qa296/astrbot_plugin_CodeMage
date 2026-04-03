"""
CodeMage工具函数模块
提供通用功能函数
"""

import re
import json
import os
import time
from typing import Dict, Any, List, Optional
from astrbot.api import logger


def validate_plugin_description(description: str) -> bool:
    """验证插件描述是否合适
    
    Args:
        description: 插件描述
        
    Returns:
        bool: 是否合适
    """
    if not description or len(description.strip()) < 5:
        return False
        
    # 检查是否包含敏感词
    sensitive_words = [
        "黑客", "破解", "攻击", "病毒", "木马", "钓鱼", "诈骗", 
        "赌博", "色情", "暴力", "政治", "反动", "违法"
    ]
    
    description_lower = description.lower()
    for word in sensitive_words:
        if word in description_lower:
            return False
            
    return True


def format_plugin_info(plugin_info: Dict[str, Any]) -> str:
    """格式化插件信息
    
    Args:
        plugin_info: 插件信息字典
        
    Returns:
        str: 格式化后的插件信息
    """
    info_lines = [
        f"插件名称：{plugin_info.get('name', '未知')}",
        f"作者：{plugin_info.get('author', '未知')}",
        f"描述：{plugin_info.get('description', '无描述')}",
        f"版本：{plugin_info.get('version', '1.0.0')}",
    ]
    
    if 'commands' in plugin_info and plugin_info['commands']:
        info_lines.append("指令列表：")
        for cmd in plugin_info['commands']:
            info_lines.append(f"  - {cmd}")
            
    return "\n".join(info_lines)


def extract_code_blocks(text: str) -> List[str]:
    """从文本中提取代码块
    
    Args:
        text: 包含代码块的文本
        
    Returns:
        List[str]: 提取的代码块列表
    """
    # 匹配 ```python ... ``` 或 ```json ... ``` 或 ``` ... ``` 格式的代码块
    pattern = r'```(?:python|json)?\s*\n?(.*?)\n?```'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


def parse_json_response(text: str) -> Optional[Dict[str, Any]]:
    """解析LLM返回的JSON响应
    
    Args:
        text: LLM返回的文本
        
    Returns:
        Optional[Dict[str, Any]]: 解析后的JSON字典，失败返回None
    """
    try:
        # 尝试直接解析
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取JSON部分
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return None


def sanitize_plugin_name(name: str) -> str:
    """清理插件名称，确保符合命名规范
    
    Args:
        name: 原始插件名称
        
    Returns:
        str: 清理后的插件名称
    """
    # 移除特殊字符，只保留字母、数字和下划线
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', name)
    
    # 确保以字母开头
    if sanitized and not sanitized[0].isalpha():
        sanitized = f"plugin_{sanitized}"
        
    # 转换为小写
    sanitized = sanitized.lower()
    
    # 确保不为空
    if not sanitized:
        sanitized = "unnamed_plugin"
        
    return sanitized


def generate_plugin_id(name: str) -> str:
    """生成插件ID
    
    Args:
        name: 插件名称
        
    Returns:
        str: 插件ID
    """
    timestamp = int(time.time())
    sanitized_name = sanitize_plugin_name(name)
    return f"{sanitized_name}_{timestamp}"


def create_plugin_directory(base_path: str, plugin_name: str) -> str:
    """创建插件目录
    
    Args:
        base_path: 基础路径
        plugin_name: 插件名称
        
    Returns:
        str: 创建的目录路径
    """
    folder_name = plugin_name if plugin_name.startswith("astrbot_plugin_") else f"astrbot_plugin_{plugin_name}"
    plugin_dir = os.path.join(base_path, folder_name)
    os.makedirs(plugin_dir, exist_ok=True)
    return plugin_dir


def validate_plugin_code(code: str, negative_prompt: str) -> Dict[str, Any]:
    """验证插件代码安全性
    
    Args:
        code: 插件代码
        negative_prompt: 反向提示词
        
    Returns:
        Dict[str, Any]: 验证结果
    """
    result = {
        "safe": True,
        "critical_issues": []
    }
    
    # 检查最危险的函数调用
    critical_patterns = [
        r'eval\s*\(',
        r'exec\s*\(',
        r'__import__\s*\(',
        r'subprocess\.',
        r'os\.system\s*\(',
        r'os\.popen\s*\(',
        r'os\.spawn',
        r'os\.exec',
    ]
    
    for pattern in critical_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            result["safe"] = False
            result["critical_issues"].append(f"检测到危险函数调用：{pattern}")
    
    return result


def format_time(timestamp: float) -> str:
    """格式化时间戳
    
    Args:
        timestamp: 时间戳
        
    Returns:
        str: 格式化后的时间字符串
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


def extract_codemage_block(text: str, tag_name: str) -> Optional[str]:
    """提取 <codemage:tag>...</codemage:tag> 包裹的内容
    
    使用带命名空间的 XML 标签包裹内容，避免与内容中可能出现的 ```` ``` ```` 或其他标记冲突。
    
    Args:
        text: 包含 codemage 标签的文本
        tag_name: 标签名，如 'json', 'python', 'markdown'
        
    Returns:
        Optional[str]: 提取的内容，失败返回 None
    """
    pattern = rf'<codemage:{tag_name}>(.*?)</codemage:{tag_name}>'
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None


def escape_markdown(text: str) -> str:
    """转义Markdown特殊字符
    
    Args:
        text: 原始文本
        
    Returns:
        str: 转义后的文本
    """
    markdown_chars = ['\\', '`', '*', '_', '{', '}', '[', ']', 
                     '(', ')', '#', '+', '-', '.', '!', '|']
    
    for char in markdown_chars:
        text = text.replace(char, f'\\{char}')
        
    return text