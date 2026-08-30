---
title: LLM configuration
sidebar_position: 3
---

# LLM configuration

Set `LLM_MODEL` in `backend/.env`:

| Provider | Value |
|---|---|
| Google Gemini (default) | `gemini-3.5-flash` |
| OpenAI via LiteLLM | `litellm:openai/gpt-4o` |
| Anthropic via LiteLLM | `litellm:anthropic/claude-3-5-sonnet-20241022` |
| Amazon Bedrock via LiteLLM | `litellm:bedrock/global.anthropic.claude-sonnet-4-6` |

Every other backend setting has its own page under [Configuration reference](../operations/configuration.md).

## Gemini (default)

```env
LLM_MODEL=gemini-3.5-flash
GOOGLE_API_KEY=your_google_api_key_here
```

## OpenAI (via LiteLLM)

```env
LLM_MODEL=litellm:openai/gpt-4o
OPENAI_API_KEY=your_openai_api_key_here
```

## Anthropic (via LiteLLM)

```env
LLM_MODEL=litellm:anthropic/claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock (via LiteLLM)

Bedrock is the one provider that needs extra packages — install them into the backend before starting it:

```bash
cd backend && uv add boto3 "botocore[crt]"
```

```env
LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-4-6
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_bearer_token_here
```
