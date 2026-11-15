---
title: LLM の設定
sidebar_position: 3
---

# LLM の設定

`backend/.env` に `SYSTEM_DEFAULT_LLM_MODEL`(モデル)と `SYSTEM_DEFAULT_LLM_API_KEY`(その API キー)を設定します。

| プロバイダ | 値 |
|---|---|
| Google Gemini(既定) | `gemini-3.8-flash` |
| OpenAI(LiteLLM 経由) | `litellm:openai/gpt-6.1-sol` |
| Anthropic(LiteLLM 経由) | `litellm:anthropic/claude-sonnet-5-5` |
| Amazon Bedrock(LiteLLM 経由) | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

これらはシステムの既定の LLM です。バックエンドは起動するたびにこれらを[システム設定](../guides/system-settings.md#llm)へ書き込むので、設定してある変数は常にその画面より優先されます。画面で変更したい項目は、変数を未設定にしておきます。細かい決まりは [LLM](../operations/configuration.md#llm) を参照してください。テナントは別のモデルや専用の API キーで動かすこともできます。[テナントの LLM](../guides/users-and-groups.md#tenant-llm)を参照してください。

エージェントは次の順に、設定されているものを使います。項目ごとに順に見るので、モデルだけを設定したテナントでも、API キーにはシステムのものを使います。

| 順位 | 取得元 |
|---|---|
| 1 | そのテナント専用の LLM(上位管理者がテナントに設定した場合) |
| 2 | システム設定画面のシステムの LLM |
| 3 | 組み込みの既定モデル `gemini-3.8-flash` |

どちらにも API キーがない場合は、従来どおりプロバイダ固有の環境変数(`GOOGLE_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`AWS_BEARER_TOKEN_BEDROCK`)が使われます。

バックエンドのそれ以外の設定は[設定リファレンス](../operations/configuration.md)にまとめてあります。

## Gemini(既定) {#gemini-default}

```env
SYSTEM_DEFAULT_LLM_MODEL=gemini-3.8-flash
SYSTEM_DEFAULT_LLM_API_KEY=your_google_api_key_here
```

## OpenAI(LiteLLM 経由) {#openai-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:openai/gpt-6.1-sol
SYSTEM_DEFAULT_LLM_API_KEY=your_openai_api_key_here
```

## Anthropic(LiteLLM 経由) {#anthropic-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock(LiteLLM 経由) {#amazon-bedrock-via-litellm}

この経路が必要とする `boto3` と `botocore[crt]` はバックエンドに同梱されているため、追加のインストールは不要です。

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_bedrock_bearer_token_here
```
