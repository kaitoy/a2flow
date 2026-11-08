---
title: Configuration du LLM
sidebar_position: 3
---

# Configuration du LLM

Définissez `LLM_MODEL` dans `backend/.env` :

| Fournisseur | Valeur |
|---|---|
| Google Gemini (par défaut) | `gemini-3.8-flash` |
| OpenAI via LiteLLM | `litellm:openai/gpt-6.1-sol` |
| Anthropic via LiteLLM | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock via LiteLLM | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

Tous les autres paramètres du backend sont décrits dans la [Référence de configuration](../operations/configuration.md).

## Gemini (par défaut) {#gemini-default}

```env
LLM_MODEL=gemini-3.8-flash
GOOGLE_API_KEY=your_google_api_key_here
```

## OpenAI (via LiteLLM) {#openai-via-litellm}

```env
LLM_MODEL=litellm:openai/gpt-6.1-sol
OPENAI_API_KEY=your_openai_api_key_here
```

## Anthropic (via LiteLLM) {#anthropic-via-litellm}

```env
LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock (via LiteLLM) {#amazon-bedrock-via-litellm}

Les paquets `boto3` et `botocore[crt]` nécessaires à cette voie sont fournis avec le backend : il n'y a donc aucune installation supplémentaire à effectuer.

```env
LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_bearer_token_here
```
