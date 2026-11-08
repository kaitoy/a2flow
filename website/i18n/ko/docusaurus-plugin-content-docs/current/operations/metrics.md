---
title: 운영 메트릭
sidebar_position: 6
---

# 운영 메트릭

워크플로 운영 데이터(승인 적체, 실행량, 실패, 리드 타임)는 외부 대시보드용으로 두 가지 형태로 제공됩니다. 둘 다 호출자의 테넌트로 범위가 제한되며, 아래에 언급된 실패 목록을 제외하면 인증된 사용자라면 누구나 사용할 수 있습니다.

[액세스 제어 태그](../guides/tags.md#access-control-tags)가 호출자에게 숨기는 실행은, 실행 목록 자체에 나타나지 않는 것과 똑같이 아래의 모든 보기에서 제외되므로, 메트릭이 읽는 사람이 열 수 없는 실행을 언급하는 일은 없습니다.

아직 `초안`인 워크플로에서 시작된 실행(개발자나 슈퍼 관리자의 [게시 전 테스트 실행](../guides/workflows.md#running-a-workflow))은 `isDraft: true`로 기록되고 **아래의 모든 메트릭에서 제외됩니다**. Prometheus KPI와, 승인 적체 보기를 포함한 집계 하위 리소스 모두 마찬가지이므로, 버려지는 테스트 데이터가 수치를 왜곡하지 않습니다. 이 플래그는 실행이 시작될 때 고정되며, 나중에 워크플로를 게시해도 이미 일어난 실행은 다시 분류되지 않습니다.

## Prometheus 엔드포인트 {#prometheus-endpoint}

`GET /api/v1/metrics`는 단일 값 KPI를 [Prometheus](https://prometheus.io/) 텍스트 노출 형식으로 렌더링합니다. 모든 샘플에는 `tenant` 레이블이 붙습니다.

승인:

| 메트릭 | 의미 |
|---|---|
| `a2flow_approvals_pending` | 결정을 기다리는 승인 요청 |
| `a2flow_approvals_pending_over_threshold{threshold}` | 그중 임곗값(기본값 24시간)보다 오래 기다리는 요청 |
| `a2flow_approval_pending_age_seconds_max` | 가장 오래 기다린 요청의 대기 시간 |
| `a2flow_approvals_decided_today{decision}` | 오늘 결정된 승인(`approved` / `rejected` / `returned`별) |

워크플로 실행:

| 메트릭 | 의미 |
|---|---|
| `a2flow_workflow_executions_active` | 현재 진행 중인 실행(`running` 또는 `scheduled`) |
| `a2flow_workflow_executions_finished_today{status}` | 오늘 완료된 실행(종료 상태별) |
| `a2flow_workflow_executions_started_recently{window,workflow}` | 최근 24시간 동안 시작된 실행(워크플로별) |
| `a2flow_workflow_executions_failed_recently{window}` | 최근 24시간 동안 실패로 끝난 실행 |
| `a2flow_workflow_tasks_failed_recently{window,error_kind}` | 최근 24시간 동안 실패한 작업(원인별) |
| `a2flow_workflow_execution_lead_time_seconds_avg{window,workflow}` | 최근 24시간 동안 완료된 실행의 시작부터 종료까지의 평균 소요 시간 |

알림 이메일:

| 메트릭 | 의미 |
|---|---|
| `a2flow_email_queue_depth{status}` | [발신 대기열](../guides/notifications.md#the-delivery-queue)에 있는 이메일(`pending` / `sending` / `sent` / `failed`별) |
| `a2flow_email_queue_oldest_pending_age_seconds` | 전송되지 않은 이메일 중 가장 오래 기다린 것의 대기 시간입니다. 릴레이에 접근할 수 없으면 증가합니다 |

`?thresholdHours=`는 지연된 승인의 기준을 재정의합니다. `TIMEZONE`(IANA 이름, 기본값 `UTC`, [서버 설정](./configuration.md#server-settings) 참조)이 "오늘"의 시작 시점을 결정하며, 인식할 수 없는 이름은 시작 실패 대신 UTC로 대체됩니다.

이 엔드포인트는 일반 세션 쿠키로 보호되므로 스크레이프 구성에 쿠키를 포함해야 합니다. `GET`은 안전한 메서드이므로 CSRF 토큰은 필요 없습니다.

```yaml
- job_name: a2flow
  metrics_path: /api/v1/metrics
  http_headers:
    Cookie: { values: ["a2flow_session=<token>"] }
```

세션의 유휴 타임아웃은 요청할 때마다 연장되므로, 계속 실행되는 스크레이프는 자신의 세션을 무기한 유지합니다. 다만 백엔드 재시작이나 명시적 로그아웃 후에는 세션이 유지되지 않으며, 그때 토큰을 새로 고쳐야 합니다. 스크레이프 하나는 정확히 하나의 테넌트만 다룹니다. 여러 테넌트를 모니터링하려면 테넌트마다 job을 하나씩 구성하세요.

## 집계 하위 리소스 {#aggregate-sub-resources}

사용자 ID, 실행 ID, 자유 형식 오류 메시지가 자연 키가 되는 항목은 의도적으로 Prometheus에 넣지 않습니다. 레이블 집합이 무한히 늘어나기 때문입니다. 이런 보기는 대신 기존 컬렉션의 JSON 하위 리소스로, 일반적인 `{meta, data, error}` 엔벨로프에 담아 제공합니다.

| 엔드포인트 | 반환 값 |
|---|---|
| `GET /api/v1/workflow-executions/by-workflow` | 워크플로별 실행 수(`total` / `running` / `completed` / `failed`, `running`에는 `scheduled` 실행 포함)와 평균 리드 타임 |
| `GET /api/v1/workflow-executions/lead-time-trend` | 일별 평균 리드 타임. 빈 날을 포함해 달력상의 하루마다 버킷 하나 |
| `GET /api/v1/workflow-executions/failures` | 조치가 필요한 실행과, 각 실행의 실패한 작업 및 기록된 원인. 호출자가 관여하지 않은 실행의 작업 제목과 오류 메시지를 인용하므로 관리자 전용입니다 |
| `GET /api/v1/approvals/by-approver` | 지정된 승인자별 승인 대기 적체 |
| `GET /api/v1/approvals/by-workflow` | 같은 적체를 워크플로별로 묶은 것 |

실행 엔드포인트는 `since` / `until`(ISO-8601, 기본값은 최근 30일, 최대 366일)과 `limit`을 받고, 승인 엔드포인트는 `thresholdHours`(기본값 24)와 `limit`을 받습니다. 적체 항목은 단일 대기 시간이 가장 긴 순서로 반환되므로 `?limit=5`는 최악의 5건입니다. 소요 시간은 항상 초 단위 정수입니다.

`by-approver`는 승인의 **대상**(사용자 또는 그룹일 수 있음)으로 묶습니다. 각 항목에는 이를 구분하는 `groupKind`(`"user"` 또는 `"group"`)가 있으며, `"user"` 항목은 ID만 제공하고 `"group"` 항목은 `groupLabel`에 그룹 이름도 담습니다.

실패한 작업은 **이유**를 기록합니다. `error_kind`(`api_error`, `timeout`, `script_error`, `invalid_input`, `permission_denied`, `rejected`, `other` 중 하나)와 자유 형식 `error_message`가 `status="failed"`와 함께 저장됩니다. 둘 다 일반 작업 필드이므로 작업 목록을 이 값으로 필터링할 수 있습니다(예: `?q=errorKind:eq:timeout`).
