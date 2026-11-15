---
title: LLM 配置
sidebar_position: 3
---

# LLM 配置

在 `backend/.env` 中设置 `SYSTEM_DEFAULT_LLM_MODEL`（模型）和 `SYSTEM_DEFAULT_LLM_API_KEY`（对应的 API 密钥）：

| 提供商 | 值 |
|---|---|
| Google Gemini（默认） | `gemini-3.8-flash` |
| OpenAI（通过 LiteLLM） | `litellm:openai/gpt-6.1-sol` |
| Anthropic（通过 LiteLLM） | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock（通过 LiteLLM） | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

它们是系统的默认 LLM。后端每次启动都会把它们写入[系统设置](../guides/system-settings.md#llm)，因此已设置的变量总是优先于该界面；想在界面中更改某个字段，就不要设置对应的变量。确切规则见 [LLM](../operations/configuration.md#llm)。租户可以使用其他模型或自己的密钥，详见[租户的 LLM](../guides/users-and-groups.md#tenant-llm)。

代理按以下顺序使用这些设置。每个字段各自依次回退，因此只设置了模型的租户仍会使用系统的密钥：

| 顺序 | 来源 |
|---|---|
| 1 | 租户自己的 LLM（超级管理员为该租户设置过时） |
| 2 | 系统设置界面中系统的 LLM |
| 3 | 内置的默认模型 `gemini-3.8-flash` |

如果两处都没有密钥，则像以前一样读取提供商自己的环境变量：`GOOGLE_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 或 `AWS_BEARER_TOKEN_BEDROCK`。

后端的其他设置都在[配置参考](../operations/configuration.md)中有各自的说明。

## Gemini（默认） {#gemini-default}

```env
SYSTEM_DEFAULT_LLM_MODEL=gemini-3.8-flash
SYSTEM_DEFAULT_LLM_API_KEY=your_google_api_key_here
```

## OpenAI（通过 LiteLLM） {#openai-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:openai/gpt-6.1-sol
SYSTEM_DEFAULT_LLM_API_KEY=your_openai_api_key_here
```

## Anthropic（通过 LiteLLM） {#anthropic-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock（通过 LiteLLM） {#amazon-bedrock-via-litellm}

这种方式所需的 `boto3` 和 `botocore[crt]` 软件包已随后端提供，因此无需额外安装。

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_bedrock_bearer_token_here
```
