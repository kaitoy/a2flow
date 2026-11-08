---
title: 상태 확인
sidebar_position: 5
---

# 상태 확인

`GET /api/v1/health`는 오케스트레이터나 로드 밸런서가 백엔드 인스턴스에 트래픽을 보내도 되는지 판단하기 위해 주기적으로 호출하는 엔드포인트입니다. 인증이 필요 없으며, 일반적인 `{meta, data, error}` 엔벨로프 대신 단순 객체를 반환합니다.

| 조건 | 상태 | 본문 |
|---|---|---|
| 데이터베이스가 간단한 쿼리에 응답함 | `200` | `{"status": "ok"}` |
| 응답하지 않음 | `503` | `{"status": "unavailable"}` |

확인 내용은 이것이 전부입니다. 실패를 오류 페이지가 아니라 명확한 상태 코드로 알리고 액세스 로그에서 제외되므로, 몇 초마다 호출해도 비용이 들지 않고 로그가 지저분해지지 않습니다.

**liveness와 readiness 모두에 사용하세요.** 데이터베이스에 접근할 수 없는 백엔드는 쓸모 있는 것을 제공할 수 없고, 새 인스턴스는 시작이 끝난 뒤에야 200으로 응답하는데, 이때가 바로 [마이그레이션](../architecture/database.md)이 적용된 시점이기도 합니다. 롤아웃을 이 엔드포인트로 제어하면 롤링 배포가 스키마 작업이 아직 진행 중인 인스턴스로 트래픽을 보내는 일을 막을 수 있습니다.

Docker Compose는 이미 이렇게 합니다([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)).

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:8000/api/v1/health || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

어디에서 구성하든 확인에 시작 유예 시간을 주세요. 첫 시작에서는 마이그레이션을 적용하고 [초기 사용자](./configuration.md#seeded-users)를 생성하므로, 인스턴스가 평상시 재시작보다 응답에 오래 걸리는 것은 정상입니다.

프런트엔드에는 자체 상태 확인 라우트가 없습니다. 상태를 보유하지 않고 백엔드 외에는 의존하는 것이 없으므로, 루트에 대한 일반 HTTP 요청이면 확인에 충분합니다.

실행 중인 배포의 수치(승인 적체, 실행량, 실패, 리드 타임, 이메일 대기열 깊이)는 [운영 메트릭](./metrics.md)을 참조하세요.
