"""
CodeMage LLM调用处理器模块
负责处理与LLM的交互和调用
"""

import json
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.star import Context

from .utils import extract_code_blocks, parse_json_response


class LLMHandler:
    """LLM调用处理器类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        self.context = context
        self.config = config
        self.provider_id = config.get("llm_provider_id")
        self.negative_prompt = config.get("negative_prompt", "")
        self.logger = logger
        self._dev_docs_cache: str | None = None

    async def call_llm(
        self, prompt: str, system_prompt: str = "", expect_json: bool = False
    ) -> str:
        """调用LLM

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            expect_json: 是否期望返回JSON格式

        Returns:
            str: LLM响应内容
        """
        if not self.provider_id:
            raise ValueError("未配置LLM提供商ID")

        # 构建完整的系统提示词
        full_system_prompt = system_prompt
        if self.negative_prompt:
            full_system_prompt += f"\n\n反向提示词：{self.negative_prompt}"

        try:
            # 构建额外参数
            extra_kwargs = {}
            if expect_json:
                # 使用 OpenAI 兼容的 JSON 模式参数
                extra_kwargs["response_format"] = {"type": "json_object"}

            # 使用新 API llm_generate
            # 显式传递 contexts=[] 确保生成请求是无状态的，不包含之前的对话历史
            llm_resp = await self.context.llm_generate(
                chat_provider_id=self.provider_id,
                prompt=prompt,
                system_prompt=full_system_prompt,
                contexts=[],
                **extra_kwargs,
            )
            return llm_resp.completion_text

        except Exception as e:
            logger.error(f"LLM调用失败：{str(e)}")
            raise

    def _get_dev_docs(self) -> str:
        """获取开发文档（带缓存）

        Returns:
            str: 开发文档内容
        """
        if self._dev_docs_cache is None:
            try:
                # 尝试从当前目录读取
                import os

                current_dir = os.path.dirname(os.path.abspath(__file__))
                doc_path = os.path.join(current_dir, "merged_plugin_dev_docs.md")

                if os.path.exists(doc_path):
                    with open(doc_path, encoding="utf-8") as f:
                        self._dev_docs_cache = f.read()
                else:
                    self.logger.warning(f"开发文档不存在: {doc_path}")
                    self._dev_docs_cache = ""
            except Exception as e:
                self.logger.warning(f"无法读取开发文档: {str(e)}")
                self._dev_docs_cache = ""

        return self._dev_docs_cache

    async def generate_plugin_metadata(self, description: str) -> dict[str, Any]:
        """生成插件元数据和MD文档

        Args:
            description: 插件描述

        Returns:
            Dict[str, Any]: 包含元数据和MD文档的字典
        """
        # 读取插件开发文档
        dev_docs = self._get_dev_docs()

        system_prompt = f"""你是一个专业的AstrBot插件开发助手。请根据用户描述生成插件的元数据和Markdown文档。

请严格按照以下AstrBot插件开发规范：

## 插件开发规范（必须遵守）：

- 需包含良好的注释
- 良好的错误处理，避免插件崩溃

## 开发文档：
{dev_docs}...

请按照以下格式返回，包含在```json和```之间：

```json
{{
  "name": "插件名称",
  "author": "作者名称",
  "description": "插件描述",
  "version": "1.0.0",
  "metadata": {{
    "repo_url": "仓库地址",
    "dependencies": ["依赖1", "依赖2"]
  }},
  "markdown": "# 插件名称\\n\\n## 插件简介\\n\\n插件功能简要介绍\\n\\n## 功能说明\\n\\n插件提供的具体功能\\n\\n## 插件流程\\n\\n详细说明插件的工作流程和内部逻辑，包括各种情况下的处理过程\\n\\n## 使用方法\\n\\n详细说明如何使用插件的各项功能，包括命令使用示例等\\n\\n## 配置说明\\n\\n插件配置项说明\\n\\n## 注意事项\\n\\n使用插件需要注意的事项和限制"
}}
```

要求：
1. 插件名称要简洁明了，使用英文，以astrbot_plugin_开头
2. Markdown文档要详细说明插件功能、工作流程和使用方法，提供充足的信息
3. 插件流程部分需要详细描述插件的内部工作逻辑
4. 使用方法部分需要提供具体的使用示例和操作指南
5. 确保生成的内容符合反向提示词要求：{self.negative_prompt}
6. 严格按照上述开发规范生成插件结构"""

        prompt = f"请为以下插件描述生成元数据和Markdown文档：\n\n{description}"

        response = await self.call_llm(prompt, system_prompt)

        # 解析JSON响应
        json_match = extract_code_blocks(response)
        if json_match:
            json_content = json_match[0]
            result = parse_json_response(json_content)
            if result:
                return result

        raise ValueError("无法解析LLM返回的插件元数据")

    async def generate_metadata_structure(self, description: str) -> dict[str, Any]:
        """分步生成插件元数据

        Args:
            description: 插件描述

        Returns:
            Dict[str, Any]: 插件元数据
        """
        dev_docs = self._get_dev_docs()

        system_prompt = f"""你是一个专业的AstrBot插件规划助手。请根据用户描述先生成插件的元数据信息，不要生成Markdown文档。

请严格遵守以下要求：
1. 输出必须是JSON，并放在```json和```之间
2. JSON需要包含以下字段：
   - name: string，插件名称，格式为 astrbot_plugin_xxx
   - author: string
   - description: string
   - version: string，格式为 "1.0.0"
   - tags: string数组，可选
   - commands: 数组，每个元素包含 command(指令名) 和 description(说明)
   - metadata: 对象，其中包含：
       - repo_url: string
       - dependencies: 字符串数组（可为空数组）
3. 严格遵守反向提示词要求：{self.negative_prompt}
4. 插件的功能设计必须符合以下开发文档：
{dev_docs}...
"""

        prompt = f"根据以下描述生成AstrBot插件的元数据：\n\n{description}"
        response = await self.call_llm(prompt, system_prompt)
        json_blocks = extract_code_blocks(response)
        if json_blocks:
            metadata = parse_json_response(json_blocks[0])
            if metadata:
                return metadata

        metadata = parse_json_response(response)
        if metadata:
            return metadata

        raise ValueError("无法解析LLM返回的插件元数据信息")

    async def generate_markdown_document(
        self, metadata: dict[str, Any], description: str
    ) -> str:
        """生成插件Markdown文档

        Args:
            metadata: 插件元数据
            description: 用户原始描述

        Returns:
            str: Markdown文档内容
        """
        dev_docs = self._get_dev_docs()
        metadata_str = json.dumps(metadata, ensure_ascii=False, indent=2)

        system_prompt = f"""你是一个专业的AstrBot插件技术作家。请根据插件元数据生成详细的Markdown文档。

请严格遵守以下要求：
1. 输出必须放在`````和```之间
2. 文档需要包含以下章节：
   - 插件简介
   - 功能说明
   - 插件流程（必须详细说明插件的工作流程和内部逻辑）
   - 使用方法（必须详细说明如何使用插件的各种功能）
   - 配置说明（如果有配置项）
   - 注意事项
3. 文档内容必须与元数据描述一致，并符合反向提示词要求：{self.negative_prompt}
4. 插件流程和使用方法部分必须提供足够详细的信息，确保用户能够充分了解插件的工作原理和使用方式
5. 请参考以下开发文档，确保文档结构和术语符合规范：
{dev_docs}...
"""

        prompt = f"根据以下插件信息生成Markdown文档：\n\n元数据：\n{metadata_str}\n\n用户描述：\n{description}"
        response = await self.call_llm(prompt, system_prompt)
        markdown_blocks = extract_code_blocks(response)
        if markdown_blocks:
            return markdown_blocks[0]

        raise ValueError("无法从LLM响应中提取插件Markdown文档")

    async def optimize_plugin_metadata(
        self, metadata: dict[str, Any], feedback: str = ""
    ) -> dict[str, Any]:
        """优化插件元数据和MD文档

        Args:
            metadata: 原始元数据
            feedback: 用户反馈

        Returns:
            Dict[str, Any]: 优化后的元数据
        """
        system_prompt = f"""你是一个专业的AstrBot插件开发助手。请根据用户反馈优化插件的元数据和Markdown文档。

请按照以下格式返回，包含在```json和```之间：

```json
{{
  "name": "插件名称",
  "author": "作者名称",
  "description": "插件描述",
  "version": "1.0.0",
  "metadata": {{
    "repo_url": "仓库地址",
    "dependencies": ["依赖1", "依赖2"]
  }},
  "markdown": "# 插件名称\\n\\n## 插件简介\\n\\n插件功能简要介绍\\n\\n## 功能说明\\n\\n插件提供的具体功能\\n\\n## 插件流程\\n\\n详细说明插件的工作流程和内部逻辑，包括各种情况下的处理过程\\n\\n## 使用方法\\n\\n详细说明如何使用插件的各项功能，包括命令使用示例等\\n\\n## 配置说明\\n\\n插件配置项说明\\n\\n## 注意事项\\n\\n使用插件需要注意的事项和限制"
}}
```

要求：
1. 根据用户反馈进行针对性优化
2. 保持JSON格式正确
3. 确保Markdown文档包含详细的插件流程和使用方法
4. 插件流程部分需要详细描述插件的内部工作逻辑
5. 使用方法部分需要提供具体的使用示例和操作指南
6. 确保生成的内容符合反向提示词要求：{self.negative_prompt}"""

        current_metadata = json.dumps(metadata, ensure_ascii=False, indent=2)
        prompt = f"请优化以下插件元数据：\n\n{current_metadata}\n\n用户反馈：{feedback}"

        response = await self.call_llm(prompt, system_prompt)

        # 解析JSON响应
        json_match = extract_code_blocks(response)
        if json_match:
            json_content = json_match[0]
            result = parse_json_response(json_content)
            if result:
                return result

        raise ValueError("无法解析LLM返回的优化后插件元数据")

    async def generate_plugin_code(
        self, metadata: dict[str, Any], markdown: str, config_schema: str = ""
    ) -> str:
        """生成插件代码

        Args:
            metadata: 插件元数据
            markdown: Markdown文档
            config_schema: 配置文件内容

        Returns:
            str: 插件代码
        """
        # 读取插件开发文档
        dev_docs = self._get_dev_docs()

        system_prompt = f"""你是一个专业的AstrBot插件开发助手。请根据插件元数据和Markdown文档生成完整的插件代码。
## 开发文档：
{dev_docs}...

要求：
1. 生成完整的main.py文件
2. 代码要符合AstrBot插件开发规范
3. 包含必要的错误处理
4. 代码要有良好的注释
5. 确保生成的内容符合反向提示词要求：{self.negative_prompt}
6. 如果有配置文件，必须在插件的__init__方法中正确接收和使用config参数
7. 配置项的使用示例：self.config.get("配置项名", "默认值")

配置文件内容（如果有）：
```json
{config_schema}
```

请直接返回Python代码，包含在``python和```之间。"""

        metadata_str = json.dumps(metadata, ensure_ascii=False, indent=2)
        prompt = f"请根据以下插件元数据和Markdown文档生成插件代码：\n\n元数据：\n{metadata_str}\n\n文档：\n{markdown}"

        response = await self.call_llm(prompt, system_prompt)

        # 提取代码块
        code_blocks = extract_code_blocks(response)
        if code_blocks:
            return code_blocks[0]

        raise ValueError("无法从LLM响应中提取插件代码")

    async def review_plugin_code(
        self, code: str, metadata: dict[str, Any], markdown: str
    ) -> dict[str, Any]:
        """审查插件代码

        Args:
            code: 插件代码
            metadata: 插件元数据
            markdown: Markdown文档

        Returns:
            Dict[str, Any]: 审查结果
        """
        # 读取插件开发文档
        dev_docs = self._get_dev_docs()

        negative_prompt = self.config.get("negative_prompt", "")

        system_prompt = f"""# Role: Python Code Review Expert

你是一位资深的 Python 代码审查专家，专注于代码质量、安全性和异步最佳实践。

## 任务

你的任务是分析提供的Python文件。针对每个文件，分别提供一份审查报告，以 ### 文件路径 为标题开头。将所有报告合并为单一响应。请严格遵循以下所有规则和审查要点，并**只报告发现的问题**。

## 核心审查要求

### 1. 版本与运行环境
- **Python 版本**: 严格限定为 Python 3.10 进行审查。
- **运行环境**: 代码运行在异步环境中。

### 2. 综合审查维度
请从以下五个维度进行全面分析：
- **代码质量与编码规范**:
    - 是否遵循 PEP 8 规范？
    - 命名是否清晰、表意明确？
    - 是否有过于复杂的代码块可以简化？
- **功能实现与逻辑正确性**:
    - 代码是否能够正确实现其预期功能？
    - 是否存在明显的逻辑错误或边界条件处理不当？
- **安全漏洞与最佳实践**:
    - 是否存在常见的安全漏洞（如：不安全的外部命令执行、硬编码的敏感信息、不安全的 pickle 反序列化等）？
    - 是否遵循了 Python 社区公认的最佳实践？
- **可维护性与可读性**:
    - 代码结构是否清晰，易于理解和维护？
    - 函数和类的职责是否单一明确？
- **潜在缺陷或问题**:
    - 是否存在潜在的性能瓶颈？
    - 是否有未处理的异常或资源泄漏风险？

### 3. 框架适应性检查

- **日志记录**:
    - 日志记录器 logger **必须且只能**从 astrabot.api 导入 (即 from astrbot.api import logger)。
    - **严禁**使用任何其他第三方日志库（如 loguru）或 Python 内置的 logging 模块（例如 logging.getLogger）。

- **并发模型**:
    - 检查代码中是否存在**同步阻塞**操作，注意仅检测并指出网络I/O相关问题，无需检测或指出文件I/O相关问题。

- **数据持久化**:
    - 对于需要持久化保存的数据，应检查其是否通过从 astrabot.api.star 导入 StarTools 并调用 StarTools.get_data_dir() 方法来获取规范的数据存储目录，以避免硬编码路径。
    - 注意，StarTools.get_data_dir() 方法返回的路径是一个 Path 对象，而不是字符串，因此在使用时需要确保正确处理。
    - StarTools.get_data_dir() 方法返回的路径为 data/plugin_data/<plugin_name>。如插件需要操作其他目录的文件，则禁止向用户提出违反了数据持久化的检查项。


### 4. 针对 main.py 的额外审查要求 (必须严格遵守)

除了上述通用规则，还需对 main.py 的结构进行以下专项检查：

- **插件注册与主类**:
    - 文件中**必须**存在一个继承自 Star 的类。
    - 该类**可以**使用 @register 装饰器进行注册。
    - 注册格式应为 @register("插件名", "作者", "描述", "版本", "仓库链接")。
    - 注册格式也可以为 @register("插件名", "作者", "描述", "版本")。
    - **正确示例-1**:

      @register("helloworld", "Soulter", "一个简单的 Hello World 插件", "1.0.0", "repo url")
      class MyPlugin(Star):
          def __init__(self, context: Context):
              super().__init__(context)

    - **正确示例-2**:
      @register("helloworld", "Soulter", "一个简单的 Hello World 插件", "1.0.0")
      class MyPlugin(Star):
          def __init__(self, context: Context):
              super().__init__(context)

    - **注意**: 在 v3.5.20 版本之后，@register 装饰器已废弃，AstrBot 会自动识别继承自 Star 的类并将其作为插件类加载。因此，建议在新版本中不再使用 @register 装饰器。
    - **v3.5.20 版本之后的示例**:
      class MyPlugin(Star):
          def __init__(self, context: Context):
              super().__init__(context)


- **filter 装饰器导入**:
    - 所有事件监听器的装饰器（如 @filter.command）都来自于 filter 对象。
    - **必须**检查 filter 是否从 astrbot.api.event.filter 正确导入 (即 from astrbot.api.event import filter)。
    - 此项检查至关重要，以避免与 Python 内置的 filter 函数产生命名冲突。

- **LLM 事件钩子 (on_llm_request / on_llm_response)**:
    - 如果实现了 on_llm_request 或 on_llm_response 钩子，请严格检查其定义。
    - 它们必须是 async def 方法。
    - 它们必须接收**三个**参数：self, event: AstrMessageEvent，以及第三个特定对象。
    - **正确示例**:

      # 请注意有三个参数
      @filter.on_llm_request()
      async def my_custom_hook_1(self, event: AstrMessageEvent, req: ProviderRequest):
          ...

      # 请注意有三个参数
      @filter.on_llm_response()
      async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
          ...

- **@filter.llm_tool 与 @filter.permission_type 的使用限制**:
    - @filter.permission_type 装饰器无法用于 @filter.llm_tool 装饰的方法上，这种权限控制组合是无效的。

- **通用事件监听器签名**:
    - **除去 on_astrbot_loaded 外**，所有使用 @filter 装饰的事件监听器方法（如 @filter.command, @filter.on_full_match 等），其签名中都必须包含 event 参数。
    - **正确示例**:

      @filter.command("helloworld")
      async def helloworld(self, event: AstrMessageEvent):
          '''这是 hello world 指令'''
          user_name = event.get_sender_name()
          yield event.plain_result(f"Hello, {{user_name}}!")


- **消息发送方式**:
    - 在 on_llm_request, on_llm_response, on_decorating_result, after_message_sent 这四个特殊的钩子函数内部，**禁止**使用 yield 语句（如 yield event.plain_result(...)）来发送消息。
    - 在这些函数中如果需要发送消息，**必须**直接调用 event.send() 方法。

警告！请**严格**按照以下JSON格式返回审查结果：

```json
{{
  "approved": true/false,
  "satisfaction_score": 0-100,
  "reason": "审查理由",
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}}
```

审查标准（附加）：
1. 代码安全性：
   - 严格检查是否违反反向提示词要求：{negative_prompt}

2. 功能完整性：
   - 代码是否实现了元数据中描述的所有功能
   - 是否包含必要的错误处理机制
   - 是否使用了正确的AstrBot API（如使用 logger 而不是 logging）

3. 代码质量：
   - 是否有良好的代码结构和注释
   - 是否遵循Python编码规范
   - 是否包含必要的文档字符串

4. 开发文档合规性：
   - 代码是否符合AstrBot插件开发文档中的规范

开发文档参考：
{dev_docs}...

满意度评分标准（必须严格执行）：
- 90-100分：优秀，代码完全符合所有标准，可以直接使用
- 80-89分：良好，有小问题但不影响使用，需要小修改
- 70-79分：一般，有一些问题需要修复，不能直接使用
- 60-69分：较差，有较多问题需要修复，需要重大修改
- 0-59分：不合格，存在严重安全问题或功能缺失，需要重新生成

重要：如果发现任何无法运行的问题或违反反向提示词要求，必须将 approved 设置为 false，并给出详细的问题描述。"""

        prompt = f"请审查以下插件代码：\n\n代码：\n{code}\n\n元数据：\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n文档：\n{metadata}"

        response = await self.call_llm(prompt, system_prompt, expect_json=True)

        # 解析JSON响应
        result = parse_json_response(response)
        if result:
            return result

        raise ValueError("无法解析LLM返回的代码审查结果")

    async def fix_plugin_code(
        self, code: str, issues: list[str], suggestions: list[str], max_retries: int = 3
    ) -> str:
        """修复插件代码

        Args:
            code: 原始代码
            issues: 问题列表
            suggestions: 建议列表
            max_retries: 最大重试次数

        Returns:
            str: 修复后的代码
        """
        system_prompt = f"""你是一个专业的AstrBot插件开发助手。请根据审查结果修复插件代码中的问题。

要求：
1. 修复所有列出的问题
2. 采纳合理的建议
3. 保持原有功能不变
4. 确保修复后的代码符合反向提示词要求：{self.negative_prompt}

请直接返回修复后的Python代码，包含在``python和```之间。"""

        issues_str = "\n".join([f"- {issue}" for issue in issues])
        suggestions_str = "\n".join([f"- {suggestion}" for suggestion in suggestions])
        prompt = f"请修复以下插件代码中的问题：\n\n代码：\n{code}\n\n问题：\n{issues_str}\n\n建议：\n{suggestions_str}"

        for attempt in range(max_retries):
            try:
                response = await self.call_llm(prompt, system_prompt)

                # 提取代码块
                code_blocks = extract_code_blocks(response)
                if code_blocks:
                    return code_blocks[0]

                # 如果不是最后一次尝试，修改提示词要求更明确的格式
                if attempt < max_retries - 1:
                    prompt += "\n\n重要：请确保返回的代码包含在```python和```之间，不要包含其他内容。"

            except Exception as e:
                logger.error(
                    f"修复插件代码失败（尝试 {attempt + 1}/{max_retries}）：{str(e)}"
                )
                if attempt == max_retries - 1:
                    raise

        raise ValueError(
            f"经过{max_retries}次重试，仍无法从LLM响应中提取修复后的插件代码"
        )

    async def generate_config_schema(
        self, metadata: dict[str, Any], description: str
    ) -> str:
        """生成插件配置文件

        Args:
            metadata: 插件元数据
            description: 用户原始描述

        Returns:
            str: 配置文件JSON内容
        """
        dev_docs = self._get_dev_docs()

        system_prompt = f"""你是一个专业的AstrBot插件配置设计助手。请根据插件元数据和功能描述生成插件的配置文件(_conf_schema.json)。

请严格遵守以下要求：
1. 输出必须是JSON格式，并放在```json和```之间
2. 配置文件需要包含插件可能需要的配置项
3. 根据插件功能智能推断合适的配置项类型和默认值
4. 配置项应该包含description、type、hint、default等字段
5. 确保配置项设计合理，符合AstrBot配置规范
6. 严格遵守反向提示词要求：{self.negative_prompt}
7. 设计文档// 请你把这里补充好
8. 参考以下开发文档，确保配置文件符合规范：
{dev_docs}...

请按照以下格式返回：
```json
{{
  "配置项名": {{
    "description": "配置项描述",
    "type": "string/int/float/bool/object/list",
    "hint": "配置项提示信息",
    "default": "默认值",
    "obvious_hint": true/false,
    "options": ["选项1", "选项2"],
    "editor_mode": true/false,
    "editor_language": "json",
    "editor_theme": "vs-light"
  }}
}}
```

要求：
1. 根据插件功能智能推断需要的配置项
2. 配置项类型要准确（string、int、float、bool、object、list）
3. 提供合理的默认值和提示信息
4. 对于复杂配置项，可以提供options选项列表
5. 对于需要大量文本的配置项，可以启用editor_mode
6. 确保生成的内容符合反向提示词要求"""

        prompt = f"请为以下插件生成配置文件：\n\n插件元数据：\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n功能描述：\n{description}"

        response = await self.call_llm(prompt, system_prompt)

        # 解析JSON响应
        json_blocks = extract_code_blocks(response)
        if json_blocks:
            config_content = json_blocks[0]
            # 验证是否为有效JSON
            try:
                parsed_config = json.loads(config_content)
                return config_content
            except json.JSONDecodeError:
                self.logger.warning("LLM返回的配置文件JSON格式不正确，尝试提取")
                # 尝试从响应中提取JSON
                parsed_config = parse_json_response(response)
                if parsed_config:
                    return json.dumps(parsed_config, ensure_ascii=False, indent=2)

        raise ValueError("无法生成有效的插件配置文件")

    async def modify_config_schema(
        self, current_config: str, metadata: dict[str, Any], feedback: str = ""
    ) -> str:
        """修改插件配置文件

        Args:
            current_config: 当前配置文件内容
            metadata: 插件元数据
            feedback: 用户反馈

        Returns:
            str: 修改后的配置文件内容
        """
        dev_docs = self._get_dev_docs()
        system_prompt = f"""你是一个专业的AstrBot插件配置修改助手。请根据用户反馈修改插件的配置文件。

请严格遵守以下要求：
1. 根据用户反馈进行针对性修改
2. 保持JSON格式正确
3. 确保配置项设计合理，符合AstrBot配置规范
4. 严格遵守反向提示词要求：{self.negative_prompt}
5. 参考以下开发文档，确保配置文件符合规范：
{dev_docs}...

当前配置文件：
```json
{current_config}
```

插件元数据：
```json
{json.dumps(metadata, ensure_ascii=False, indent=2)}
```

用户反馈：{feedback}

请直接返回修改后的JSON配置文件内容，包含在```json和```之间。"""

        prompt = f"请根据用户反馈修改以下插件配置文件：\n\n当前配置：\n{current_config}\n\n插件元数据：\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n用户反馈：\n{feedback}"

        response = await self.call_llm(prompt, system_prompt)

        # 解析JSON响应
        json_blocks = extract_code_blocks(response)
        if json_blocks:
            return json_blocks[0]

        raise ValueError("无法修改插件配置文件")

    async def modify_markdown_document(
        self, current_markdown: str, metadata: dict[str, Any], feedback: str = ""
    ) -> str:
        """修改插件Markdown文档

        Args:
            current_markdown: 当前Markdown文档内容
            metadata: 插件元数据
            feedback: 用户反馈

        Returns:
            str: 修改后的Markdown文档内容
        """
        system_prompt = f"""你是一个专业的AstrBot插件文档修改助手。请根据用户反馈修改插件的Markdown文档。

请严格遵守以下要求：
1. 根据用户反馈进行针对性修改
2. 保持Markdown格式正确
3. 确保文档内容与元数据描述一致
4. 严格遵守反向提示词要求：{self.negative_prompt}

当前Markdown文档：
```markdown
{current_markdown}
```

插件元数据：
```json
{json.dumps(metadata, ensure_ascii=False, indent=2)}
```

用户反馈：{feedback}

请直接返回修改后的Markdown文档内容，包含在`````和```之间。"""

        prompt = f"请根据用户反馈修改以下插件Markdown文档：\n\n当前文档：\n{current_markdown}\n\n插件元数据：\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n\n用户反馈：\n{feedback}"

        response = await self.call_llm(prompt, system_prompt)

        # 提取Markdown内容
        markdown_blocks = extract_code_blocks(response)
        if markdown_blocks:
            return markdown_blocks[0]

        raise ValueError("无法修改插件Markdown文档")

    async def modify_plugin_metadata(
        self, current_metadata: dict[str, Any], feedback: str = ""
    ) -> dict[str, Any]:
        """修改插件元数据

        Args:
            current_metadata: 当前插件元数据
            feedback: 用户反馈

        Returns:
            Dict[str, Any]: 修改后的插件元数据
        """
        system_prompt = f"""你是一个专业的AstrBot插件元数据修改助手。请根据用户反馈修改插件的元数据。

请严格遵守以下要求：
1. 根据用户反馈进行针对性修改
2. 保持JSON格式正确
3. 确保元数据包含必要字段：name、author、description、version、metadata
4. 严格遵守反向提示词要求：{self.negative_prompt}

当前元数据：
```json
{json.dumps(current_metadata, ensure_ascii=False, indent=2)}
```

用户反馈：{feedback}

请按照以下格式返回修改后的元数据，包含在```json和```之间：
```json
{{
  "name": "插件名称",
  "author": "作者名称",
  "description": "插件描述",
  "version": "1.0.0",
  "tags": ["标签1", "标签2"],
  "commands": [
    {{
      "command": "指令名",
      "description": "指令说明"
    }}
  ],
  "metadata": {{
    "repo_url": "仓库地址",
    "dependencies": ["依赖1", "依赖2"]
  }}
}}
```

要求：
1. 根据用户反馈进行针对性修改
2. 保持元数据结构完整
3. 确保修改后的内容符合插件开发规范
4. 插件名称格式为 astrbot_plugin_xxx"""

        prompt = f"请根据用户反馈修改以下插件元数据：\n\n当前元数据：\n{json.dumps(current_metadata, ensure_ascii=False, indent=2)}\n\n用户反馈：\n{feedback}"

        response = await self.call_llm(prompt, system_prompt)

        # 解析JSON响应
        json_blocks = extract_code_blocks(response)
        if json_blocks:
            json_content = json_blocks[0]
            result = parse_json_response(json_content)
            if result:
                return result

        raise ValueError("无法修改插件元数据")
