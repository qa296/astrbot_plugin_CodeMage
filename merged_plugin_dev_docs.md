# AstrBot Developer Documentation (Merged)
> All development documentation merged and ordered by importance.

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
- See [Message Events](#message-events) and [Message Object](#message-object) sections below for details on `AstrMessageEvent` and `AstrBotMessage`.

> [!TIP]
>
> Handlers must be registered within the plugin class, with the first two parameters being `self` and `event`. If the file becomes too long, you can write services externally and call them from the handler.
>
> The file containing the plugin class must be named `main.py`.

All handler functions must be written within the plugin class. To keep content concise, in subsequent sections, we may omit the plugin class definition.

---

# AstrBot Plugin Development Guide 🌠

Prerequisites: Python programming and Git experience.

## Environment Setup

### Obtain the Plugin Template

1. Open [helloworld](https://github.com/Soulter/helloworld) template → `Use this template` → `Create new repository`
2. Name it following conventions: `astrbot_plugin_<name>` (lowercase, no spaces, concise)

### Clone the Project Locally

```bash
git clone https://github.com/AstrBotDevs/AstrBot
mkdir -p AstrBot/data/plugins && cd AstrBot/data/plugins
git clone <your-plugin-repository-url>
```

Open `AstrBot` in VSCode, navigate to `data/plugins/<your-plugin-name>`, and update `metadata.yaml`.

> [!WARNING]
> `metadata.yaml` is required for AstrBot to recognize plugin metadata.

### Optional Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `logo.png` | file | 1:1 aspect ratio, recommended 256x256 |
| `display_name` | string | Display name in plugin marketplace |
| `support_platforms` | `list[str]` | Supported platform adapter keys |
| `astrbot_version` | string | Required AstrBot version range (PEP 440, no `v` prefix) |

**Supported platforms:** `aiocqhttp`, `qq_official`, `telegram`, `wecom`, `lark`, `dingtalk`, `discord`, `slack`, `kook`, `vocechat`, `weixin_official_account`, `satori`, `misskey`, `line`

**Version examples:** `>=4.17.0`, `>=4.16,<5`, `~=4.17`. If unmet, plugin is blocked (can override with "Ignore Warning and Install" in WebUI).

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

> See the [Minimal Example](#minimal-example) section above for a complete plugin class with a `helloworld` command.

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

Command groups organize related commands. Use `pass` in the group function; register subcommands with `group_name.command()`.

```python
@filter.command_group("math")
def math(self):
    pass

@math.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a + b}")
```

Command groups can be nested infinitely using `group()` (not `command_group`):

```py
@filter.command_group("math")
def math():
    pass

@math.group("calc")
def calc():
    pass

@calc.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"Result is: {a + b}")

@calc.command("help")
def calc_help(self, event: AstrMessageEvent):
    yield event.plain_result("Commands: add, sub")
```

Missing subcommand shows an error with the command tree structure.

## Command Aliases

> Available after v3.4.28

You can add different aliases for commands or command groups:

```python
@filter.command("help", alias={'帮助', 'helpme'})
def help(self, event: AstrMessageEvent):
    yield event.plain_result("This is the help command. Use /help for assistance.")
```

### Event Type Filtering

All filter decorators can be combined with `AND` logic by stacking multiple decorators.

| Decorator | Values | Description |
|-----------|--------|-------------|
| `@filter.event_message_type()` | `EventMessageType.ALL`, `PRIVATE_MESSAGE`, `GROUP_MESSAGE` | Filter by message type |
| `@filter.platform_adapter_type()` | `PlatformAdapterType.AIOCQHTTP`, `QQOFFICIAL`, `GEWECHAT`, `ALL` (bitwise OR supported) | Filter by platform |
| `@filter.permission_type()` | `PermissionType.ADMIN`, `MEMBER` | Filter by user permission |

```python
# Example: receive all events
@filter.event_message_type(filter.EventMessageType.ALL)
async def on_all_message(self, event: AstrMessageEvent):
    yield event.plain_result("Received a message.")

# Example: private messages only
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def on_private_message(self, event: AstrMessageEvent):
    yield event.plain_result("Received a private message.")

# Example: specific platforms (bitwise OR)
@filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP | filter.PlatformAdapterType.QQOFFICIAL)
async def on_aiocqhttp(self, event: AstrMessageEvent):
    yield event.plain_result("Received from AIOCQHTTP or QQOFFICIAL.")

# Example: admin-only command
@filter.permission_type(filter.PermissionType.ADMIN)
@filter.command("test")
async def test(self, event: AstrMessageEvent):
    pass
```

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

> [!IMPORTANT]
> **You cannot use `yield` to send messages inside event hooks.** Use `event.send()` directly.

All hooks below share the common import: `from astrbot.api.event import filter, AstrMessageEvent`

#### On Bot Initialization Complete

> Available after v3.4.34

```python
@filter.on_astrbot_loaded()
async def on_astrbot_loaded(self):
    print("AstrBot initialization complete")
```

#### On LLM Request

Triggered before calling the LLM. You can obtain and modify the `ProviderRequest` object (contains request text, system prompt, etc.).

```python
from astrbot.api.provider import ProviderRequest

@filter.on_llm_request()
async def my_custom_hook(self, event: AstrMessageEvent, req: ProviderRequest):
    req.system_prompt += "Custom system_prompt"
```

#### On LLM Response Complete

Triggered after the LLM request completes. You can obtain and modify the `LLMResponse` object.

```python
from astrbot.api.provider import LLMResponse

@filter.on_llm_response()
async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
    print(resp)
```

#### Before Sending Message

Triggered before sending a message. Use for message decoration (voice conversion, image conversion, adding prefixes, etc.).

```python
@filter.on_decorating_result()
async def on_decorating_result(self, event: AstrMessageEvent):
    result = event.get_result()
    chain = result.chain
    chain.append(Plain("!"))
```

#### After Message Sent

Triggered after a message is sent to the platform.

```python
@filter.after_message_sent()
async def after_message_sent(self, event: AstrMessageEvent):
    pass
```

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

> [!TIP]
> `unified_msg_origin` is a string that records the unique ID of a session. AstrBot uses it to identify which messaging platform and which session it belongs to. This allows messages to be sent to the correct session when using `send_message`.

## Rich Media Messages

Use `MessageChain` and `astrbot.api.message_components` (aliased as `Comp`) to construct rich messages.

```python
import astrbot.api.message_components as Comp

chain = [
    Comp.At(qq=event.get_sender_id()),
    Comp.Plain("Check out this image:"),
    Comp.Image.fromURL("https://example.com/image.jpg"),
    Comp.Image.fromFileSystem("path/to/image.jpg"),
    Comp.Plain("This is an image.")
]
yield event.chain_result(chain)
```

> [!TIP]
> In aiocqhttp, `Plain` messages are `strip()`ed during sending. Add zero-width spaces `\u200b` to preserve whitespace.

**Other message types:**

| Type | Code | Notes |
|------|------|-------|
| File | `Comp.File(file="path", name="name")` | Not supported by some platforms |
| Audio | `Comp.Record(file=path, url=path)` | WAV format only |
| Video | `Comp.Video.fromFileSystem(path)` / `Comp.Video.fromURL(url)` | See example below |
| Forward | `Node(uin=..., name=..., content=[...])` | OneBot v11 only |

**Video example:**
```python
from astrbot.api.message_components import Video
music = Video.fromFileSystem(path="test.mp4")  # Requires client & bot on same system
music = Video.fromURL(url="https://example.com/video.mp4")  # More universal
yield event.chain_result([music])
```

**Group Forward Messages** (OneBot v11 only):
```python
from astrbot.api.message_components import Node, Plain, Image
node = Node(uin=905617992, name="Soulter", content=[Plain("hi"), Image.fromFileSystem("test.jpg")])
yield event.chain_result([node])
```

---

# AI

AstrBot provides built-in support for multiple Large Language Model (LLM) providers and offers a unified interface, making it convenient for plugin developers to access various LLM services.

You can use the LLM / Agent interfaces provided by AstrBot to implement your own intelligent agents.

Starting from version `v4.5.7`, we've made significant improvements to the way LLM providers are invoked. We recommend using the new approach, which is more concise and supports additional features. The legacy invocation method remains documented in the previous Chinese-only guide.

> [!TIP]
> All features in this section (Getting Chat Model ID, Invoking LLMs, Invoking Agents, Multi-Agent) were **added in v4.5.7**.

## Getting the Chat Model ID for the Current Session

```py
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo=umo)
```

## Invoking Large Language Models


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


Multi-Agent systems decompose complex applications into multiple specialized agents that collaborate to solve problems. We implement multi-agent systems using the `agent-as-tool` pattern.

In the example below, a Main Agent delegates tasks to Sub-Agents (e.g., weather retrieval).

![multi-agent-example-1](https://files.astrbot.app/docs/en/dev/star/guides/multi-agent-example-1.svg)

Define Tools. The pattern is identical for all: `@dataclass` inheriting `FunctionTool[AstrAgentContext]` with `name`, `description`, `parameters`, and `call()` method. Here's one complete example:

```py
@dataclass
class AssignAgentTool(FunctionTool[AstrAgentContext]):
    """Main agent uses this tool to decide which sub-agent to delegate a task to."""
    name: str = "assign_agent"
    description: str = "Assign an agent to a task based on the given query"
    parameters: dict = field(default_factory=lambda: {
        "type": "object", "properties": {"query": {"type": "string", "description": "The query to call the sub-agent with."}},
        "required": ["query"],
    })
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> str | CallToolResult:
        return "Based on the query, you should assign agent 1."
```

Other tools in this example:

| Tool | Purpose | Key Parameters | `call()` Logic |
|------|---------|----------------|----------------|
| `WeatherTool` | Get weather info | `city` (str) | Return weather string |
| `SubAgent1` | Sub-agent wrapping `WeatherTool` | `query` (str) | Calls `ctx.tool_loop_agent()` with `WeatherTool()` |
| `SubAgent2` | Placeholder sub-agent | `query` (str) | Returns dummy response |

`SubAgent1` is the key pattern -- it wraps another agent as a tool:

```py
@dataclass
class SubAgent1(FunctionTool[AstrAgentContext]):
    name: str = "subagent1_name"
    description: str = "subagent1_description"
    parameters: dict = field(default_factory=lambda: {
        "type": "object", "properties": {"query": {"type": "string", "description": "Query for sub-agent."}},
        "required": ["query"],
    })
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> str | CallToolResult:
        ctx = context.context.context
        event = context.context.event
        llm_resp = await ctx.tool_loop_agent(
            event=event,
            chat_provider_id=await ctx.get_current_chat_provider_id(event.unified_msg_origin),
            prompt=kwargs["query"],
            tools=ToolSet([WeatherTool()]),
            max_steps=30,
        )
        return llm_resp.completion_text
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

::: details Conversation type definition

```py
@dataclass
class Conversation:
    platform_id: str; user_id: str; cid: str  # UUID
    history: str = ""; title: str | None = ""; persona_id: str | None = ""
    created_at: int = 0; updated_at: int = 0
```
:::

::: details Persona / Personality type definitions

```py
class Persona(SQLModel, table=True):
    __tablename__ = "personas"
    id: int = Field(primary_key=True); persona_id: str = Field(max_length=255, nullable=False)
    system_prompt: str = Field(sa_type=Text, nullable=False)
    begin_dialogs: Optional[list] = Field(default=None, sa_type=JSON)
    tools: Optional[list] = Field(default=None, sa_type=JSON)  # None=all, []=none
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column_kwargs={"onupdate": datetime.now(timezone.utc)})
    __table_args__ = (UniqueConstraint("persona_id", name="uix_persona_id"),)

class Personality(TypedDict):
    """Legacy v3 persona format. Use Persona class for v4.0.0+."""
    prompt: str; name: str; begin_dialogs: list[str]
    mood_imitation_dialogs: list[str]  # Deprecated since v4.0.0
    tools: list[str] | None  # None=all, []=none
```
:::

### Main Methods

| Method | Arguments | Returns | Description |
|--------|-----------|---------|-------------|
| `new_conversation` | `unified_msg_origin`, `platform_id?`, `content?`, `title?`, `persona_id?` | `str` (UUID) | Create and switch to new conversation |
| `switch_conversation` | `unified_msg_origin`, `conversation_id` | `None` | Switch to a conversation |
| `delete_conversation` | `unified_msg_origin`, `conversation_id?` | `None` | Delete conversation (None = current) |
| `get_curr_conversation_id` | `unified_msg_origin` | `str \| None` | Get current conversation ID |
| `get_conversation` | `unified_msg_origin`, `conversation_id`, `create_if_not_exists=False` | `Conversation \| None` | Get conversation object (auto-create if flag set) |
| `get_conversations` | `unified_msg_origin?`, `platform_id?` | `List[Conversation]` | List all conversations |
| `update_conversation` | `unified_msg_origin`, `conversation_id?`, `history?`, `title?`, `persona_id?` | `None` | Update conversation fields |

## Persona Manager

`PersonaManager` handles loading, caching, and CRUD for all Personas, with v3 format compatibility.

```py
persona_mgr = self.context.persona_manager
```

### Main Methods

| Method | Arguments | Returns | Raises | Description |
|--------|-----------|---------|--------|-------------|
| `get_persona` | `persona_id` | `Persona` | `ValueError` | Get persona by ID |
| `get_all_personas` | – | `list[Persona]` | – | List all personas |
| `create_persona` | `persona_id`, `system_prompt`, `begin_dialogs?`, `tools?` | `Persona` | `ValueError` (exists) | Create new persona |
| `update_persona` | `persona_id`, `system_prompt?`, `begin_dialogs?`, `tools?` | `Persona` | `ValueError` (not found) | Update persona fields |
| `delete_persona` | `persona_id` | – | `ValueError` (not found) | Delete persona |
| `get_default_persona_v3` | `umo?` | `Personality` | – | Get default persona in v3 format |

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

For editing Python `dict` configurations. Example:

```py
"custom_extra_body": {
  "description": "Custom request body parameters", "type": "dict", "items": {},
  "hint": "Add extra parameters like temperature, top_p, max_tokens, etc.",
  "template_schema": {
      "temperature": {"name": "Temperature", "description": "Controls randomness, 0-2", "type": "float", "default": 0.6, "slider": {"min": 0, "max": 2, "step": 0.1}},
      "top_p": {"name": "Top-p", "description": "Nucleus sampling, 0-1", "type": "float", "default": 1.0, "slider": {"min": 0, "max": 1, "step": 0.01}},
      "max_tokens": {"name": "Max Tokens", "type": "int", "default": 8192},
  },
}
```

### `template_list` type schema

> Introduced in v4.10.4. See [#4208](https://github.com/AstrBotDevs/AstrBot/pull/4208).

Template-style configuration where users pick from predefined templates:

```json
"field_id": {
  "type": "template_list", "description": "Template List Field",
  "templates": {
    "template_1": { "name": "Template One", "items": {
      "attr_a": {"description": "Attribute A", "type": "int", "default": 10},
      "attr_b": {"description": "Attribute B", "type": "bool", "default": true}
    }},
    "template_2": { "name": "Template Two", "items": {
      "attr_c": {"description": "Attribute C", "type": "int", "default": 10},
      "attr_d": {"description": "Attribute D", "type": "bool", "default": true}
    }}
  }
}
```

Saved result:
```json
"field_id": [
    {"__template_key": "template_1", "attr_a": 10, "attr_b": true},
    {"__template_key": "template_2", "attr_c": 10, "attr_d": true}
]
```

## Using Configuration in Plugins

AstrBot auto-parses `_conf_schema.json` and passes config to `__init__()`:

```py
from astrbot.api import AstrBotConfig

class ConfigPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        # self.config.save_config()  # Save changes
```

## Configuration Updates

Schema updates across versions are handled automatically -- missing items get defaults, removed items are deleted.

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
async def handle_idiom_chain(self, event: AstrMessageEvent):
    yield event.plain_result("Please send an idiom~")

    @session_waiter(timeout=60, record_history_chains=False)
    async def idiom_waiter(controller: SessionController, event: AstrMessageEvent):
        idiom = event.message_str
        if idiom == "exit":
            await event.send(event.plain_result("Exited~"))
            controller.stop()
            return
        if len(idiom) != 4:
            await event.send(event.plain_result("Must be 4 characters~"))
            return
        # ... process idiom ...
        await event.send(event.plain_result("Next idiom~"))
        controller.keep(timeout=60, reset_timeout=True)

    try:
        await idiom_waiter(event)
    except TimeoutError:
        yield event.plain_result("You timed out!")
    finally:
        event.stop_event()
```

Once activated, subsequent messages from that sender go through `idiom_waiter` until stopped or timed out.

## SessionController

| Method | Description |
|--------|-------------|
| `keep(timeout, reset_timeout=False)` | Keep session alive. `reset_timeout=True` resets the timer. |
| `stop()` | End session immediately. |
| `get_history_chains()` | Returns `List[List[Comp.BaseMessageComponent]]`. |

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

**Image Rendering Options** (see Playwright [screenshot API](https://playwright.dev/python/docs/api/class-page#page-screenshot)):
`timeout` (float), `type` ("jpeg"/"png"), `quality` (int, jpeg only), `omit_background` (bool, png only), `full_page` (bool, default True), `clip` (dict), `animations` ("allow"/"disabled"), `caret` ("hide"/"initial"), `scale` ("css"/"device").

---

# Publishing Plugins to the Plugin Marketplace

Push your code to GitHub, then visit [plugins.astrbot.app](https://plugins.astrbot.app), click `+`, fill in details, and click `Submit to GITHUB` to create an Issue in the AstrBot repo.

---

# AstrBot Configuration File

## data/cmd_config.json

AstrBot's configuration file is a JSON format file. AstrBot reads this file at startup and initializes based on the settings within. Its path is `data/cmd_config.json`.

> Since AstrBot v4.0.0, we introduced the concept of [multiple configuration files](https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6). `data/cmd_config.json` serves as the default configuration `default`. Other configuration files you create in the WebUI are stored in the `data/config/` directory, starting with `abconf_`.

The default AstrBot configuration is as follows:

```jsonc
{
    "config_version": 2,
    "platform_settings": { "unique_session": False, "rate_limit": {...}, "reply_prefix": "", "forward_threshold": 1500, "enable_id_white_list": True, "id_whitelist": [], "id_whitelist_log": True, "wl_ignore_admin_on_group": True, "wl_ignore_admin_on_friend": True, "reply_with_mention": False, "reply_with_quote": False, "path_mapping": [], "segmented_reply": {...}, "no_permission_reply": True, "empty_mention_waiting": True, "empty_mention_waiting_need_reply": True, "friend_message_needs_wake_prefix": False, "ignore_bot_self_message": False, "ignore_at_all": False },
    "provider": [],
    "provider_settings": { "enable": True, "default_provider_id": "", "default_image_caption_provider_id": "", "image_caption_prompt": "Please describe the image using Chinese.", "provider_pool": ["*"], "wake_prefix": "", "web_search": False, "websearch_provider": "default", "websearch_tavily_key": [], "web_search_link": False, "display_reasoning_text": False, "identifier": False, "group_name_display": False, "datetime_system_prompt": True, "default_personality": "default", "persona_pool": ["*"], "prompt_prefix": "{{prompt}}", "max_context_length": -1, "dequeue_context_length": 1, "streaming_response": False, "show_tool_use_status": False, "streaming_segmented": False, "max_agent_step": 30, "tool_call_timeout": 60 },
    "provider_stt_settings": { "enable": False, "provider_id": "" },
    "provider_tts_settings": { "enable": False, "provider_id": "", "dual_output": False, "use_file_service": False },
    "provider_ltm_settings": { "group_icl_enable": False, "group_message_max_cnt": 300, "image_caption": False, "active_reply": {...} },
    "content_safety": { "also_use_in_response": False, "internal_keywords": {...}, "baidu_aip": {...} },
    "admins_id": ["astrbot"],
    "t2i": False, "t2i_word_threshold": 150, "t2i_strategy": "remote", "t2i_endpoint": "", "t2i_use_file_service": False, "t2i_active_template": "base",
    "http_proxy": "", "no_proxy": ["localhost", "127.0.0.1", "::1"],
    "dashboard": { "enable": True, "username": "astrbot", "password": "<md5>", "jwt_secret": "", "host": "0.0.0.0", "port": 6185 },
    "platform": [],
    "platform_specific": { "lark": {...}, "telegram": {...} },
    "wake_prefix": ["/"], "log_level": "INFO", "trace_enable": False,
    "pip_install_arg": "", "pypi_index_url": "https://mirrors.aliyun.com/pypi/simple/",
    "persona": [],  // deprecated
    "timezone": "Asia/Shanghai", "callback_api_base": "", "default_kb_collection": "",
    "plugin_set": ["*"]
}
```

## Field Details

### `config_version`
Configuration version, do not modify.

### `platform_settings`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `unique_session` | bool | `false` | Session isolation per user in groups |
| `rate_limit` | object | `{time:60,count:30,strategy:"stall"}` | Rate limiting; strategy: `stall` or `discard` |
| `reply_prefix` | string | `""` | Fixed prefix when replying |
| `forward_threshold` | int | `1500` | QQ platform: fold replies into forwarded messages above this char count |
| `enable_id_white_list` | bool | `true` | Enable ID whitelist filtering |
| `id_whitelist` | list | `[]` | Allowed session IDs (use `/sid` to get) |
| `id_whitelist_log` | bool | `true` | Log whitelist failures |
| `wl_ignore_admin_on_group` | bool | `true` | Admin group messages bypass whitelist |
| `wl_ignore_admin_on_friend` | bool | `true` | Admin private messages bypass whitelist |
| `reply_with_mention` | bool | `false` | @ mention user when replying |
| `reply_with_quote` | bool | `false` | Quote user's message when replying |
| `path_mapping` | list | `[]` | **Deprecated since v4.0.0** |
| `segmented_reply` | object | see below | Segmented reply settings |
| `no_permission_reply` | bool | `true` | Reply with "no permission" prompt |
| `empty_mention_waiting` | bool | `true` | Wait 60s for follow-up after @-only message |
| `empty_mention_waiting_need_reply` | bool | `true` | Generate LLM reply when waiting is triggered |
| `friend_message_needs_wake_prefix` | bool | `false` | Private messages require wake prefix |
| `ignore_bot_self_message` | bool | `false` | Ignore bot's own messages |
| `ignore_at_all` | bool | `false` | Ignore @all messages |

**`segmented_reply` sub-fields:** `enable` (bool, `false`), `only_llm_result` (bool, `true`), `interval_method` (`random`/`log`, `random`), `interval` (`"1.5,3.5"` for random), `log_base` (`2.6`), `words_count_threshold` (`150`), `regex` (`".*?[。？！~…]+|.+$"`), `content_cleanup_rule` (regex, `""`).

### `provider`
> Only takes effect in `data/cmd_config.json`, not in `data/config/` files.

List of configured model service provider settings.

### `provider_settings`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable` | bool | `true` | Enable LLM chat |
| `default_provider_id` | string | `""` | Default provider ID (empty = first in list) |
| `default_image_caption_provider_id` | string | `""` | Image captioning provider ID (empty = disabled) |
| `image_caption_prompt` | string | `"Please describe the image using Chinese."` | Prompt for image captioning |
| `provider_pool` | list | `["*"]` | **Not yet in use** |
| `wake_prefix` | string | `""` | Extra trigger for LLM chat (e.g., `chat` → `/chat`) |
| `web_search` | bool | `false` | Enable built-in web search |
| `websearch_provider` | string | `"default"` | `default` (Google→Bing→Sogou) or `tavily` |
| `websearch_tavily_key` | list | `[]` | Tavily API keys |
| `web_search_link` | bool | `false` | Include search result links in replies |
| `display_reasoning_text` | bool | `false` | Show model reasoning in replies |
| `identifier` | bool | `false` | Prepend group member names to prompts |
| `group_name_display` | bool | `false` | Show group name to model (QQ only) |
| `datetime_system_prompt` | bool | `true` | Include current date/time in system prompt |
| `default_personality` | string | `"default"` | Default personality ID |
| `persona_pool` | list | `["*"]` | **Not yet in use** |
| `prompt_prefix` | string | `"{{prompt}}"` | User prompt template |
| `max_context_length` | int | `-1` | Max conversation rounds (-1 = unlimited) |
| `dequeue_context_length` | int | `1` | Rounds to discard when limit exceeded |
| `streaming_response` | bool | `false` | Enable streaming (WebChat, Telegram, Lark) |
| `show_tool_use_status` | bool | `false` | Show tool name and params when using tools |
| `streaming_segmented` | bool | `false` | Fall back to segmented replies if streaming unsupported |
| `max_agent_step` | int | `30` | Max Agent tool call steps |
| `tool_call_timeout` | int | `60` | Tool call timeout in seconds (added v4.3.5) |

### `provider_stt_settings`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable` | bool | `false` | Enable STT |
| `provider_id` | string | `""` | STT provider ID |

### `provider_tts_settings`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable` | bool | `false` | Enable TTS |
| `provider_id` | string | `""` | TTS provider ID |
| `dual_output` | bool | `false` | Send both text and voice |
| `use_file_service` | bool | `false` | Provide voice as HTTP link (requires `callback_api_base`) |

### `provider_ltm_settings`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `group_icl_enable` | bool | `false` | Record group chat for context awareness |
| `group_message_max_cnt` | int | `300` | Max group messages to record |
| `image_caption` | bool | `false` | Auto-caption images in group chat (uses `default_image_caption_provider_id`) |
| `active_reply.enable` | bool | `false` | Enable active replies |
| `active_reply.method` | string | `"possibility_reply"` | Method |
| `active_reply.possibility_reply` | float | `0.1` | Probability |
| `active_reply.whitelist` | list | `[]` | Allowed session IDs |

### `content_safety`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `also_use_in_response` | bool | `false` | Check LLM replies for safety |
| `internal_keywords.enable` | bool | `true` | Enable keyword detection |
| `internal_keywords.extra_keywords` | list | `[]` | Extra keywords (regex supported) |
| `baidu_aip.enable` | bool | `false` | Enable Baidu AI moderation (requires `pip install baidu-aip`) |
| `baidu_aip.app_id` | string | `""` | Baidu App ID |
| `baidu_aip.api_key` | string | `""` | Baidu API Key |
| `baidu_aip.secret_key` | string | `""` | Baidu Secret Key |

### `admins_id`
List of administrator IDs. Use `/op` and `/deop` commands to manage. Default: `["astrbot"]`.

### `t2i` / `t2i_word_threshold` / `t2i_strategy` / `t2i_endpoint` / `t2i_use_file_service`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `t2i` | bool | `false` | Enable text-to-image for long messages |
| `t2i_word_threshold` | int | `150` | Character threshold for T2I |
| `t2i_strategy` | string | `"remote"` | `local` or `remote` |
| `t2i_endpoint` | string | `""` | Remote T2I API URL (empty = official service) |
| `t2i_use_file_service` | bool | `false` | Provide image as HTTP link |
| `t2i_active_template` | string | `"base"` | Active T2I template |

### `http_proxy` / `no_proxy` / `dashboard` / `platform` / `platform_specific`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `http_proxy` | string | `""` | HTTP proxy URL |
| `no_proxy` | list | `["localhost","127.0.0.1","::1"]` | Bypass proxy list |
| `dashboard.enable` | bool | `true` | Enable WebUI |
| `dashboard.username` | string | `"astrbot"` | WebUI username |
| `dashboard.password` | string | `<md5>` | MD5-encoded password (change in WebUI) |
| `dashboard.jwt_secret` | string | `""` | Auto-generated JWT secret |
| `dashboard.host` | string | `"0.0.0.0"` | WebUI listen address |
| `dashboard.port` | int | `6185` | WebUI listen port |
| `platform` | list | `[]` | Platform adapter configs (only in `cmd_config.json`) |
| `platform_specific` | object | `{lark:{...},telegram:{...}}` | Per-platform settings |

**`platform_specific.<platform>.pre_ack_emoji`:** Sends pre-reply emoji before LLM request (Lark: `["Typing"]`, Telegram: `["✍️"]`). Lark emoji names: [Feishu Emojis](https://open.feishu.cn/document/server-docs/im-v1/message-reaction/emojis-introduce). Telegram reactions: [reactions.txt](https://gist.github.com/Soulter/3f22c8e5f9c7e152e967e8bc28c97fc9).

### `wake_prefix` / `log_level` / `trace_enable` / `pip_install_arg` / `pypi_index_url` / `timezone` / `callback_api_base` / `default_kb_collection` / `plugin_set`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `wake_prefix` | list | `["/"]` | Bot wake prefix. If session not in whitelist, no response. |
| `log_level` | string | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `trace_enable` | bool | `false` | Record execution traces (viewable in admin panel) |
| `pip_install_arg` | string | `""` | Extra pip arguments |
| `pypi_index_url` | string | `"https://mirrors.aliyun.com/pypi/simple/"` | PyPI mirror URL |
| `persona` | list | `[]` | **Deprecated since v4.0.0**. Use WebUI instead. |
| `timezone` | string | `"Asia/Shanghai"` | IANA timezone name |
| `callback_api_base` | string | `""` | Base API URL for file services and plugin callbacks |
| `default_kb_collection` | string | `""` | Default knowledge base for RAG |
| `plugin_set` | list | `["*"]` | Enabled plugins (`*` = all) |

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

> [!NOTE]
> This section is pending translation. The original content is in Chinese.

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
    async def handle_msg(self, message: AstrBotMessage):
        message_event = FakePlatformEvent(
            message_str=message.message_str, message_obj=message,
            platform_meta=self.meta(), session_id=message.session_id, client=self.client
        )
        self.commit_event(message_event)
```

`fake_platform_event.py`:

```py
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata
from astrbot.api.message_components import Plain, Image
from .client import FakeClient
from astrbot.core.utils.io import download_image_by_url

class FakePlatformEvent(AstrMessageEvent):
    def __init__(self, message_str, message_obj, platform_meta, session_id, client):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    async def send(self, message: MessageChain):
        for i in message.chain:
            if isinstance(i, Plain):
                await self.client.send_text(to=self.get_sender_id(), message=i.text)
            elif isinstance(i, Image):
                img_url = i.file
                if img_url.startswith("file:///"): img_path = img_url[8:]
                elif i.file and i.file.startswith("http"): img_path = await download_image_by_url(i.file)
                else: img_path = img_url
                await self.client.send_image(to=self.get_sender_id(), image_path=img_path)
        await super().send(message)
```

`main.py` — import the adapter module during initialization. The decorator auto-registers:

```py
from astrbot.api.star import Context, Star
class MyPlugin(Star):
    def __init__(self, context: Context):
        from .fake_platform_adapter import FakePlatformAdapter # noqa
```