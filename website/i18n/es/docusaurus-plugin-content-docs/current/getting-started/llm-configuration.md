---
title: Configuración del LLM
sidebar_position: 3
---

# Configuración del LLM

Define `SYSTEM_DEFAULT_LLM_MODEL` (el modelo) y `SYSTEM_DEFAULT_LLM_API_KEY` (su clave de API) en `backend/.env`:

| Proveedor | Valor |
|---|---|
| Google Gemini (predeterminado) | `gemini-3.8-flash` |
| OpenAI a través de LiteLLM | `litellm:openai/gpt-6.1-sol` |
| Anthropic a través de LiteLLM | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock a través de LiteLLM | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

Estos son el LLM predeterminado del sistema. El backend los escribe en [Configuración del sistema](../guides/system-settings.md#llm) cada vez que arranca, así que una variable definida siempre prevalece sobre esa pantalla; deja una sin definir para cambiar ese campo en la pantalla. Consulta [LLM](../operations/configuration.md#llm) para ver las reglas exactas. Un tenant puede usar otro modelo o una clave propia: consulta [El LLM del tenant](../guides/users-and-groups.md#tenant-llm).

Un agente usa estos valores, en este orden. Cada campo pasa al siguiente por su cuenta, así que un tenant que solo define un modelo sigue usando la clave del sistema:

| Orden | Origen |
|---|---|
| 1 | El LLM propio del tenant, cuando un Superadministrador le ha dado uno |
| 2 | El LLM del sistema en la pantalla Configuración del sistema |
| 3 | El modelo predeterminado integrado, `gemini-3.8-flash` |

Si no hay clave en ninguno de los dos sitios, se lee como antes la variable propia del proveedor: `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` o `AWS_BEARER_TOKEN_BEDROCK`.

Todos los demás ajustes del backend tienen su propia página en la [Referencia de configuración](../operations/configuration.md).

## Gemini (predeterminado) {#gemini-default}

```env
SYSTEM_DEFAULT_LLM_MODEL=gemini-3.8-flash
SYSTEM_DEFAULT_LLM_API_KEY=your_google_api_key_here
```

## OpenAI (a través de LiteLLM) {#openai-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:openai/gpt-6.1-sol
SYSTEM_DEFAULT_LLM_API_KEY=your_openai_api_key_here
```

## Anthropic (a través de LiteLLM) {#anthropic-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock (a través de LiteLLM) {#amazon-bedrock-via-litellm}

Los paquetes `boto3` y `botocore[crt]` que necesita esta vía se incluyen con el backend, así que no hay ningún paso de instalación adicional.

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_bedrock_bearer_token_here
```
