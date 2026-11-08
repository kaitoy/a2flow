---
title: LLM 配置
sidebar_position: 3
---

# LLM 配置

在 `backend/.env` 中设置 `LLM_MODEL`：

| 提供商 | 值 |
|---|---|
| Google Gemini（默认） | `gemini-3.8-flash` |
| OpenAI（通过 LiteLLM） | `litellm:openai/gpt-6.1-sol` |
| Anthropic（通过 LiteLLM） | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock（通过 LiteLLM） | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

后端的其他设置都在[配置参考](../operations/configuration.md)中有各自的说明。

## Gemini（默认） {#gemini-default}

```env
LLM_MODEL=gemini-3.8-flash
GOOGLE_API_KEY=your_google_api_key_here
```

## OpenAI（通过 LiteLLM） {#openai-via-litellm}

```env
LLM_MODEL=litellm:openai/gpt-6.1-sol
OPENAI_API_KEY=your_openai_api_key_here
```

## Anthropic（通过 LiteLLM） {#anthropic-via-litellm}

```env
LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock（通过 LiteLLM） {#amazon-bedrock-via-litellm}

这种方式所需的 `boto3` 和 `botocore[crt]` 软件包已随后端提供，因此无需额外安装。

```env
LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_bearer_token_here
```
