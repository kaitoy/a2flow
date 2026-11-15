---
title: LLM configuration
sidebar_position: 3
---

# LLM configuration

Set `SYSTEM_DEFAULT_LLM_MODEL` (the model) and `SYSTEM_DEFAULT_LLM_API_KEY` (its API key) in `backend/.env`:

| Provider | Value |
|---|---|
| Google Gemini (default) | `gemini-3.8-flash` |
| OpenAI via LiteLLM | `litellm:openai/gpt-6.1-sol` |
| Anthropic via LiteLLM | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock via LiteLLM | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

These are the system's default LLM. The backend writes them into [System Settings](../guides/system-settings.md#llm) every time it starts, so a variable that is set always wins over that screen; leave one unset to change that field on the screen instead — see [LLM](../operations/configuration.md#llm) for the exact rules. A tenant can run on another model or a key of its own: see [The tenant's LLM](../guides/users-and-groups.md#tenant-llm).

An agent uses these, in this order. Each field falls through on its own, so a tenant that sets only a model still uses the system's key:

| Order | Source |
|---|---|
| 1 | The tenant's own LLM, when a Super Admin has given the tenant one |
| 2 | The system's LLM on the System Settings screen |
| 3 | The built-in default model, `gemini-3.8-flash` |

With no key in either place, the provider's own variable — `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` or `AWS_BEARER_TOKEN_BEDROCK` — is read as before.

Every other backend setting has its own page under [Configuration reference](../operations/configuration.md).

## Gemini (default)

```env
SYSTEM_DEFAULT_LLM_MODEL=gemini-3.8-flash
SYSTEM_DEFAULT_LLM_API_KEY=your_google_api_key_here
```

## OpenAI (via LiteLLM)

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:openai/gpt-6.1-sol
SYSTEM_DEFAULT_LLM_API_KEY=your_openai_api_key_here
```

## Anthropic (via LiteLLM)

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock (via LiteLLM)

The `boto3` and `botocore[crt]` packages this route needs ship with the backend, so there is no extra install step.

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_bedrock_bearer_token_here
```
