---
title: LLM 설정
sidebar_position: 3
---

# LLM 설정

`backend/.env`에서 `SYSTEM_DEFAULT_LLM_MODEL`(모델)과 `SYSTEM_DEFAULT_LLM_API_KEY`(해당 API 키)를 설정합니다.

| 제공자 | 값 |
|---|---|
| Google Gemini(기본값) | `gemini-3.8-flash` |
| LiteLLM을 통한 OpenAI | `litellm:openai/gpt-6.1-sol` |
| LiteLLM을 통한 Anthropic | `litellm:anthropic/claude-sonnet-5-5` |
| LiteLLM을 통한 Amazon Bedrock | `litellm:bedrock/global.anthropic.claude-sonnet-5-5` |

이 값들은 시스템의 기본 LLM입니다. 백엔드는 시작할 때마다 이 값들을 [시스템 설정](../guides/system-settings.md#llm)에 기록하므로, 설정된 변수가 항상 해당 화면보다 우선합니다. 화면에서 바꾸려는 필드는 변수를 설정하지 마세요. 정확한 규칙은 [LLM](../operations/configuration.md#llm)을 참조하세요. 테넌트는 다른 모델이나 자체 키로 실행할 수도 있습니다. [테넌트의 LLM](../guides/users-and-groups.md#tenant-llm)을 참조하세요.

에이전트는 다음 순서로 이 값들을 사용합니다. 항목마다 따로 다음 단계로 넘어가므로, 모델만 설정한 테넌트도 API 키는 시스템의 것을 사용합니다.

| 순서 | 출처 |
|---|---|
| 1 | 테넌트 자체 LLM(슈퍼 관리자가 테넌트에 지정한 경우) |
| 2 | 시스템 설정 화면의 시스템 LLM |
| 3 | 기본 제공 기본 모델 `gemini-3.8-flash` |

두 곳 모두 키가 없으면 예전처럼 제공자 자체의 환경 변수(`GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 또는 `AWS_BEARER_TOKEN_BEDROCK`)를 읽습니다.

그 밖의 백엔드 설정은 모두 [구성 참조](../operations/configuration.md) 아래의 해당 페이지에서 설명합니다.

## Gemini(기본값) {#gemini-default}

```env
SYSTEM_DEFAULT_LLM_MODEL=gemini-3.8-flash
SYSTEM_DEFAULT_LLM_API_KEY=your_google_api_key_here
```

## OpenAI(LiteLLM 사용) {#openai-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:openai/gpt-6.1-sol
SYSTEM_DEFAULT_LLM_API_KEY=your_openai_api_key_here
```

## Anthropic(LiteLLM 사용) {#anthropic-via-litellm}

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:anthropic/claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_anthropic_api_key_here
```

## Amazon Bedrock(LiteLLM 사용) {#amazon-bedrock-via-litellm}

이 경로에 필요한 `boto3`와 `botocore[crt]` 패키지는 백엔드에 포함되어 있으므로 따로 설치할 필요가 없습니다.

```env
SYSTEM_DEFAULT_LLM_MODEL=litellm:bedrock/global.anthropic.claude-sonnet-5-5
SYSTEM_DEFAULT_LLM_API_KEY=your_bedrock_bearer_token_here
```
