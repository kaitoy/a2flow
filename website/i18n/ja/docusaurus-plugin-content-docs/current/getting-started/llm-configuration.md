---
title: LLM の設定
sidebar_position: 3
---

# LLM の設定

`backend/.env` の `LLM_MODEL` を設定します。

| プロバイダ | 値 |
|---|---|
| Google Gemini(既定) | `gemini-3.5-flash` |
| OpenAI(LiteLLM 経由) | `litellm:openai/gpt-4o` |
| Anthropic(LiteLLM 経由) | `litellm:anthropic/claude-3-5-sonnet-20241022` |
| Amazon Bedrock(LiteLLM 経由) | `litellm:bedrock/global.anthropic.claude-sonnet-4-6` |

バックエンドのそれ以外の設定は[設定リファレンス](../operations/configuration.md)にまとめてあります。

## Gemini(既定)

```env
LLM_MODEL=gemini-3.5-flash
GOOGLE_API_KEY=your_google_api_key_here
```

## OpenAI(LiteLLM 経由)

```env
LLM_MODEL=litellm:openai/gpt-4o
OPENAI_API_KEY=your_openai_api_key_here
```

## Anthropic(LiteLLM 経由)

```env
LLM_MODEL=litellm:anthropic/claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock(LiteLLM 経由)

この経路が必要とする `boto3` と `botocore[crt]` はバックエンドに同梱されているため、追加のインストールは不要です。

```env
LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-4-6
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_bearer_token_here
```
