# AstrBot代码审查器

## 概述

AstrBot代码审查器是一个专门为AstrBot插件开发设计的静态代码分析工具，集成了 `ruff`、`pylint` 和 `mypy` 三大工具，用于对LLM生成的代码进行深度质量检查。

## 特性

### 1. 三重静态分析

- **Ruff**: 快速的Python代码检查和格式化工具
  - 检查代码风格和常见问题
  - 验证代码格式是否符合规范
  - 检测潜在的性能问题和bug
  
- **Pylint**: 全面的代码质量检查
  - 代码质量评分 (0-10分)
  - 检查命名规范、代码复杂度
  - 识别潜在的逻辑错误
  
- **Mypy**: 静态类型检查
  - 检测类型不匹配问题
  - 确保类型安全
  - 发现潜在的运行时错误

### 2. AstrBot特定规则检查

审查器还会检查以下AstrBot专用规范：

#### 必须遵守的规则

1. **日志记录规范**
   - 必须使用 `from astrbot.api import logger`
   - 禁止使用 Python 内置的 `logging` 模块
   - 禁止使用第三方日志库（如 loguru）

2. **异步编程规范**
   - 不建议使用同步的 `requests` 库
   - 应使用异步库如 `aiohttp`、`httpx`

3. **插件类结构**（针对 main.py）
   - 必须有一个继承自 `Star` 的类
   - `__init__` 方法签名必须正确
   - `filter` 必须从 `astrbot.api.event` 正确导入

4. **事件处理器规范**
   - 除 `on_astrbot_loaded` 外，所有事件处理器必须包含 `event` 参数
   - `on_llm_request` 和 `on_llm_response` 必须接收3个参数
   - 特殊钩子中禁止使用 `yield`，必须使用 `event.send()`

5. **数据持久化规范**
   - 避免硬编码文件路径
   - 建议使用 `StarTools.get_data_dir()` 获取数据目录

## 配置文件

### .ruff.toml

配置 ruff 的检查规则和格式化选项：

- 目标 Python 版本: 3.10
- 行长度: 100
- 启用的规则集: 代码风格、安全性、bugbear、异步最佳实践等
- 引号风格: 双引号

### .pylintrc

配置 pylint 的检查规则：

- Python 版本: 3.10
- 命名规范: snake_case 函数/变量，PascalCase 类名
- 代码复杂度限制
- 禁用过于严格的文档要求
- 针对异步代码的特殊配置

### mypy.ini

配置 mypy 的类型检查：

- Python 版本: 3.10
- 忽略缺失的第三方库类型定义
- 开启基本的类型检查
- 配置 astrbot 相关库的导入忽略

## 使用方法

### 1. 独立使用

```python
from astrbot_code_auditor import AstrBotCodeAuditor

# 初始化审查器
auditor = AstrBotCodeAuditor()

# 审查代码
code = """
from astrbot.api import logger
from astrbot.api.star import Star, Context
from astrbot.api.event import filter, AstrMessageEvent

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    @filter.command("test")
    async def test(self, event: AstrMessageEvent):
        logger.info("测试指令")
        yield event.plain_result("Hello!")
"""

result = auditor.audit_code(code, "main.py")

print(f"通过: {result['approved']}")
print(f"满意度: {result['satisfaction_score']}/100")
print(f"Pylint评分: {result['pylint_score']}/10")
print(f"问题列表: {result['issues']}")
```

### 2. 集成到插件生成流程

在 CodeMage 插件中，审查器已自动集成到代码生成流程中。通过配置项 `enable_static_analysis` 可以控制是否启用静态分析：

```json
{
  "enable_static_analysis": true
}
```

### 3. 审查整个插件目录

```python
auditor = AstrBotCodeAuditor()
result = auditor.audit_plugin_files("/path/to/plugin/directory")

print(f"通过: {result['approved']}")
print(f"总问题数: {result['total_issues']}")
for file, file_result in result['files'].items():
    print(f"文件 {file}: {file_result['approved']}")
```

## 输出结果

审查器返回的结果包含以下字段：

```python
{
    "approved": bool,              # 是否通过审查
    "satisfaction_score": int,     # 满意度分数 (0-100)
    "pylint_score": float,         # Pylint评分 (0-10)
    "ruff_passed": bool,           # Ruff检查是否通过
    "pylint_passed": bool,         # Pylint检查是否通过
    "mypy_passed": bool,           # Mypy检查是否通过
    "astrbot_rules_passed": bool,  # AstrBot规则是否通过
    "issues": List[str],           # 问题列表
    "total_issues": int,           # 问题总数
    "reason": str                  # 审查理由
}
```

## 满意度评分标准

满意度分数由以下因素决定：

- **基础分数**: Pylint评分 × 10 (0-100)
- **扣分项**:
  - Ruff检查未通过: -20分
  - Mypy检查未通过: -20分
  - AstrBot规则未通过: -15分

最终分数范围: 0-100

**评级标准**:
- 90-100分: 优秀，代码质量很高
- 80-89分: 良好，有少量问题但不影响使用
- 70-79分: 一般，需要优化
- 60-69分: 及格，有较多问题
- 0-59分: 不合格，存在严重问题

## 与LLM审查的结合

在 CodeMage 插件中，静态分析和LLM审查会结合使用：

1. **先进行静态分析**: 快速发现语法、类型、规范问题
2. **再进行LLM审查**: 深度分析逻辑、安全性、功能完整性
3. **综合评分**: 静态分析 60% + LLM审查 40%

这种双重审查机制确保了：
- 代码符合Python最佳实践
- 代码符合AstrBot开发规范
- 代码逻辑正确、安全可靠
- 功能完整、易于维护

## 安装依赖

要使用审查器，需要安装以下工具：

```bash
pip install ruff pylint mypy
```

如果工具未安装，审查器会跳过对应的检查并输出警告，但不会中断整个审查流程。

## 自定义配置

可以通过修改配置文件来调整审查规则：

- 修改 `.ruff.toml` 自定义 ruff 规则
- 修改 `.pylintrc` 自定义 pylint 规则
- 修改 `mypy.ini` 自定义 mypy 规则

配置文件会自动被审查器读取和使用。

## 最佳实践

1. **开发时使用**: 在本地开发插件时使用审查器，及早发现问题
2. **CI/CD集成**: 在持续集成流程中加入审查步骤
3. **代码审查**: 在代码审查时参考审查器的输出
4. **定期检查**: 定期对现有插件运行审查，发现潜在问题

## 限制和注意事项

1. 静态分析无法完全替代人工审查和测试
2. 某些AstrBot规则检查基于正则表达式，可能有误报
3. 需要安装对应的工具才能进行完整检查
4. 审查器主要针对单文件插件，多文件插件可能需要额外处理

## 贡献

欢迎提交问题和改进建议！如果发现AstrBot特定规则的问题，或者需要添加新的检查规则，请提交 Issue 或 Pull Request。
