# AstrBot Developer Documentation (Merged)

> All development documentation merged and ordered by importance for plugin developers.

## Table of Contents

1. [Minimal Plugin Example](#minimal-example)
2. [Plugin Development Guide](#astrbot-plugin-development-guide-)
3. [Handling Message Events](#handling-message-events)
4. [Sending Messages](#sending-messages)
5. [AI / LLM Integration](#ai)
6. [Plugin Configuration](#plugin-configuration)
7. [Session Control](#session-control)
8. [Plugin Storage](#plugin-storage)
9. [Text to Image](#text-to-image)
10. [Publishing Plugins](#publishing-plugins-to-the-plugin-marketplace)
11. [AstrBot Configuration File](#astrbot-configuration-file)
12. [HTTP API](#astrbot-http-api)
13. [Developing a Platform Adapter](#开发一个平台适配器)

---

# Minimal Example

The `main.py` file in the plugin template is a minimal plugin instance.

```python
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star
from astrbot.api import logger # Use the logger interface provided by AstrBot

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    # Decorator to register a command. The command name is "helloworld". Once registered, sending `/helloworld` will trigger this command and respond with `Hello, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        '''This is a hello world command''' # This is the handler's description, which will be parsed to help users understand the plugin's functionality. Highly recommended to provide.
        user_name = event.get_sender_name()
        message_str = event.message_str # Get the plain text content of the message
        logger.info("Hello world command triggered!")
        yield event.plain_result(f"Hello, {user_name}!") # Send a plain text message

    async def terminate(self):
        '''Optionally implement the terminate function, which will be called when the plugin is uninstalled/disabled.'''
```

Explanation:

- Plugins must inherit from the `Star` class.
- The `Context` class is used for plugin interaction with AstrBot Core, allowing you to call various APIs provided by AstrBot Core.
- Specific handler functions are defined within the plugin class, such as the `helloworld` function here.
- `AstrMessageEvent` is AstrBot's message event object, which stores information about the message sender, message content, etc.
- `AstrBotMessage` is AstrBot's message object, which stores the specific content of messages delivered by the messaging platform. It can be accessed via `event.message_obj`.

> [!TIP]
>
> Handlers must be registered within the plugin class, with the first two parameters being `self` and `event`. If the file becomes too long, you can write services externally and call them from the handler.
>
> The file containing the plugin class must be named `main.py`.

All handler functions must be written within the plugin class. To keep content concise, in subsequent sections, we may omit the plugin class definition.

---

# AstrBot Plugin Development Guide 🌠

Welcome to the AstrBot Plugin Development Guide! This section will guide you through developing AstrBot plugins. Before we begin, we hope you have the following foundational knowledge:

1. Some experience with Python programming.
2. Some experience with Git and GitHub.

## Environment Setup

### Obtain the Plugin Template

1. Open the AstrBot plugin template: [helloworld](https://github.com/Soulter/helloworld)
2. Click `Use this template` in the upper right corner
3. Then click `Create new repository`.
4. Fill in your plugin name in the `Repository name` field. Plugin naming conventions:
   - Recommended to start with `astrbot_plugin_`;
   - Must not contain spaces;
   - Keep all letters lowercase;
   - Keep it concise.
5. Click `Create repository` in the lower right corner.

### Clone the Project Locally

Clone both the AstrBot main project and the plugin repository you just created to your local machine.

```bash
git clone https://github.com/AstrBotDevs/AstrBot
mkdir -p AstrBot/data/plugins
cd AstrBot/data/plugins
git clone <your-plugin-repository-url>
```

Then, use `VSCode` to open the `AstrBot` project. Navigate to the `data/plugins/<your-plugin-name>` directory.

Update the `metadata.yaml` file with your plugin's metadata information.

> [!WARNING]
> Please make sure to modify this file, as AstrBot relies on the `metadata.yaml` file to recognize plugin metadata.

### Set Plugin Logo (Optional)

You can add a `logo.png` file in the plugin directory as the plugin's logo. Please maintain an aspect ratio of 1:1, with a recommended size of 256x256.

![Plugin logo example](https://files.astrbot.app/docs/source/images/plugin/plugin_logo.png)

### Plugin Display Name (Optional)

You can modify (or add) the `display_name` field in the `metadata.yaml` file to serve as the plugin's display name in scenarios like the plugin marketplace, making it easier for users to read.

### Declare Supported Platforms (Optional)

You can add a `support_platforms` field (`list[str]`) to `metadata.yaml` to declare which platform adapters your plugin supports. The WebUI plugin page will display this field.

```yaml
support_platforms:
  - telegram
  - discord
```

The values in `support_platforms` must be keys from `ADAPTER_NAME_2_TYPE`. Currently supported:

- `aiocqhttp`
- `qq_official`
- `telegram`
- `wecom`
- `lark`
- `dingtalk`
- `discord`
- `slack`
- `kook`
- `vocechat`
- `weixin_official_account`
- `satori`
- `misskey`
- `line`

### Declare AstrBot Version Range (Optional)

You can add an `astrbot_version` field in `metadata.yaml` to declare the required AstrBot version range for your plugin. The format follows dependency specifiers in `pyproject.toml` (PEP 440), and must not include a `v` prefix.

```yaml
astrbot_version: ">=4.16,<5"
```

Examples:

- `>=4.17.0`
- `>=4.16,<5`
- `~=4.17`

If you only want to declare a minimum version, use:

- `>=4.17.0`

If the current AstrBot version does not satisfy this range, the plugin will be blocked from loading with a compatibility error.
In the WebUI installation flow, you can choose to "Ignore Warning and Install" to bypass this check.

### Debugging Plugins

AstrBot uses a runtime plugin injection mechanism. Therefore, when debugging plugins, you need to start the AstrBot main application.

You can use AstrBot's hot reload feature to streamline the development process.

After modifying the plugin code, you can find your plugin in the AstrBot WebUI's plugin management section, click the `...` button in the upper right corner, and select `Reload Plugin`.

If the plugin fails to load due to code errors or other reasons, you can also click **"Try one-click reload fix"** in the error prompt on the admin panel to reload it.

### Plugin Dependency Management

Currently, AstrBot manages plugin dependencies using pip's built-in `requirements.txt` file. If your plugin requires third-party libraries, please be sure to create a `requirements.txt` file in the plugin directory and list the dependencies used, to prevent Module Not Found errors when users install your plugin.

> For the complete format of `requirements.txt`, please refer to the [pip official documentation](https://pip.pypa.io/en/stable/reference/requirements-file-format/).

## Development Principles

Thank you for contributing to the AstrBot ecosystem. Please follow these principles when developing plugins, which are also good programming practices:

- Features must be tested.
- Include comprehensive comments.
- Store persistent data in the `data` directory, not in the plugin's own directory, to prevent data loss when updating/reinstalling the plugin.
- Implement robust error handling mechanisms; don't let a single error crash the plugin.
- Before committing, please use the [ruff](https://docs.astral.sh/ruff/) tool to format your code.
- Do not use the `requests` library for network requests; use asynchronous network request libraries such as `aiohttp` or `httpx`.
- If you're extending functionality for an existing plugin, please prioritize submitting a PR to that plugin rather than creating a separate one (unless the original plugin author has stopped maintaining it).

---

# Handling Message Events

Event listeners can receive message content delivered by the platform and implement features such as commands, command groups, and event listening.

Event listener decorators are located in `astrbot.api.event.filter` and must be imported first. Please make sure to import it, otherwise it will conflict with Python's built-in `filter` higher-order function.

```py
from astrbot.api.event import filter, AstrMessageEvent
```

## Messages and Events

AstrBot receives messages delivered by messaging platforms and encapsulates them as `AstrMessageEvent` objects, which are then passed to plugins for processing.

![message-event](https://files.astrbot.app/docs/en/dev/star/guides/message-event.svg)

### Message Events

`AstrMessageEvent` is AstrBot's message event object, which stores information about the message sender, message content, etc.

### Message Object

`AstrBotMessage` is AstrBot's message object, which stores the specific content of messages delivered by the messaging platform. The `AstrMessageEvent` object contains a `message_obj` attribute to retrieve this message object.

```py{11}
class AstrBotMessage:
    '''AstrBot's message object'''
    type: MessageType  # Message type
    self_id: str  # Bot's identification ID
    session_id: str  # Session ID. Depends on the unique_session setting.
    message_id: str  # Message ID
    group_id: str = "" # Group ID, empty if it's a private chat
    sender: MessageMember  # Sender
    message: List[BaseMessageComponent]  # Message chain. For example: [Plain("Hello"), At(qq=123456)]
    message_str: str  # The most straightforward plain text message string, concatenating Plain messages (text messages) from the message chain
    raw_message: object
    timestamp: int  # Message timestamp
```

Here, `raw_message` is the **raw message object** from the messaging platform adapter.

### Message Chain

![message-chain](https://files.astrbot.app/docs/en/dev/star/guides/message-chain.svg)

A `message chain` describes the structure of a message. It's an ordered list where each element is called a `message segment`.

Common message segment types include:

- `Plain`: Text message segment
- `At`: Mention message segment
- `Image`: Image message segment
- `Record`: Audio message segment
- `Video`: Video message segment
- `File`: File message segment

Most messaging platforms support the above message segment types.

Additionally, the OneBot v11 platform (QQ personal accounts, etc.) also supports the following common message segment types:

- `Face`: Emoji message segment
- `Node`: A node in a forward message
- `Nodes`: Multiple nodes in a forward message
- `Poke`: Poke message segment

In AstrBot, message chains are represented as lists of type `List[BaseMessageComponent]`.

## Commands

![message-event-simple-command](https://files.astrbot.app/docs/en/dev/star/guides/message-event-simple-command.svg)

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("helloworld") # from astrbot.api.event.filter import command
    async def helloworld(self, event: AstrMessageEvent):
        '''This is a hello world command'''
        user_name = event.get_sender_name()
        message_str = event.message_str # Get the plain text content of the message
        yield event.plain_result(f"Hello, {user_name}!")
```

> [!TIP]
> Commands cannot contain spaces, otherwise AstrBot will parse them as a second parameter. You can use the command group feature below, or use a listener to parse the message content yourself.

## Commands with Parameters

![command-with-param](https://files.astrbot.app/docs/en/dev/star/guides/command-with-param.svg)

AstrBot will automatically parse command parameters for you.

```python
@filter.command("add")
def add(self, event: AstrMessageEvent, a: int, b: int):
    # /add 1 2 -> Result is: 3
    yield event.plain_result(f"Wow! The answer is {a + b}!")
```

## Command Groups

Command groups help you organize commands.

```python
@filter.command_group("math")
def math(self):
    pass

@math.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    # /math add 1 2 -> Result is: 3
    yield event.plain_result(f"Result is: {a + b}")

@math.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    # /math sub 1 2 -> Result is: -1
    yield event.plain_result(f"Result is: {a - b}")
```

The command group function doesn't need to implement any logic; just use `pass` directly or add comments within the function. Subcommands of the command group are registered using `command_group_name.command`.

When a user doesn't input a subcommand, an error will be reported and the tree structure of the command group will be rendered.

![image](https://files.astrbot.app/docs/source/images/plugin/image-1.png)

![image](https://files.astrbot.app/docs/source/images/plugin/898a169ae7ed0478f41c0a7d14cb4d64.png)

![image](https://files.astrbot.app/docs/source/images/plugin/image-2.png)

Theoretically, command groups can be nested infinitely!

```py
'''
math
├── calc
│   ├── add (a(int),b(int),)
│   ├── sub (a(int),b(int),)
│   ├── help (command with no parameters)
'''

@filter.command_group("math")
def math():
    pass

@math.group("calc") # Note: this is group, not command_group
def calc():
    pass

@calc.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a + b}")

@calc.command("sub")
async def sub(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a - b}")

@calc.command("help")
def calc_help(self, event: AstrMessageEvent):
    # /math calc help
    yield event.plain_result("This is a calculator plugin with add and sub commands.")
```

## Command Aliases

> Available after v3.4.28

You can add different aliases for commands or command groups:

```python
@filter.command("help", alias={'帮助', 'helpme'})
def help(self, event: AstrMessageEvent):
    yield event.plain_result("This is a calculator plugin with add and sub commands.")
```

### Event Type Filtering

#### Receive All

This will receive all events.

```python
@filter.event_message_type(filter.EventMessageType.ALL)
async def on_all_message(self, event: AstrMessageEvent):
    yield event.plain_result("Received a message.")
```

#### Group Chat and Private Chat

```python
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def on_private_message(self, event: AstrMessageEvent):
    message_str = event.message_str # Get the plain text content of the message
    yield event.plain_result("Received a private message.")
```

`EventMessageType` is an `Enum` type that contains all event types. Current event types are `PRIVATE_MESSAGE` and `GROUP_MESSAGE`.

#### Messaging Platform

```python
@filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP | filter.PlatformAdapterType.QQOFFICIAL)
async def on_aiocqhttp(self, event: AstrMessageEvent):
    '''Only receive messages from AIOCQHTTP and QQOFFICIAL'''
    yield event.plain_result("Received a message")
```

In the current version, `PlatformAdapterType` includes `AIOCQHTTP`, `QQOFFICIAL`, `GEWECHAT`, and `ALL`.

#### Admin Commands

```python
@filter.permission_type(filter.PermissionType.ADMIN)
@filter.command("test")
async def test(self, event: AstrMessageEvent):
    pass
```

Only admins can use the `test` command.

### Multiple Filters

Multiple filters can be used simultaneously by adding multiple decorators to a function. Filters use `AND` logic, meaning the function will only execute if all filters pass.

```python
@filter.command("helloworld")
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
```

### Event Hooks

> [!TIP]
> Event hooks do not support being used together with @filter.command, @filter.command_group, @filter.event_message_type, @filter.platform_adapter_type, or @filter.permission_type.

#### On Bot Initialization Complete

> Available after v3.4.34

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.on_astrbot_loaded()
async def on_astrbot_loaded(self):
    print("AstrBot initialization complete")

```

#### On LLM Request

In AstrBot's default execution flow, the `on_llm_request` hook is triggered before calling the LLM.

You can obtain the `ProviderRequest` object and modify it.

The ProviderRequest object contains all information about the LLM request, including the request text, system prompt, etc.

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest

@filter.on_llm_request()
async def my_custom_hook_1(self, event: AstrMessageEvent, req: ProviderRequest): # Note there are three parameters
    print(req) # Print the request text
    req.system_prompt += "Custom system_prompt"

```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### On LLM Response Complete

After the LLM request completes, the `on_llm_response` hook is triggered.

You can obtain the `ProviderResponse` object and modify it.

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse

@filter.on_llm_response()
async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse): # Note there are three parameters
    print(resp)
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

#### Before Sending Message

Before sending a message, the `on_decorating_result` hook is triggered.

You can implement some message decoration here, such as converting to voice, converting to image, adding prefixes, etc.

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.on_decorating_result()
async def on_decorating_result(self, event: AstrMessageEvent):
    result = event.get_result()
    chain = result.chain
    print(chain) # Print the message chain
    chain.append(Plain("!")) # Add an exclamation mark at the end of the message chain
```

> You cannot use yield to send messages here. This hook is only for decorating event.get_result().chain. If you need to send, please use the `event.send()` method directly.

#### After Message Sent

After a message is sent to the messaging platform, the `after_message_sent` hook is triggered.

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.after_message_sent()
async def after_message_sent(self, event: AstrMessageEvent):
    pass
```

> You cannot use yield to send messages here. If you need to send, please use the `event.send()` method directly.

### Priority

Commands, event listeners, and event hooks can have priority set to execute before other commands, listeners, or hooks. The default priority is `0`.

```python
@filter.command("helloworld", priority=1)
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
```

## Controlling Event Propagation

```python{6}
@filter.command("check_ok")
async def check_ok(self, event: AstrMessageEvent):
    ok = self.check() # Your own logic
    if not ok:
        yield event.plain_result("Check failed")
        event.stop_event() # Stop event propagation
```

When event propagation is stopped, all subsequent steps will not be executed.

Assuming there's a plugin A, after A terminates event propagation, all subsequent operations will not be executed, such as executing other plugins' handlers or requesting the LLM.

---

# Sending Messages

## Passive Messages

Passive messages refer to the bot responding to messages reactively.

```python
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.plain_result("你好！")

    yield event.image_result("path/to/image.jpg") # Send an image
    yield event.image_result("https://example.com/image.jpg") # Send an image from URL, must start with http or https
```

## Active Messages

Active messages refer to the bot proactively pushing messages. Some platforms may not support active message sending.

For scheduled tasks or when you don't want to send messages immediately, you can use `event.unified_msg_origin` to get a string and store it, then use `self.context.send_message(unified_msg_origin, chains)` to send messages when needed.

```python
from astrbot.api.event import MessageChain

@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    umo = event.unified_msg_origin
    message_chain = MessageChain().message("Hello!").file_image("path/to/image.jpg")
    await self.context.send_message(event.unified_msg_origin, message_chain)
```

With this feature, you can store the `unified_msg_origin` and send messages when needed.

> [!TIP]
> About unified_msg_origin.
> `unified_msg_origin` is a string that records the unique ID of a session. AstrBot uses it to identify which messaging platform and which session it belongs to. This allows messages to be sent to the correct session when using `send_message`. For more about MessageChain, see the next section.

## Rich Media Messages

AstrBot supports sending rich media messages such as images, audio, videos, etc. Use `MessageChain` to construct messages.

```python
import astrbot.api.message_components as Comp

@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    chain = [
        Comp.At(qq=event.get_sender_id()), # Mention the message sender
        Comp.Plain("Check out this image:"),
        Comp.Image.fromURL("https://example.com/image.jpg"), # Send image from URL
        Comp.Image.fromFileSystem("path/to/image.jpg"), # Send image from local file system
        Comp.Plain("This is an image.")
    ]
    yield event.chain_result(chain)
```

The above constructs a `message chain`, which will ultimately send a message containing both images and text while preserving the order.

> [!TIP]
> In the aiocqhttp message adapter, for messages of type `plain`, the `strip()` method is used during sending to remove spaces and line breaks. You can add zero-width spaces `\u200b` before and after the message to resolve this issue.

Similarly,

**File**

```py
Comp.File(file="path/to/file.txt", name="file.txt") # Not supported by some platforms
```

**Audio Record**

```py
path = "path/to/record.wav" # Currently only accepts wav format, please convert other formats yourself
Comp.Record(file=path, url=path)
```

**Video**

```py
path = "path/to/video.mp4"
Comp.Video.fromFileSystem(path=path)
Comp.Video.fromURL(url="https://example.com/video.mp4")
```

## Sending Video Messages

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Video
    # fromFileSystem requires the user's protocol client and bot to be on the same system.
    music = Video.fromFileSystem(
        path="test.mp4"
    )
    # More universal approach
    music = Video.fromURL(
        url="https://example.com/video.mp4"
    )
    yield event.chain_result([music])
```

![Sending video messages](https://files.astrbot.app/docs/source/images/plugin/db93a2bb-671c-4332-b8ba-9a91c35623c2.png)

## Sending Group Forward Messages

> Most platforms do not support this message type. Current support: OneBot v11

You can send group forward messages as follows.

```py
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Node, Plain, Image
    node = Node(
        uin=905617992,
        name="Soulter",
        content=[
            Plain("hi"),
            Image.fromFileSystem("test.jpg")
        ]
    )
    yield event.chain_result([node])
```

![Sending group forward messages](https://files.astrbot.app/docs/source/images/plugin/image-4.png)

---

# AI

AstrBot provides built-in support for multiple Large Language Model (LLM) providers and offers a unified interface, making it convenient for plugin developers to access various LLM services.

You can use the LLM / Agent interfaces provided by AstrBot to implement your own intelligent agents.

Starting from version `v4.5.7`, we've made significant improvements to the way LLM providers are invoked. We recommend using the new approach, which is more concise and supports additional features. The legacy invocation method remains documented in the previous Chinese-only guide.

## Getting the Chat Model ID for the Current Session

> [!TIP]
> Added in v4.5.7

```py
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo=umo)
```

## Invoking Large Language Models

> [!TIP]
> Added in v4.5.7


```py
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id, # Chat model ID
    prompt="Hello, world!",
)
# print(llm_resp.completion_text) # Get the returned text
```

## Defining Tools

Tools enable large language models to invoke external capabilities.

```py
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class BilibiliTool(FunctionTool[AstrAgentContext]):
    name: str = "bilibili_videos"  # Tool name
    description: str = "A tool to fetch Bilibili videos."  # Tool description
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Keywords to search for Bilibili videos.",
                },
            },
            "required": ["keywords"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        return "1. Video Title: How to Use AstrBot\nVideo Link: xxxxxx"
```

## Invoking Agents

> [!TIP]
> Added in v4.5.7


An Agent can be defined as a combination of system_prompt + tools + llm, enabling more sophisticated intelligent behavior.

After defining the Tool above, you can invoke an Agent as follows:

```py
llm_resp = await self.context.tool_loop_agent(
    event=event,
    chat_provider_id=prov_id,
    prompt="Search for videos related to AstrBot on Bilibili.",
    tools=ToolSet([BilibiliTool()]),
    max_steps=30, # Maximum agent execution steps
    tool_call_timeout=60, # Tool invocation timeout
)
# print(llm_resp.completion_text) # Get the returned text
```

`tool_loop_agent()` method automatically handles the loop of tool invocations and LLM requests until the model stops calling tools or the maximum number of steps is reached.

## Multi-Agent

> [!TIP]
> Added in v4.5.7


Multi-Agent systems decompose complex applications into multiple specialized agents that collaborate to solve problems. Unlike relying on a single agent to handle every step, multi-agent architectures allow smaller, more focused agents to be composed into coordinated workflows. We implement multi-agent systems using the `agent-as-tool` pattern.

In the example below, we define a Main Agent responsible for delegating tasks to different Sub-Agents based on user queries. Each Sub-Agent focuses on specific tasks, such as retrieving weather information.

![multi-agent-example-1](https://files.astrbot.app/docs/en/dev/star/guides/multi-agent-example-1.svg)

Define Tools:

```py
@dataclass
class AssignAgentTool(FunctionTool[AstrAgentContext]):
    """Main agent uses this tool to decide which sub-agent to delegate a task to."""

    name: str = "assign_agent"
    description: str = "Assign an agent to a task based on the given query"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to call the sub-agent with.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> str | CallToolResult:
        # Here you would implement the actual agent assignment logic.
        # For demonstration purposes, we'll return a dummy response.
        return "Based on the query, you should assign agent 1."


@dataclass
class WeatherTool(FunctionTool[AstrAgentContext]):
    """In this example, sub agent 1 uses this tool to get weather information."""

    name: str = "weather"
    description: str = "Get weather information for a location"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city to get weather information for.",
                },
            },
            "required": ["city"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> str | CallToolResult:
        city = kwargs["city"]
        # Here you would implement the actual weather fetching logic.
        # For demonstration purposes, we'll return a dummy response.
        return f"The current weather in {city} is sunny with a temperature of 25°C."


@dataclass
class SubAgent1(FunctionTool[AstrAgentContext]):
    """Define a sub-agent as a function tool."""

    name: str = "subagent1_name"
    description: str = "subagent1_description"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to call the sub-agent with.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> str | CallToolResult:
        ctx = context.context.context
        event = context.context.event
        logger.info(f"the llm context messages: {context.messages}")
        llm_resp = await ctx.tool_loop_agent(
            event=event,
            chat_provider_id=await ctx.get_current_chat_provider_id(
                event.unified_msg_origin
            ),
            prompt=kwargs["query"],
            tools=ToolSet([WeatherTool()]),
            max_steps=30,
        )
        return llm_resp.completion_text


@dataclass
class SubAgent2(FunctionTool[AstrAgentContext]):
    """Define a sub-agent as a function tool."""

    name: str = "subagent2_name"
    description: str = "subagent2_description"
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to call the sub-agent with.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> str | CallToolResult:
        return "I am useless :(, you shouldn't call me :("
```

Then, similarly, invoke the Agent using the `tool_loop_agent()` method:

```py
@filter.command("test")
async def test(self, event: AstrMessageEvent):
    umo = event.unified_msg_origin
    prov_id = await self.context.get_current_chat_provider_id(umo)
    llm_resp = await self.context.tool_loop_agent(
        event=event,
        chat_provider_id=prov_id,
        prompt="Test calling sub-agent for Beijing's weather information.",
        system_prompt=(
            "You are the main agent. Your task is to delegate tasks to sub-agents based on user queries."
            "Before delegating, use the 'assign_agent' tool to determine which sub-agent is best suited for the task."
        ),
        tools=ToolSet([SubAgent1(), SubAgent2(), AssignAgentTool()]),
        max_steps=30,
    )
    yield event.plain_result(llm_resp.completion_text)
```

## Conversation Manager

### Getting the Current LLM Conversation History for a Session

```py
from astrbot.core.conversation_mgr import Conversation

uid = event.unified_msg_origin
conv_mgr = self.context.conversation_manager
curr_cid = await conv_mgr.get_curr_conversation_id(uid)
conversation = await conv_mgr.get_conversation(uid, curr_cid)  # Conversation
```

::: details Conversation 类型定义

```py
@dataclass
class Conversation:
    """The conversation entity representing a chat session."""

    platform_id: str
    """The platform ID in AstrBot"""
    user_id: str
    """The user ID associated with the conversation."""
    cid: str
    """The conversation ID, in UUID format."""
    history: str = ""
    """The conversation history as a string."""
    title: str | None = ""
    """The title of the conversation. For now, it's only used in WebChat."""
    persona_id: str | None = ""
    """The persona ID associated with the conversation."""
    created_at: int = 0
    """The timestamp when the conversation was created."""
    updated_at: int = 0
    """The timestamp when the conversation was last updated."""
```

:::

### Main Methods

#### `new_conversation`

- **Usage**  
  Create a new conversation in the current session and automatically switch to it.
- **Arguments**  
  - `unified_msg_origin: str` – In the format `platform_name:message_type:session_id`  
  - `platform_id: str | None` – Platform identifier, defaults to parsing from `unified_msg_origin`  
  - `content: list[dict] | None` – Initial message history  
  - `title: str | None` – Conversation title  
  - `persona_id: str | None` – Associated persona ID
- **Returns**  
  `str` – Newly generated UUID conversation ID

#### `switch_conversation`

- **Usage**  
  Switch the session to a specified conversation.
- **Arguments**  
  - `unified_msg_origin: str`  
  - `conversation_id: str`
- **Returns**  
  `None`

#### `delete_conversation`

- **Usage**  
  Delete a conversation from the session; if `conversation_id` is `None`, deletes the current conversation.
- **Arguments**  
  - `unified_msg_origin: str`  
  - `conversation_id: str | None`
- **Returns**  
  `None`

#### `get_curr_conversation_id`

- **Usage**  
  Get the conversation ID currently in use by the session.
- **Arguments**  
  - `unified_msg_origin: str`
- **Returns**  
  `str | None` – Current conversation ID, returns `None` if it doesn't exist

#### `get_conversation`

- **Usage**  
  Get the complete object for a specified conversation; automatically creates it if it doesn't exist and `create_if_not_exists=True`.
- **Arguments**  
  - `unified_msg_origin: str`  
  - `conversation_id: str`  
  - `create_if_not_exists: bool = False`
- **Returns**  
  `Conversation | None`

#### `get_conversations`

- **Usage**  
  Retrieve the complete list of conversations for a user or platform.
- **Arguments**  
  - `unified_msg_origin: str | None` – When `None`, does not filter by user  
  - `platform_id: str | None`
- **Returns**  
  `List[Conversation]`

#### `update_conversation`

- **Usage**  
  Update the title, history, or persona_id of a conversation.
- **Arguments**  
  - `unified_msg_origin: str`  
  - `conversation_id: str | None` – Uses the current conversation when `None`  
  - `history: list[dict] | None`  
  - `title: str | None`  
  - `persona_id: str | None`
- **Returns**  
  `None`

## Persona Manager

`PersonaManager` is responsible for unified loading, caching, and providing CRUD interfaces for all Personas, while maintaining compatibility with the legacy persona format (v3) from before AstrBot 4.x.  
During initialization, it automatically reads all personas from the database and generates v3-compatible data for seamless use with legacy code.

```py
persona_mgr = self.context.persona_manager
```

### Main Methods

#### `get_persona`

- **Usage**
  Get persona data by persona ID.
- **Arguments**
  - `persona_id: str` – Persona ID
- **Returns**
  `Persona` – Persona data, returns None if it doesn't exist
- **Raises**
  `ValueError` – Raised when it doesn't exist

#### `get_all_personas`

- **Usage**  
  Retrieve all personas from the database at once.
- **Returns**  
  `list[Persona]` – Persona list, may be empty

#### `create_persona`

- **Usage**  
  Create a new persona and immediately write it to the database; automatically refreshes the local cache upon success.
- **Arguments**  
  - `persona_id: str` – New persona ID (unique)  
  - `system_prompt: str` – System prompt  
  - `begin_dialogs: list[str]` – Optional, opening dialogs (even number of entries, alternating user/assistant)  
  - `tools: list[str]` – Optional, list of allowed tools; `None`=all tools, `[]`=disable all
- **Returns**  
  `Persona` – Newly created persona object
- **Raises**  
  `ValueError` – If `persona_id` already exists

#### `update_persona`

- **Usage**  
  Update any fields of an existing persona and synchronize to database and cache.
- **Arguments**  
  - `persona_id: str` – Persona ID to update  
  - `system_prompt: str` – Optional, new system prompt  
  - `begin_dialogs: list[str]` – Optional, new opening dialogs  
  - `tools: list[str]` – Optional, new tool list; semantics same as `create_persona`
- **Returns**  
  `Persona` – Updated persona object
- **Raises**  
  `ValueError` – If `persona_id` doesn't exist

#### `delete_persona`

- **Usage**  
  Delete the specified persona and clean up both database and cache.
- **Arguments**  
  - `persona_id: str` – Persona ID to delete
- **Raises**  
  `ValueError` – If `persona_id` doesn't exist

#### `get_default_persona_v3`

- **Usage**  
  Get the default persona (v3 format) to use based on the current session configuration.  
  Falls back to `DEFAULT_PERSONALITY` if configuration doesn't specify one or the specified persona doesn't exist.
- **Arguments**  
  - `umo: str | MessageSession | None` – Session identifier, used to read user-level configuration
- **Returns**  
  `Personality` – Default persona object in v3 format

::: details Persona / Personality 类型定义

```py

class Persona(SQLModel, table=True):
    """Persona is a set of instructions for LLMs to follow.

    It can be used to customize the behavior of LLMs.
    """

    __tablename__ = "personas"

    id: int = Field(primary_key=True, sa_column_kwargs={"autoincrement": True})
    persona_id: str = Field(max_length=255, nullable=False)
    system_prompt: str = Field(sa_type=Text, nullable=False)
    begin_dialogs: Optional[list] = Field(default=None, sa_type=JSON)
    """a list of strings, each representing a dialog to start with"""
    tools: Optional[list] = Field(default=None, sa_type=JSON)
    """None means use ALL tools for default, empty list means no tools, otherwise a list of tool names."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            name="uix_persona_id",
        ),
    )


class Personality(TypedDict):
    """LLM Persona class.

    Starting from v4.0.0 and later, it's recommended to use the Persona class above. Additionally, the mood_imitation_dialogs field has been deprecated.
    """

    prompt: str
    name: str
    begin_dialogs: list[str]
    mood_imitation_dialogs: list[str]
    """Mood imitation dialog preset. Deprecated since v4.0.0 and later."""
    tools: list[str] | None
    """Tool list. None means use all tools, empty list means don't use any tools"""
```

:::

---

# Plugin Configuration

As plugin functionality grows, you may need to define configurations to allow users to customize plugin behavior.

AstrBot provides "powerful" configuration parsing and visualization features. Users can configure plugins directly in the management panel without modifying code.

## Configuration Definition

To register configurations, first add a `_conf_schema.json` JSON file in your plugin directory.

The file content is a `Schema` that represents the configuration. The Schema is in JSON format, for example:

```json
{
  "token": {
    "description": "Bot Token",
    "type": "string",
  },
  "sub_config": {
    "description": "Test nested configuration",
    "type": "object",
    "hint": "xxxx",
    "items": {
      "name": {
        "description": "testsub",
        "type": "string",
        "hint": "xxxx"
      },
      "id": {
        "description": "testsub",
        "type": "int",
        "hint": "xxxx"
      },
      "time": {
        "description": "testsub",
        "type": "int",
        "hint": "xxxx",
        "default": 123
      }
    }
  }
}
```

- `type`: **Required**. The type of the configuration. Supports `string`, `text`, `int`, `float`, `bool`, `object`, `list`, `dict`, `template_list`, `file`. When the type is `text`, it will be visualized as a larger resizable textarea component to accommodate large text.
- `description`: Optional. Description of the configuration. A one-sentence description of the configuration's behavior is recommended.
- `hint`: Optional. Hint information for the configuration, displayed in the question mark button on the right in the image above, shown when hovering over it.
- `obvious_hint`: Optional. Whether the configuration hint should be prominently displayed, like `token` in the image above.
- `default`: Optional. The default value of the configuration. If the user hasn't configured it, the default value will be used. Default values: int is 0, float is 0.0, bool is False, string is "", object is {}, list is [].
- `items`: Optional. If the configuration type is `object`, the `items` field needs to be added. The content of `items` is the sub-Schema of this configuration item. Theoretically, it can be nested infinitely, but excessive nesting is not recommended.
- `invisible`: Optional. Whether the configuration is hidden. Default is `false`. If set to `true`, it will not be displayed in the management panel.
- `options`: Optional. A list, such as `"options": ["chat", "agent", "workflow"]`. Provides dropdown list options.
- `editor_mode`: Optional. Whether to enable code editor mode. Requires AstrBot >= `v3.5.10`. Versions below this won't report errors but won't take effect. Default is false.
- `editor_language`: Optional. The code language for the code editor, defaults to `json`.
- `editor_theme`: Optional. The theme for the code editor. Options are `vs-light` (default) and `vs-dark`.
- `_special`: Optional. Used to call AstrBot's visualization features for provider selection, persona selection, knowledge base selection, etc. See details below.

When the code editor is enabled, it looks like this:

![editor_mode](https://files.astrbot.app/docs/source/images/plugin/image-6.png)

![editor_mode_fullscreen](https://files.astrbot.app/docs/source/images/plugin/image-7.png)

The **_special** field is only available after v4.0.0. Currently supports `select_provider`, `select_provider_tts`, `select_provider_stt`, `select_persona`, allowing users to quickly select model providers, personas, and other data already configured in the WebUI. Results are all strings. Using select_provider as an example, it will present the following effect:

![image](https://files.astrbot.app/docs/source/images/plugin/image-select-provider.png)

### `file` type schema

Introduced in v4.13.0, this allows plugins to define file-upload configuration items to guide users to upload files required by the plugin.

```json
{
  "demo_files": {
    "type": "file",
    "description": "Uploaded files for demo",
    "default": [],
    "file_types": ["pdf", "docx"]
  }
}
```

### `dict` type schema

Used to visualize editing a Python `dict` type configuration. For example, AstrBot Core's custom extra body parameter configuration:

```py
"custom_extra_body": {
  "description": "Custom request body parameters",
  "type": "dict",
  "items": {},
  "hint": "Used to add extra parameters to requests, such as temperature, top_p, max_tokens, etc.",
  "template_schema": {
      "temperature": {
          "name": "Temperature",
          "description": "Temperature parameter",
          "hint": "Controls randomness of output, typically 0-2. Higher is more random.",
          "type": "float",
          "default": 0.6,
          "slider": {"min": 0, "max": 2, "step": 0.1},
      },
      "top_p": {
          "name": "Top-p",
          "description": "Top-p sampling",
          "hint": "Nucleus sampling parameter, typically 0-1. Controls probability mass considered.",
          "type": "float",
          "default": 1.0,
          "slider": {"min": 0, "max": 1, "step": 0.01},
      },
      "max_tokens": {
          "name": "Max Tokens",
          "description": "Maximum tokens",
          "hint": "Maximum number of tokens to generate.",
          "type": "int",
          "default": 8192,
      },
  },
}
```

### `template_list` type schema

> [!NOTE]
> Introduced in v4.10.4. For more details see: [#4208](https://github.com/AstrBotDevs/AstrBot/pull/4208)

Plugin developers can add a template-style configuration to `_conf_schema` in the following format (somewhat similar to nested configs):

```json
 "field_id": {
  "type": "template_list",
  "description": "Template List Field",
  "templates": {
    "template_1": {
        "name": "Template One",
        "hint":"hint",
        "items": {
          "attr_a": {
            "description": "Attribute A",
            "type": "int",
            "default": 10
          },
          "attr_b": {
            "description": "Attribute B",
            "hint": "This is a boolean attribute",
            "type": "bool",
            "default": true
          }
        }
      },
    "template_2": {
      "name": "Template Two",
      "hint":"hint",
      "items": {
        "attr_c": {
          "description": "Attribute A",
          "type": "int",
          "default": 10
        },
        "attr_d": {
          "description": "Attribute B",
          "hint": "This is a boolean attribute",
          "type": "bool",
          "default": true
        }
      }
    }
  }
}
```

Saved config example:

```json
"field_id": [
    {
        "__template_key": "template_1",
        "attr_a": 10,
        "attr_b": true
    },
    {
        "__template_key": "template_2",
        "attr_c": 10,
        "attr_d": true
    }
]
```

<img width="1000" alt="image" src="https://github.com/user-attachments/assets/74876d30-11a4-491b-a7a0-8ebe8d603782" />


## Using Configuration in Plugins

When loading plugins, AstrBot will check if there's a `_conf_schema.json` file in the plugin directory. If it exists, it will automatically parse the configuration and save it under `data/config/<plugin_name>_config.json` (a configuration file entity created according to the Schema), and pass it to `__init__()` when instantiating the plugin class.

```py
from astrbot.api import AstrBotConfig

class ConfigPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig): # AstrBotConfig inherits from Dict and has all dictionary methods
        super().__init__(context)
        self.config = config
        print(self.config)

        # Supports direct configuration saving
        # self.config.save_config() # Save configuration
```

## Configuration Updates

When you update the Schema across different versions, AstrBot will recursively inspect the configuration items in the Schema, automatically adding default values for missing items and removing those that no longer exist.

---

# Session Control

> v3.4.36 and above

Why do we need session control? Consider a Chinese idiom chain game plugin where a user or group needs to have multiple conversations with the bot rather than a one-time command. This is when session control becomes necessary.

```txt
User: /idiom-chain
Bot: Please send an idiom
User: One horse takes the lead (一马当先)
Bot: Foresight (先见之明)
User: Keen observation (明察秋毫)
...
```

AstrBot provides out-of-the-box session control functionality:

Import:

```py
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionController,
)
```

Code within the handler can be written as follows:

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("idiom-chain")
async def handle_empty_mention(self, event: AstrMessageEvent):
    """Idiom chain game implementation"""
    try:
        yield event.plain_result("Please send an idiom~")

        # How to use the session controller
        @session_waiter(timeout=60, record_history_chains=False) # Register a session controller with a 60-second timeout, without recording message history
        async def empty_mention_waiter(controller: SessionController, event: AstrMessageEvent):
            idiom = event.message_str # The idiom sent by the user, e.g., "one horse takes the lead"

            if idiom == "exit":   # If the user wants to exit the idiom chain game by typing "exit"
                await event.send(event.plain_result("Exited the idiom chain game~"))
                controller.stop()    # Stop the session controller, which will end immediately.
                return

            if len(idiom) != 4:   # If the user's input is not a 4-character idiom
                await event.send(event.plain_result("The idiom must be four characters~"))  # Send a reply, cannot use yield
                return
                # Exit the current method without executing subsequent logic, but the session is not interrupted; subsequent user input will still enter the current session

            # ...
            message_result = event.make_result()
            message_result.chain = [Comp.Plain("Foresight")] # import astrbot.api.message_components as Comp
            await event.send(message_result) # Send a reply, cannot use yield

            controller.keep(timeout=60, reset_timeout=True) # Reset timeout to 60s. If not reset, it will continue the previous timeout countdown.

            # controller.stop() # Stop the session controller, which will end immediately.
            # If history chains are recorded, you can retrieve them via controller.get_history_chains()

        try:
            await empty_mention_waiter(event)
        except TimeoutError as _: # When timeout occurs, the session controller will raise TimeoutError
            yield event.plain_result("You timed out!")
        except Exception as e:
            yield event.plain_result("An error occurred, please contact the administrator: " + str(e))
        finally:
            event.stop_event()
    except Exception as e:
        logger.error("handle_empty_mention error: " + str(e))
```

Once the session controller is activated, messages subsequently sent by that sender will first be processed by the `empty_mention_waiter` function you defined above, until the session controller is stopped or times out.

## SessionController

Used by developers to control whether a session should end, and to retrieve message history chains.

- keep(): Keep this session alive
  - timeout (float): Required. Session timeout duration.
  - reset_timeout (bool): When set to True, it resets the timeout; timeout must be > 0, if <= 0 the session ends immediately. When set to False, it maintains the original timeout; new timeout = remaining timeout + timeout (can be < 0)
- stop(): End this session
- get_history_chains() -> List[List[Comp.BaseMessageComponent]]: Retrieve message history chains

## Custom Session ID Filter

By default, the AstrBot session controller uses `sender_id` (the sender's ID) as the identifier for distinguishing different sessions. If you want to treat an entire group as one session, you need to customize the session ID filter.

```py
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import (
    session_waiter,
    SessionFilter,
    SessionController,
)

# Using the handler from above
# ...
class CustomFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return event.get_group_id() if event.get_group_id() else event.unified_msg_origin

await empty_mention_waiter(event, session_filter=CustomFilter()) # Pass in session_filter here
# ...
```

After this setup, when a user in a group sends a message, the session controller will treat the entire group as one session, and messages from other users in the group will also be considered part of the same session.

You can even use this feature to enable team-based activities within groups!

---

# Plugin Storage

## Simple KV Storage

> [!TIP]
> Requires AstrBot version >= 4.9.2.

Plugins can use AstrBot's simple key-value store to persist configuration or temporary data. The storage is scoped per plugin, so each plugin has its own isolated space.

```py
class Main(star.Star):
    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """Aloha!"""
        await self.put_kv_data("greeted", True)
        greeted = await self.get_kv_data("greeted", False)
        await self.delete_kv_data("greeted")
```


## Large File Storage Convention

To keep large file handling consistent, store large files under `data/plugin_data/{plugin_name}/`.

You can fetch the plugin data directory with:

```py
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

plugin_data_path = get_astrbot_data_path() / "plugin_data" / self.name  # self.name is the plugin name; available in v4.9.2 and above. For lower versions, specify the plugin name yourself.
```

---

# Text to Image

> [!TIP]
> For easier development, you can use the [AstrBot Text2Image Playground](https://t2i-playground.astrbot.app/) for online visual editing and testing of HTML templates.

## Basic Usage

AstrBot supports rendering text into images.

```python
@filter.command("image") # Register an /image command that accepts a text parameter.
async def on_aiocqhttp(self, event: AstrMessageEvent, text: str):
    url = await self.text_to_image(text) # text_to_image() is a method of the Star class.
    # path = await self.text_to_image(text, return_url = False) # If you want to save the image locally
    yield event.image_result(url)

```

![image](https://files.astrbot.app/docs/source/images/plugin/image-3.png)

## Customization (HTML-Based)

If you find the default rendered images insufficiently aesthetic, you can use custom HTML templates to render images.

AstrBot supports rendering text-to-image templates using `HTML + Jinja2`.

```py{7}
# Custom Jinja2 template with CSS support
TMPL = '''
<div style="font-size: 32px;">
<h1 style="color: black">Todo List</h1>

<ul>
{% for item in items %}
    <li>{{ item }}</li>
{% endfor %}
</div>
'''

@filter.command("todo")
async def custom_t2i_tmpl(self, event: AstrMessageEvent):
    options = {} # Optionally pass rendering options.
    url = await self.html_render(TMPL, {"items": ["Eat", "Sleep", "Play Genshin"]}, options=options) # The second parameter is the data for Jinja2 rendering
    yield event.image_result(url)
```

The result:

![image](https://files.astrbot.app/docs/source/images/plugin/fcc2dcb472a91b12899f617477adc5c7.png)

This is just a simple example. Thanks to the powerful capabilities of HTML and DOM renderers, you can create more complex and visually appealing designs. Additionally, Jinja2 supports syntax for loops, conditionals, and more to accommodate data structures like lists and dictionaries. You can learn more about Jinja2 online.

**Image Rendering Options (options)**:

Please refer to Playwright's [screenshot](https://playwright.dev/python/docs/api/class-page#page-screenshot) API.

- `timeout` (float, optional): Screenshot timeout duration.
- `type` (Literal["jpeg", "png"], optional): Screenshot image type.
- `quality` (int, optional): Screenshot quality, only applicable to JPEG format images.
- `omit_background` (bool, optional): Whether to hide the default white background, allowing transparent screenshots. Only applicable to PNG format.
- `full_page` (bool, optional): Whether to capture the entire page rather than just the viewport size. Defaults to True.
- `clip` (dict, optional): The region to crop after taking the screenshot. Refer to Playwright's screenshot API.
- `animations`: (Literal["allow", "disabled"], optional): Whether to allow CSS animations to play.
- `caret`: (Literal["hide", "initial"], optional): When set to hide, the text cursor will be hidden during the screenshot. Defaults to hide.
- `scale`: (Literal["css", "device"], optional): Page scaling setting. When set to css, device resolution maps one-to-one with CSS pixels, which may result in smaller screenshots on high-DPI screens. When set to device, scaling is based on the device's screen scaling settings or the device_scale_factor parameter in the current Playwright Page/Context.

---

# Publishing Plugins to the Plugin Marketplace

After completing your plugin development, you can choose to publish it to the AstrBot Plugin Marketplace, allowing more users to benefit from your work.

AstrBot uses GitHub to host plugins, so you'll need to push your plugin code to the GitHub plugin repository you created earlier.

You can submit your plugin by visiting the [AstrBot Plugin Marketplace](https://plugins.astrbot.app). Once on the website, click the `+` button in the bottom-right corner, fill in the basic information, author details, repository information, and other required fields. Then click the `Submit to GITHUB` button. You will be redirected to the AstrBot repository's Issue submission page. Please verify that all information is correct, then click the `Create` button to complete the plugin publication process.

![fill out the form](https://files.astrbot.app/docs/source/images/plugin-publish/image.png)

---

# AstrBot Configuration File

## data/cmd_config.json

AstrBot's configuration file is a JSON format file. AstrBot reads this file at startup and initializes based on the settings within. Its path is `data/cmd_config.json`.

> Since AstrBot v4.0.0, we introduced the concept of [multiple configuration files](https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6). `data/cmd_config.json` serves as the default configuration `default`. Other configuration files you create in the WebUI are stored in the `data/config/` directory, starting with `abconf_`.

The default AstrBot configuration is as follows:

```jsonc
{
    "config_version": 2,
    "platform_settings": {
        "unique_session": False,
        "rate_limit": {
            "time": 60,
            "count": 30,
            "strategy": "stall",  # stall, discard
        },
        "reply_prefix": "",
        "forward_threshold": 1500,
        "enable_id_white_list": True,
        "id_whitelist": [],
        "id_whitelist_log": True,
        "wl_ignore_admin_on_group": True,
        "wl_ignore_admin_on_friend": True,
        "reply_with_mention": False,
        "reply_with_quote": False,
        "path_mapping": [],
        "segmented_reply": {
            "enable": False,
            "only_llm_result": True,
            "interval_method": "random",
            "interval": "1.5,3.5",
            "log_base": 2.6,
            "words_count_threshold": 150,
            "regex": ".*?[。？！~…]+|.+$",
            "content_cleanup_rule": "",
        },
        "no_permission_reply": True,
        "empty_mention_waiting": True,
        "empty_mention_waiting_need_reply": True,
        "friend_message_needs_wake_prefix": False,
        "ignore_bot_self_message": False,
        "ignore_at_all": False,
    },
    "provider": [],
    "provider_settings": {
        "enable": True,
        "default_provider_id": "",
        "default_image_caption_provider_id": "",
        "image_caption_prompt": "Please describe the image using Chinese.",
        "provider_pool": ["*"],  # "*" means use all available providers
        "wake_prefix": "",
        "web_search": False,
        "websearch_provider": "default",
        "websearch_tavily_key": [],
        "web_search_link": False,
        "display_reasoning_text": False,
        "identifier": False,
        "group_name_display": False,
        "datetime_system_prompt": True,
        "default_personality": "default",
        "persona_pool": ["*"],
        "prompt_prefix": "{{prompt}}",
        "max_context_length": -1,
        "dequeue_context_length": 1,
        "streaming_response": False,
        "show_tool_use_status": False,
        "streaming_segmented": False,
        "max_agent_step": 30,
        "tool_call_timeout": 60,
    },
    "provider_stt_settings": {
        "enable": False,
        "provider_id": "",
    },
    "provider_tts_settings": {
        "enable": False,
        "provider_id": "",
        "dual_output": False,
        "use_file_service": False,
    },
    "provider_ltm_settings": {
        "group_icl_enable": False,
        "group_message_max_cnt": 300,
        "image_caption": False,
        "active_reply": {
            "enable": False,
            "method": "possibility_reply",
            "possibility_reply": 0.1,
            "whitelist": [],
        },
    },
    "content_safety": {
        "also_use_in_response": False,
        "internal_keywords": {"enable": True, "extra_keywords": []},
        "baidu_aip": {"enable": False, "app_id": "", "api_key": "", "secret_key": ""},
    },
    "admins_id": ["astrbot"],
    "t2i": False,
    "t2i_word_threshold": 150,
    "t2i_strategy": "remote",
    "t2i_endpoint": "",
    "t2i_use_file_service": False,
    "t2i_active_template": "base",
    "http_proxy": "",
    "no_proxy": ["localhost", "127.0.0.1", "::1"],
    "dashboard": {
        "enable": True,
        "username": "astrbot",
        "password": "77b90590a8945a7d36c963981a307dc9",
        "jwt_secret": "",
        "host": "0.0.0.0",
        "port": 6185,
    },
    "platform": [],
    "platform_specific": {
        # Platform-specific settings: categorized by platform, then by feature group
        "lark": {
            "pre_ack_emoji": {"enable": False, "emojis": ["Typing"]},
        },
        "telegram": {
            "pre_ack_emoji": {"enable": False, "emojis": ["✍️"]},
        },
    },
    "wake_prefix": ["/"],
    "log_level": "INFO",
    "trace_enable": False,
    "pip_install_arg": "",
    "pypi_index_url": "https://mirrors.aliyun.com/pypi/simple/",
    "persona": [],  # deprecated
    "timezone": "Asia/Shanghai",
    "callback_api_base": "",
    "default_kb_collection": "",  # Default knowledge base name
    "plugin_set": ["*"],  # "*" means use all available plugins, empty list means none
}
```

## Field Details

### `config_version`

Configuration version, do not modify.

### `platform_settings`

General settings for message platform adapters.

#### `platform_settings.unique_session`

Whether to enable session isolation. Default is `false`. When enabled, each person's conversation context in groups or channels is independent.

#### `platform_settings.rate_limit`

Strategy when message rate exceeds limits. `time` is the window, `count` is the number of messages, and `strategy` is the limit strategy. `stall` means wait, `discard` means drop.

#### `platform_settings.reply_prefix`

Fixed prefix string when replying to messages. Default is empty.

#### `platform_settings.forward_threshold`

> Currently only applicable to the QQ platform adapter.

Message forwarding threshold. When the reply content exceeds a certain number of characters, the bot will fold the message into a QQ group "forwarded message" to prevent spamming.

#### `platform_settings.enable_id_white_list`

Whether to enable the ID whitelist. Default is `true`. When enabled, only messages from IDs in the whitelist will be processed.

#### `platform_settings.id_whitelist`

ID whitelist. If filled, only message events from the specified IDs will be processed. Empty means the whitelist filter is not enabled. You can use the `/sid` command to get the session ID on a platform.

Session IDs can also be found in AstrBot logs; when a message fails the whitelist, an INFO level log is output, e.g., `aiocqhttp:GroupMessage:547540978`.

#### `platform_settings.id_whitelist_log`

Whether to print logs for messages that fail the ID whitelist. Default is `true`.

#### `platform_settings.wl_ignore_admin_on_group` & `platform_settings.wl_ignore_admin_on_friend`

- `wl_ignore_admin_on_group`: Whether group messages from admins bypass the ID whitelist. Default is `true`.

- `wl_ignore_admin_on_friend`: Whether private messages from admins bypass the ID whitelist. Default is `true`.

#### `platform_settings.reply_with_mention`

Whether to @ mention the user when replying. Default is `false`.

#### `platform_settings.reply_with_quote`

Whether to quote the user's message when replying. Default is `false`.

#### `platform_settings.path_mapping`

*This configuration item has been deprecated since v4.0.0.*

List of path mappings. Used to replace file paths in messages. Each mapping item contains `from` and `to` fields, indicating that `from` in the message path is replaced with `to`.

#### `platform_settings.segmented_reply`

Segmented reply settings.

- `enable`: Whether to enable segmented replies. Default is `false`.
- `only_llm_result`: Whether to only segment replies generated by the LLM. Default is `true`.
- `interval_method`: Method for segmentation intervals. Options are `random` and `log`. Default is `random`.
- `interval`: Interval time for segmentation. For `random`, fill in two comma-separated numbers representing min and max intervals (seconds). For `log`, fill in one number representing the log base. Default is `"1.5,3.5"`.
- `log_base`: Log base, only applicable when `interval_method` is `log`. Default is `2.6`.
- `words_count_threshold`: Character limit for segmented replies. Only messages shorter than this value will be segmented; longer messages will be sent directly (unsegmented). Default is `150`.
- `regex`: Used to split a message. By default, it splits based on punctuation like periods and question marks. `re.findall(r'<regex>', text)`. Default is `".*?[。？！~…]+|.+$"`.
- `content_cleanup_rule`: Removes specified content from segments. Supports regex. For example, `[。？！]` will remove all periods, question marks, and exclamation points. `re.sub(r'<regex>', '', text)`.

#### `platform_settings.no_permission_reply`

Whether to reply with a "no permission" prompt when a user lacks authority. Default is `true`.

#### `platform_settings.empty_mention_waiting`

Whether to enable the empty @ waiting mechanism. Default is `true`. When enabled, if a user sends a message containing only an @ mention of the bot, the bot waits for the user to send the next message within 60 seconds and merges the two for processing. This is particularly useful on platforms that don't support sending @ and voice/images simultaneously.

#### `platform_settings.empty_mention_waiting_need_reply`

In the above item (`empty_mention_waiting`), if waiting is triggered, enabling this will make the bot immediately generate an LLM reply. Otherwise, it just waits without replying. Default is `true`.

#### `platform_settings.friend_message_needs_wake_prefix`

Whether private messages on platforms require a wake prefix. Default is `false`. When enabled, users must use a wake prefix to trigger a bot response in private chats.

#### `platform_settings.ignore_bot_self_message`

Whether to ignore messages sent by the bot itself. Default is `false`. When enabled, the bot won't process its own messages, preventing infinite loops on some platforms.

#### `platform_settings.ignore_at_all`

Whether to ignore @all messages. Default is `false`. When enabled, the bot won't respond to messages containing @all.

### `provider`

> This item only takes effect in `data/cmd_config.json`; AstrBot does not read this from configuration files in the `data/config/` directory.

List of configured model service provider settings.

### `provider_settings`

General settings for LLM providers.

#### `provider_settings.enable`

Whether to enable LLM chat. Default is `true`.

#### `provider_settings.default_provider_id`

Default conversation model provider ID. Must be a provider ID already configured in the `provider` list. If empty, the first provider in the list is used.

#### `provider_settings.default_image_caption_provider_id`

Default image captioning model provider ID. Must be a provider ID already configured in the `provider` list. If empty, image captioning is disabled.

This means when a user sends an image, AstrBot uses this provider to generate a text description, which is then used as part of the conversation context. This is useful when the conversation model doesn't support multimodal input.

#### `provider_settings.image_caption_prompt`

Prompt template for image captioning. Default is `"Please describe the image using Chinese."`.

#### `provider_settings.provider_pool`

*This configuration item is not yet in actual use.*

#### `provider_settings.wake_prefix`

Extra trigger condition for LLM chat. For example, if `chat` is filled, messages must start with `/chat` to trigger LLM chat, where `/` is the bot's wake prefix. This is a measure to prevent abuse.

#### `provider_settings.web_search`

Whether to enable AstrBot's built-in web search capability. Default is `false`. When enabled, the LLM may automatically search the web and answer based on the content.

#### `provider_settings.websearch_provider`

Web search provider type. Default is `default`. Currently supports `default` and `tavily`.

- `default`: Works best when Google is accessible. If Google fails, it tries Bing and Sogou in order.

- `tavily`: Uses the Tavily search engine.

#### `provider_settings.websearch_tavily_key`

API Key list for the Tavily search engine. Required when using `tavily` as the web search provider.

#### `provider_settings.web_search_link`

Whether to prompt the model to include links to search results in the reply. Default is `false`.

#### `provider_settings.display_reasoning_text`

Whether to display the model's reasoning process in the reply. Default is `false`.

#### `provider_settings.identifier`

Whether to prepend the group member's name to the prompt so the model better understands the group chat state. Default is `false`. Enabling this slightly increases token usage.

#### `provider_settings.group_name_display`

Whether to let the model know the name of the group it's in. Default is `false`. This currently only takes effect in the QQ platform adapter.

#### `provider_settings.datetime_system_prompt`

Whether to include the current machine date and time in the system prompt. Default is `true`.

#### `provider_settings.default_personality`

ID of the default personality to use. Configure personalities in the WebUI.

#### `provider_settings.persona_pool`

*This configuration item is not yet in actual use.*

#### `provider_settings.prompt_prefix`

User prompt. You can use `{{prompt}}` as a placeholder for user input. If no placeholder is provided, it's prepended to the user input.

#### `provider_settings.max_context_length`

When the conversation context exceeds this number, the oldest parts are discarded. One round of chat counts as 1. -1 means no limit.

#### `provider_settings.dequeue_context_length`

The number of conversation rounds to discard each time the `max_context_length` limit is triggered.

#### `provider_settings.streaming_response`

Whether to enable streaming responses. Default is `false`. When enabled, the model's reply is sent to the user in real-time with a typewriter effect. This only takes effect on WebChat, Telegram, and Lark platforms.

#### `provider_settings.show_tool_use_status`

Whether to show tool usage status. Default is `false`. When enabled, the model displays the tool name and input parameters when using a tool.

#### `provider_settings.streaming_segmented`

Whether platforms that don't support streaming responses should fall back to segmented replies. Default is `false`. This means if streaming is enabled but the platform doesn't support it, segmented multiple replies are used instead.

#### `provider_settings.max_agent_step`

Limit on the maximum number of Agent steps. Default is `30`. Each tool call by the model counts as one step.

#### `provider_settings.tool_call_timeout`

Added in `v4.3.5`

Maximum timeout for tool calls (seconds), default is `60` seconds.

#### `provider_stt_settings`

General settings for Speech-to-Text (STT) providers.

#### `provider_stt_settings.enable`

Whether to enable STT services. Default is `false`.

#### `provider_stt_settings.provider_id`

STT provider ID. Must be an STT provider ID already configured in the `provider` list.

#### `provider_tts_settings`

General settings for Text-to-Speech (TTS) providers.

#### `provider_tts_settings.enable`

Whether to enable TTS services. Default is `false`.

#### `provider_tts_settings.provider_id`

TTS provider ID. Must be a TTS provider ID already configured in the `provider` list.

#### `provider_tts_settings.dual_output`

Whether to enable dual output. Default is `false`. When enabled, the bot sends both text and voice messages.

#### `provider_tts_settings.use_file_service`

Whether to enable the file service. Default is `false`. When enabled, the bot provides the output voice file as an external HTTP link to the message platform. This depends on the `callback_api_base` configuration.

#### `provider_ltm_settings`

General settings for group chat context awareness providers.

#### `provider_ltm_settings.group_icl_enable`

Whether to enable group chat context awareness. Default is `false`. When enabled, the bot records group chat conversations to better understand context.

The context content is placed in the conversation's system prompt.

#### `provider_ltm_settings.group_message_max_cnt`

Maximum number of group chat messages to record. Default is `100`. Messages exceeding this count are discarded.

#### `provider_ltm_settings.image_caption`

Whether to record images in group chats and automatically generate text descriptions using an image captioning model. Default is `false`. This depends on the `provider_settings.default_image_caption_provider_id` configuration. Use with caution as it can significantly increase API calls and token usage.

#### `provider_ltm_settings.active_reply`

- `enable`: Whether to enable active replies. Default is `false`.
- `method`: Method for active replies. Option is `possibility_reply`.
- `possibility_reply`: Probability of an active reply. Default is `0.1`. Only applicable when `method` is `possibility_reply`.
- `whitelist`: ID whitelist for active replies. Only IDs in this list will trigger active replies. Empty means no whitelist filter. You can use the `/sid` command to get the session ID on a platform.

### `content_safety`

Content safety settings.

#### `content_safety.also_use_in_response`

Whether to also perform content safety checks on LLM replies. Default is `false`. When enabled, bot-generated replies also undergo safety checks to prevent inappropriate content.

#### `content_safety.internal_keywords`

Internal keyword detection settings.

- `enable`: Whether to enable internal keyword detection. Default is `true`.
- `extra_keywords`: List of extra keywords, supports regex. Default is empty.

#### `content_safety.baidu_aip`

Baidu AI content moderation settings.

- `enable`: Whether to enable Baidu AI content moderation. Default is `false`.
- `app_id`: App ID for Baidu AI content moderation.
- `api_key`: API Key for Baidu AI content moderation.
- `secret_key`: Secret Key for Baidu AI content moderation.

> [!TIP]
> To enable Baidu AI content moderation, please `pip install baidu-aip` first.

### `admins_id`

List of administrator IDs. Additionally, you can use `/op` and `/deop` commands to add or remove admins.

### `t2i`

Whether to enable Text-to-Image (T2I) functionality. Default is `false`. When enabled, if a user's message exceeds a certain character count, the bot renders the message as an image to improve readability and prevent spamming. Supports Markdown rendering.

### `t2i_word_threshold`

Character threshold for T2I. Default is `150`. When a message exceeds this count, the bot renders it as an image.

### `t2i_strategy`

Rendering strategy for T2I. Options are `local` and `remote`. Default is `remote`.

- `local`: Uses AstrBot's local T2I service for rendering. Lower quality but doesn't depend on external services.
- `remote`: Uses a remote T2I service for rendering. Uses the official AstrBot service by default, which offers better quality.

### `t2i_endpoint`

AstrBot API address. Used for rendering Markdown images. Effective when `t2i_strategy` is `remote`. Default is empty, meaning the official AstrBot service is used.

### `t2i_use_file_service`

Whether to enable the file service. Default is `false`. When enabled, the bot provides the rendered image as an external HTTP link to the message platform. This depends on the `callback_api_base` configuration.

### `http_proxy`

HTTP proxy. E.g., `http://localhost:7890`.

### `no_proxy`

List of addresses that bypass the proxy. E.g., `["localhost", "127.0.0.1"]`.

### `dashboard`

AstrBot WebUI configuration.

Please do not change the `password` value arbitrarily. It is an `md5` encoded password. Change the password in the control panel.

- `enable`: Whether to enable the AstrBot WebUI. Default is `true`.
- `username`: Username for the AstrBot WebUI. Default is `astrbot`.
- `password`: Password for the AstrBot WebUI. Default is the `md5` encoded value of `astrbot`. Do not modify directly unless you know what you are doing.
- `jwt_secret`: JWT secret key. AstrBot generates this randomly at initialization. Do not modify unless you know what you are doing.
- `host`: Address the AstrBot WebUI listens on. Default is `0.0.0.0`.
- `port`: Port the AstrBot WebUI listens on. Default is `6185`.

### `platform`

> This item only takes effect in `data/cmd_config.json`; AstrBot does not read this from configuration files in the `data/config/` directory.

List of configured AstrBot message platform adapter settings.

### `platform_specific`

Platform-specific settings. Categorized by platform, then by feature group.

#### `platform_specific.<platform>.pre_ack_emoji`

When enabled, AstrBot sends a pre-reply emoji before requesting the LLM to inform the user that the request is being processed. This currently only takes effect in the Lark and Telegram platform adapters.

##### lark

- `enable`: Whether to enable pre-reply emojis for Lark messages. Default is `false`.
- `emojis`: List of pre-reply emojis. Default is `["Typing"]`. Refer to [Emoji Documentation](https://open.feishu.cn/document/server-docs/im-v1/message-reaction/emojis-introduce) for emoji names.

##### telegram

- `enable`: Whether to enable pre-reply emojis for Telegram messages. Default is `false`.
- `emojis`: List of pre-reply emojis. Default is `["✍️"]`. Telegram only supports a fixed set of reactions; refer to [reactions.txt](https://gist.github.com/Soulter/3f22c8e5f9c7e152e967e8bc28c97fc9).

### `wake_prefix`

Wake prefix. Default is `/`. When a message starts with `/`, AstrBot is awakened.

> [!TIP]
> If the awakened session is not in the ID whitelist, AstrBot will not respond.

### `log_level`

Log level. Default is `INFO`. Can be set to `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

### `trace_enable`

Whether to enable trace recording. Default is `false`. When enabled, AstrBot records execution traces, which can be viewed on the Trace page of the admin panel.

### `pip_install_arg`

Arguments for `pip install`. E.g., `-i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`.

### `pypi_index_url`

PyPI index URL. Default is `https://mirrors.aliyun.com/pypi/simple/`.

### `persona`

*This configuration item has been deprecated since v4.0.0. Please use the WebUI to configure personalities.*

List of configured personalities. Each personality contains `id`, `name`, `description`, and `system_prompt` fields.

### `timezone`

Timezone setting. Please fill in an IANA timezone name, such as Asia/Shanghai. If empty, the system default timezone is used. See all timezones at: [IANA Time Zone Database](https://data.iana.org/time-zones/tzdb-2021a/zone1970.tab).

### `callback_api_base`

Base address for the AstrBot API. Used for file services, plugin callbacks, etc. E.g., `http://example.com:6185`. Default is empty, meaning file services and plugin callbacks are disabled.

### `default_kb_collection`

Default knowledge base name. Used for RAG. If empty, no knowledge base is used.

### `plugin_set`

List of enabled plugins. `*` means all available plugins are enabled. Default is `["*"]`.

---

# AstrBot HTTP API

Starting from v4.18.0, AstrBot provides API Key based HTTP APIs for programmatic access.

## Quick Start

1. Create an API key in WebUI - Settings.
2. Include the API key in request headers:

```http
Authorization: Bearer abk_xxx
```

Also supported:

```http
X-API-Key: abk_xxx
```

3. For chat endpoints, `username` is required:

- `POST /api/v1/chat`: request body must include `username`
- `GET /api/v1/chat/sessions`: query params must include `username`

## Common Endpoints

- `POST /api/v1/chat`: send chat message (SSE stream, server generates UUID when `session_id` is omitted)
- `GET /api/v1/chat/sessions`: list sessions for a specific `username` with pagination
- `GET /api/v1/configs`: list available config files
- `POST /api/v1/file`: upload attachment
- `POST /api/v1/im/message`: proactive message via UMO
- `GET /api/v1/im/bots`: list bot/platform IDs

## Example

```bash
curl -N 'http://localhost:6185/api/v1/chat' \
  -H 'Authorization: Bearer abk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello","username":"alice"}'
```

## Full API Reference

Use the interactive docs:

- https://docs.astrbot.app/scalar.html

---

# 开发一个平台适配器

AstrBot 支持以插件的形式接入平台适配器，你可以自行接入 AstrBot 没有的平台。如飞书、钉钉甚至是哔哩哔哩私信、Minecraft。

我们以一个平台 `FakePlatform` 为例展开讲解。

首先，在插件目录下新增 `fake_platform_adapter.py` 和 `fake_platform_event.py` 文件。前者主要是平台适配器的实现，后者是平台事件的定义。

## 平台适配器

假设 FakePlatform 的客户端 SDK 是这样：

```py
import asyncio

class FakeClient():
    '''模拟一个消息平台，这里 5 秒钟下发一个消息'''
    def __init__(self, token: str, username: str):
        self.token = token
        self.username = username
        # ...
                
    async def start_polling(self):
        while True:
            await asyncio.sleep(5)
            await getattr(self, 'on_message_received')({
                'bot_id': '123',
                'content': '新消息',
                'username': 'zhangsan',
                'userid': '123',
                'message_id': 'asdhoashd',
                'group_id': 'group123',
            })
            
    async def send_text(self, to: str, message: str):
        print('发了消息:', to, message)
        
    async def send_image(self, to: str, image_path: str):
        print('发了消息:', to, image_path)
```

我们创建  `fake_platform_adapter.py`：

```py
import asyncio

from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, PlatformMetadata, MessageType
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain, Image, Record # 消息链中的组件，可以根据需要导入
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.api.platform import register_platform_adapter
from astrbot import logger
from .client import FakeClient
from .fake_platform_event import FakePlatformEvent
            
# 注册平台适配器。第一个参数为平台名，第二个为描述。第三个为默认配置。
@register_platform_adapter("fake", "fake 适配器", default_config_tmpl={
    "token": "your_token",
    "username": "bot_username"
})
class FakePlatformAdapter(Platform):

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue) -> None:
        super().__init__(event_queue)
        self.config = platform_config # 上面的默认配置，用户填写后会传到这里
        self.settings = platform_settings # platform_settings 平台设置。
    
    async def send_by_session(self, session: MessageSesion, message_chain: MessageChain):
        # 必须实现
        await super().send_by_session(session, message_chain)
    
    def meta(self) -> PlatformMetadata:
        # 必须实现，直接像下面一样返回即可。
        return PlatformMetadata(
            "fake",
            "fake 适配器",
        )

    async def run(self):
        # 必须实现，这里是主要逻辑。

        # FakeClient 是我们自己定义的，这里只是示例。这个是其回调函数
        async def on_received(data):
            logger.info(data)
            abm = await self.convert_message(data=data) # 转换成 AstrBotMessage
            await self.handle_msg(abm) 
        
        # 初始化 FakeClient
        self.client = FakeClient(self.config['token'], self.config['username'])
        self.client.on_message_received = on_received
        await self.client.start_polling() # 持续监听消息，这是个堵塞方法。

    async def convert_message(self, data: dict) -> AstrBotMessage:
        # 将平台消息转换成 AstrBotMessage
        # 这里就体现了适配程度，不同平台的消息结构不一样，这里需要根据实际情况进行转换。
        abm = AstrBotMessage()
        abm.type = MessageType.GROUP_MESSAGE # 还有 friend_message，对应私聊。具体平台具体分析。重要！
        abm.group_id = data['group_id'] # 如果是私聊，这里可以不填
        abm.message_str = data['content'] # 纯文本消息。重要！
        abm.sender = MessageMember(user_id=data['userid'], nickname=data['username']) # 发送者。重要！
        abm.message = [Plain(text=data['content'])] # 消息链。如果有其他类型的消息，直接 append 即可。重要！
        abm.raw_message = data # 原始消息。
        abm.self_id = data['bot_id']
        abm.session_id = data['userid'] # 会话 ID。重要！
        abm.message_id = data['message_id'] # 消息 ID。
        
        return abm
    
    async def handle_msg(self, message: AstrBotMessage):
        # 处理消息
        message_event = FakePlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            client=self.client
        )
        self.commit_event(message_event) # 提交事件到事件队列。不要忘记！
```


`fake_platform_event.py`：

```py
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image
from .client import FakeClient
from astrbot.core.utils.io import download_image_by_url

class FakePlatformEvent(AstrMessageEvent):
    def __init__(self, message_str: str, message_obj: AstrBotMessage, platform_meta: PlatformMetadata, session_id: str, client: FakeClient):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        
    async def send(self, message: MessageChain):
        for i in message.chain: # 遍历消息链
            if isinstance(i, Plain): # 如果是文字类型的
                await self.client.send_text(to=self.get_sender_id(), message=i.text)
            elif isinstance(i, Image): # 如果是图片类型的 
                img_url = i.file
                img_path = ""
                # 下面的三个条件可以直接参考一下。
                if img_url.startswith("file:///"):
                    img_path = img_url[8:]
                elif i.file and i.file.startswith("http"):
                    img_path = await download_image_by_url(i.file)
                else:
                    img_path = img_url

                # 请善于 Debug！
                    
                await self.client.send_image(to=self.get_sender_id(), image_path=img_path)

        await super().send(message) # 需要最后加上这一段，执行父类的 send 方法。
```

最后，main.py 只需这样，在初始化的时候导入 fake_platform_adapter 模块。装饰器会自动注册。

```py
from astrbot.api.star import Context, Star

class MyPlugin(Star):
    def __init__(self, context: Context):
        from .fake_platform_adapter import FakePlatformAdapter # noqa
```

搞好后，运行 AstrBot：

![image](https://files.astrbot.app/docs/source/images/plugin-platform-adapter/QQ_1738155926221.png)

这里出现了我们创建的 fake。

![image](https://files.astrbot.app/docs/source/images/plugin-platform-adapter/QQ_1738155982211.png)

启动后，可以看到正常工作：

![image](https://files.astrbot.app/docs/source/images/plugin-platform-adapter/QQ_1738156166893.png)


有任何疑问欢迎加群询问~