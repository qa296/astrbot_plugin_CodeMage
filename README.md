# CodeMage - AI驱动的AstrBot插件生成器

<p align="center">
  <img src="https://github.com/qa296/astrbot_plugin_CodeMage/blob/main/logo.png" alt="CodeMage Logo" width="200">
</p>

<p align="center">
  <strong>使用AI自动生成AstrBot插件</strong>
</p>

<p align="center">
  <a href="https://github.com/qa296/astrbot_plugin_codemage/issues">
    <img src="https://img.shields.io/github/issues/qa296/astrbot_plugin_codemage" alt="GitHub Issues">
  </a>
  <a href="https://github.com/qa296/astrbot_plugin_codemage/stargazers">
    <img src="https://img.shields.io/github/stars/qa296/astrbot_plugin_codemage" alt="GitHub Stars">
  </a>
  <a href="https://github.com/qa296/astrbot_plugin_codemage/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/qa296/astrbot_plugin_codemage" alt="GitHub License">
  </a>
</p>

> ⚠️ **安全警告**: 本工具使用AI生成代码，生成的插件可能存在安全风险。

## 简介

CodeMage 是一个基于AI的 AstrBot 插件生成器，可以根据自然语言描述自动生成完整的 AstrBot 插件。它利用大型语言模型（LLM）的强大能力，将您的想法快速转化为可运行的插件代码。

## 功能特点

- 🤖 **AI驱动**: 利用大型语言模型自动生成插件代码
- ⚡ **快速开发**: 将想法快速转化为可用插件
- 🔧 **自动化流程**: 自动生成插件元数据、文档和代码
- 📦 **一键安装**: 生成后可直接安装到 AstrBot
- 🔍 **代码审查**: 内置代码审查机制，确保生成质量
- 🔐 **安全过滤**: 防止生成恶意或不适当的内容

## 安装

1. 在 AstrBot 的插件市场中搜索 "CodeMage" 并安装
2. 或者通过以下命令手动安装:

```bash
# 进入 AstrBot 插件目录
cd AstrBot/data/plugins

# 克隆插件仓库
git clone https://github.com/qa296/astrbot_plugin_codemage.git
```

3. 重启 AstrBot 以加载插件

## 配置


### 配置项说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `llm_provider_id` | LLM提供商ID，需要在AstrBot中配置 | 无 |
| `admin_only` | 是否限制只有管理员才能使用插件生成功能 | `true` |
| `negative_prompt` | 反向提示词，禁止生成的内容规则 | 见默认值 |
| `auto_approve` | 是否自动批准生成的插件，跳过用户确认步骤 | `false` |
| `step_by_step` | 是否使用分步生成模式 | `true` |
| `satisfaction_threshold` | 插件审查通过的最低满意度分数（0-100） | `80` |
| `strict_review` | 是否启用严格审查模式 | `true` |
| `max_retries` | 插件生成失败时的最大重试次数 | `3` |
| `enable_function_call` | 是否允许通过LLM函数调用生成插件 | `true` |
| `allow_dependencies` | 是否允许生成的插件包含外部依赖 | `false` |
| `astrbot_url` | AstrBot的API地址，用于安装插件 | `http://localhost:6185` |
| `api_username` | AstrBot API的登录用户名 | `astrbot` |
| `api_password_md5` | AstrBot API的登录密码（MD5加密） | 空 |

> 使用 `/密码转md5 your_password` 命令可以将明文密码转换为MD5格式

## 使用方法

### 基本命令

1. **生成插件**
   ```
   /生成插件 <插件功能描述>
   ```
   示例:
   ```
   /生成插件 创建一个天气查询插件，可以通过城市名称查询天气信息
   ```

2. **查看插件生成状态**
   ```
   /插件生成状态
   ```

3. **密码转MD5**
   ```
   /密码转md5 <明文密码>
   ```
   用于生成API密码的MD5哈希值

### 使用流程

1. 配置好 LLM 提供商
2. 使用 `/生成插件` 命令并提供插件功能描述
3. 等待插件生成过程完成
4. 根据提示确认安装插件

## 工作原理

CodeMage 插件生成过程包括以下步骤:

1. **需求分析**: 使用LLM分析用户提供的插件描述
2. **元数据生成**: 生成插件的基本信息（名称、作者、版本等）
3. **文档生成**: 创建插件的说明文档
4. **代码生成**: 生成插件的核心代码
5. **代码审查**: 对生成的代码进行质量检查和修复
6. **打包安装**: 将插件打包并安装到 AstrBot

## 安全机制

- 反向提示词过滤，防止生成恶意内容
- 代码审查机制，确保生成代码的安全性
- 管理员权限控制，限制插件生成权限
- 严格的依赖控制，默认不允许外部依赖

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！
