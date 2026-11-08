---
title: Configuración del LLM
sidebar_position: 3
---

# Configuración del LLM

Define `LLM_MODEL` en `backend/.env`:

| Proveedor | Valor |
|---|---|
| Google Gemini (predeterminado) | `gemini-3.8-flash` |
| OpenAI a través de LiteLLM | `litellm:openai/gpt-6.1-sol` |
| Anthropic a través de LiteLLM | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock a través de LiteLLM | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

Todos los demás ajustes del backend tienen su propia página en la [Referencia de configuración](../operations/configuration.md).

## Gemini (predeterminado) {#gemini-default}

```env
LLM_MODEL=gemini-3.8-flash
GOOGLE_API_KEY=your_google_api_key_here
```

## OpenAI (a través de LiteLLM) {#openai-via-litellm}

```env
LLM_MODEL=litellm:openai/gpt-6.1-sol
OPENAI_API_KEY=your_openai_api_key_here
```

## Anthropic (a través de LiteLLM) {#anthropic-via-litellm}

```env
LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock (a través de LiteLLM) {#amazon-bedrock-via-litellm}

Los paquetes `boto3` y `botocore[crt]` que necesita esta vía se incluyen con el backend, así que no hay ningún paso de instalación adicional.

```env
LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_bearer_token_here
```
