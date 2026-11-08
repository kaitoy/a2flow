---
title: LLM 설정
sidebar_position: 3
---

# LLM 설정

`backend/.env`에서 `LLM_MODEL`을 설정합니다.

| 제공자 | 값 |
|---|---|
| Google Gemini(기본값) | `gemini-3.8-flash` |
| LiteLLM을 통한 OpenAI | `litellm:openai/gpt-6.1-sol` |
| LiteLLM을 통한 Anthropic | `litellm:anthropic/claude-sonnet-5-5` |
| LiteLLM을 통한 Amazon Bedrock | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

그 밖의 백엔드 설정은 모두 [구성 참조](../operations/configuration.md) 아래의 해당 페이지에서 설명합니다.

## Gemini(기본값) {#gemini-default}

```env
LLM_MODEL=gemini-3.8-flash
GOOGLE_API_KEY=your_google_api_key_here
```

## OpenAI(LiteLLM 사용) {#openai-via-litellm}

```env
LLM_MODEL=litellm:openai/gpt-6.1-sol
OPENAI_API_KEY=your_openai_api_key_here
```

## Anthropic(LiteLLM 사용) {#anthropic-via-litellm}

```env
LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock(LiteLLM 사용) {#amazon-bedrock-via-litellm}

이 경로에 필요한 `boto3`와 `botocore[crt]` 패키지는 백엔드에 포함되어 있으므로 따로 설치할 필요가 없습니다.

```env
LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
AWS_BEARER_TOKEN_BEDROCK=your_bedrock_bearer_token_here
```
