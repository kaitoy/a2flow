---
title: Configuration du LLM
sidebar_position: 3
---

# Configuration du LLM

Définissez `SYSTEM_DEFAULT_LLM_MODEL` (le modèle) et `SYSTEM_DEFAULT_LLM_API_KEY` (sa clé d'API) dans `backend/.env` :

| Fournisseur | Valeur |
|---|---|
| Google Gemini (par défaut) | `gemini-3.8-flash` |
| OpenAI via LiteLLM | `litellm:openai/gpt-6.1-sol` |
| Anthropic via LiteLLM | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock via LiteLLM | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

Ce sont le LLM par défaut du système. Le backend les écrit dans [Paramètres système](../guides/system-settings.md#llm) à chaque démarrage : une variable définie l'emporte donc toujours sur cet écran ; laissez-en une non définie pour modifier ce champ sur l'écran. Voir [LLM](../operations/configuration.md#llm) pour les règles exactes. Un tenant peut utiliser un autre modèle ou une clé qui lui est propre : voir [Le LLM du tenant](../guides/users-and-groups.md#tenant-llm).

Un agent utilise ces valeurs dans l'ordre suivant. Chaque champ passe au suivant indépendamment : un tenant qui ne définit qu'un modèle utilise donc toujours la clé du système :

| Ordre | Source |
|---|---|
| 1 | Le LLM propre au tenant, lorsqu'un Super administrateur lui en a donné un |
| 2 | Le LLM du système, sur l'écran Paramètres système |
| 3 | Le modèle par défaut intégré, `gemini-3.8-flash` |

Si aucune clé n'est définie à ces deux endroits, la variable propre au fournisseur est lue comme avant : `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` ou `AWS_BEARER_TOKEN_BEDROCK`.

Tous les autres paramètres du backend sont décrits dans la [Référence de configuration](../operations/configuration.md).

## Gemini (par défaut) {#gemini-default}

```env
SYSTEM_DEFAULT_LLM_MODEL=gemini-3.8-flash
SYSTEM_DEFAULT_LLM_API_KEY=your_google_api_key_here
```

## OpenAI (via LiteLLM) {#openai-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:openai/gpt-6.1-sol
SYSTEM_DEFAULT_LLM_API_KEY=your_openai_api_key_here
```

## Anthropic (via LiteLLM) {#anthropic-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock (via LiteLLM) {#amazon-bedrock-via-litellm}

Les paquets `boto3` et `botocore[crt]` nécessaires à cette voie sont fournis avec le backend : il n'y a donc aucune installation supplémentaire à effectuer.

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_bedrock_bearer_token_here
```
