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

バックエンドのそれ以外の設定は[設定リファレンス](../operations/configuration.md)にまとめてあります。

## Gemini(既定)

```env
LLM_MODEL=gemini-3.5-flash
GOOGLE_API_KEY=your_google_api_key
```

## OpenAI(LiteLLM 経由)

```env
LLM_MODEL=litellm:openai/gpt-4o
OPENAI_API_KEY=your_openai_api_key
```

## Anthropic(LiteLLM 経由)

```env
LLM_MODEL=litellm:anthropic/claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=your_anthropic_api_key
```

## エージェントへの指示

```env
AGENT_INSTRUCTION=You are a helpful assistant. Answer concisely and clearly.
```
