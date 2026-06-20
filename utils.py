"""
CodeMage工具函数模块
提供通用功能函数
"""

import difflib
import json
import os
import re
import time
from typing import Any


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
        "黑客",
        "破解",
        "攻击",
        "病毒",
        "木马",
        "钓鱼",
        "诈骗",
        "赌博",
        "色情",
        "暴力",
        "政治",
        "反动",
        "违法",
    ]

    description_lower = description.lower()
    for word in sensitive_words:
        if word in description_lower:
            return False

    return True


def format_plugin_info(plugin_info: dict[str, Any]) -> str:
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

    if "commands" in plugin_info and plugin_info["commands"]:
        info_lines.append("指令列表：")
        for cmd in plugin_info["commands"]:
            info_lines.append(f"  - {cmd}")

    return "\n".join(info_lines)


def extract_code_blocks(text: str) -> list[str]:
    """从文本中提取代码块

    Args:
        text: 包含代码块的文本

    Returns:
        List[str]: 提取的代码块列表
    """
    # 匹配 ```python ... ``` 或 ```json ... ``` 或 ``` ... ``` 格式的代码块
    pattern = r"```(?:python|json)?\s*\n?(.*?)\n?```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


def parse_json_response(text: str) -> dict[str, Any] | None:
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
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
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
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "", name)

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
    folder_name = (
        plugin_name
        if plugin_name.startswith("astrbot_plugin_")
        else f"astrbot_plugin_{plugin_name}"
    )
    plugin_dir = os.path.join(base_path, folder_name)
    os.makedirs(plugin_dir, exist_ok=True)
    return plugin_dir


def validate_plugin_code(code: str, negative_prompt: str) -> dict[str, Any]:
    """验证插件代码安全性

    Args:
        code: 插件代码
        negative_prompt: 反向提示词

    Returns:
        Dict[str, Any]: 验证结果
    """
    result = {"safe": True, "critical_issues": []}

    # 检查最危险的函数调用
    critical_patterns = [
        r"eval\s*\(",
        r"exec\s*\(",
        r"__import__\s*\(",
        r"subprocess\.",
        r"os\.system\s*\(",
        r"os\.popen\s*\(",
        r"os\.spawn",
        r"os\.exec",
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


def extract_codemage_block(text: str, tag_name: str) -> str | None:
    """提取 <codemage:tag>...</codemage:tag> 包裹的内容

    使用带命名空间的 XML 标签包裹内容，避免与内容中可能出现的 ```` ``` ```` 或其他标记冲突。

    Args:
        text: 包含 codemage 标签的文本
        tag_name: 标签名，如 'json', 'python', 'markdown'

    Returns:
        Optional[str]: 提取的内容，失败返回 None
    """
    pattern = rf"<codemage:{tag_name}>(.*?)</codemage:{tag_name}>"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None


def escape_markdown(text: str) -> str:
    """转义Markdown特殊字符

    Args:
        text: 原始文本

    Returns:
        str: 转义后的文本
    """
    markdown_chars = [
        "\\",
        "`",
        "*",
        "_",
        "{",
        "}",
        "[",
        "]",
        "(",
        ")",
        "#",
        "+",
        "-",
        ".",
        "!",
        "|",
    ]

    for char in markdown_chars:
        text = text.replace(char, f"\\{char}")

    return text


def parse_search_replace_blocks(text: str) -> list[tuple[str, str]]:
    """解析 LLM 输出的 SEARCH/REPLACE 块。

    块格式：
        <<<<<<< SEARCH
        <原始代码片段>
        =======
        <替换后的代码片段>
        >>>>>>> REPLACE

    Args:
        text: LLM 返回的原始文本。

    Returns:
        List[Tuple[str, str]]: (search, replace) 列表。
        解析失败或 LLM 未输出任何块时返回空列表。
    """
    pattern = re.compile(
        r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE",
        re.DOTALL,
    )
    return [(m.group(1), m.group(2)) for m in pattern.finditer(text)]


def _sliding_window_match(
    content_lines: list[str],
    search_lines: list[str],
    threshold: float,
) -> tuple[int, float] | None:
    """在 content_lines 上做行级滑动窗口，查找与 search_lines 最相似的子序列。

    窗口大小 = search_lines 行数 ±2。

    Args:
        content_lines: 原文件按行切分（不含换行符）。
        search_lines: SEARCH 块按行切分。
        threshold: 相似度阈值。

    Returns:
        Optional[Tuple[int, float]]: (窗口起始行号, 相似度)，低于阈值返回 None。
        行号以 0 开始。
    """
    if not search_lines:
        return None

    n = len(search_lines)
    if not content_lines:
        return None

    best_ratio = 0.0
    best_start = -1

    # 窗口大小 = n ± 2；同时确保窗口至少 1 行
    min_size = max(1, n - 2)
    max_size = n + 2
    max_size = min(max_size, len(content_lines))

    matcher = difflib.SequenceMatcher(autojunk=False)

    for size in range(min_size, max_size + 1):
        for start in range(len(content_lines) - size + 1):
            window = content_lines[start : start + size]
            matcher.set_seqs("\n".join(search_lines), "\n".join(window))
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = start

    if best_ratio >= threshold and best_start >= 0:
        return best_start, best_ratio
    return None


def apply_search_replace(
    content: str,
    search: str,
    replace: str,
    fuzzy_threshold: float = 0.85,
) -> tuple[bool, str, str]:
    """应用单个 SEARCH/REPLACE 到 content。

    匹配策略：
    1. 精确匹配 1 次 → 直接替换。
    2. 精确匹配 ≥2 次 → 报歧义。
    3. 精确匹配 0 次 → 用 difflib 行级滑动窗口做 fuzzy 匹配。
       相似度 ≥ fuzzy_threshold 才应用，并在 message 中标记 method=fuzzy。

    Args:
        content: 原始文件内容。
        search: SEARCH 块原文。
        replace: REPLACE 块原文。
        fuzzy_threshold: fuzzy 匹配的相似度阈值（0~1）。

    Returns:
        Tuple[bool, str, str]: (success, new_content, message)。
        message 中包含匹配方式：'exact' / 'fuzzy' / 失败原因。
    """
    # 1. 精确匹配
    count = content.count(search)
    if count == 1:
        new_content = content.replace(search, replace, 1)
        return True, new_content, "exact"

    if count > 1:
        return (
            False,
            content,
            f"SEARCH block appears {count} times in the file (ambiguous match)",
        )

    # 2. Fuzzy 匹配
    # 切分时保留原始换行结构；splitlines() 会丢弃各种换行符，需要重新拼接
    content_lines = content.splitlines()
    search_lines = search.splitlines()

    window_match = _sliding_window_match(content_lines, search_lines, fuzzy_threshold)
    if window_match is None:
        # 兜底：尝试 trim 末尾空行再匹配（LLM 经常少一个或多个尾随换行）
        trimmed_search = search.rstrip("\n")
        if trimmed_search != search and content.count(trimmed_search) == 1:
            new_content = content.replace(trimmed_search, replace.rstrip("\n"), 1)
            return True, new_content, "exact-trimmed"

        return (
            False,
            content,
            f"SEARCH block not found in the file (no match above fuzzy threshold {fuzzy_threshold})",
        )

    start_line, ratio = window_match
    # 把命中窗口替换为 replace；保留前后换行符不丢失
    # content_lines[start_line] 到 content_lines[start_line + size - 1] 是匹配窗口
    # 窗口大小需要重算（因为 size 在 fuzzy 中变化），根据 ratio 所在 size 重新推导
    # 简化处理：取最佳 size 的窗口——通过重新匹配最佳 size 来定位
    n = len(search_lines)
    best_size = n
    best_r = 0.0
    matcher = difflib.SequenceMatcher(autojunk=False)
    for size in range(max(1, n - 2), min(n + 2, len(content_lines)) + 1):
        window = content_lines[start_line : start_line + size]
        matcher.set_seqs("\n".join(search_lines), "\n".join(window))
        r = matcher.ratio()
        if r > best_r:
            best_r = r
            best_size = size

    new_lines = (
        content_lines[:start_line]
        + replace.splitlines()
        + content_lines[start_line + best_size :]
    )
    # 重建文本：行间用 '\n' 连接；如果原 content 以 '\n' 结尾则保留
    new_content = "\n".join(new_lines)
    if content.endswith("\n") and not new_content.endswith("\n"):
        new_content += "\n"

    return (
        True,
        new_content,
        f"fuzzy (ratio={ratio:.2f}, threshold={fuzzy_threshold})",
    )
