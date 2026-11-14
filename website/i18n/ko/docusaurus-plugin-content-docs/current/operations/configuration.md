---
title: 구성 참조
sidebar_position: 2
---

# 구성 참조

아래의 모든 설정은 환경 변수입니다. 백엔드는 `backend/.env`에서 읽습니다(주석이 달린 템플릿은 [backend/.env.example](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example)입니다). 프런트엔드 변수 두 개는 프런트엔드 자체의 프로세스 환경에서 읽습니다. 모델과 API 키 설정은 [LLM 설정](../getting-started/llm-configuration.md) 페이지에서 따로 다룹니다.

## 서버 설정 {#server-settings}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `HOST` | `0.0.0.0` | 백엔드가 바인딩하는 주소 |
| `PORT` | `8000` | 백엔드가 바인딩하는 포트 |
| `RELOAD` | `false` | 로컬 개발용 uvicorn 자동 리로드입니다. 백엔드를 `python -m backend.main`으로 시작할 때만 읽으며, Docker 이미지 자체의 시작 명령은 어느 쪽이든 영향을 받지 않습니다 |
| `TIMEZONE` | `UTC` | 배포의 현지 시간대를 나타내는 IANA 이름입니다. [운영 메트릭](./metrics.md)에서 달력상의 하루가 시작되는 시점, 즉 "오늘" 집계와 리드 타임 추세의 일별 버킷을 결정하며, 작업의 시간 요구 사항에 시간대가 명시되지 않았을 때 워크플로 에이전트가 그 요구 사항을 해석하는 시간대이기도 합니다. 인식할 수 없는 이름은 시작 실패 대신 `UTC`로 대체되므로, 오타가 있으면 앱이 멈추는 대신 현지 시간이 어긋납니다 |

## 프런트엔드 설정 {#frontend-settings}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | 리버스 프록시가 먼저 `/api/*`를 백엔드로 라우팅하지 않을 때(컨테이너 없이 실행할 때) 프런트엔드가 `/api/*`를 전달하는 대상이며, API 문서 페이지가 로그인한 세션을 확인하는 대상이기도 합니다. 프로세스 시작 시 한 번만 읽습니다. Docker Compose 스택에서는 공개 주소가 아니라 내부 네트워크상의 백엔드 주소입니다 |
| `APP_PORT` | `3000` | Docker Compose 전용입니다. 앱이 공개되는 호스트 포트, 즉 화면과 API를 모두 제공하는 `ingress` 서비스의 포트입니다. 백엔드의 `CORS_ORIGINS`는 자동으로 이 값을 따릅니다 |
| `APP_DOMAIN` | `localhost` | `compose.https.yml`을 사용하는 Docker Compose 전용입니다. HTTPS로 앱을 제공하는 호스트 이름입니다. 공개 이름이면 Let's Encrypt에서, `localhost`이면 로컬 인증 기관에서 인증서를 받습니다. 백엔드의 `CORS_ORIGINS`와 `APP_BASE_URL`은 자동으로 이 값을 따르고, `SESSION_COOKIE_SECURE`는 켜집니다. [HTTPS로 제공하기](../getting-started/docker-compose.md#https)를 참조하세요 |
| `OPENBAO_PORT` | `8200` | `--profile openbao`를 사용하는 Docker Compose 전용입니다. OpenBao UI가 공개되는 호스트 포트입니다. [OpenBao로 Vault 시크릿 사용해 보기](../getting-started/docker-compose.md#openbao)를 참조하세요. A2Flow는 이 값과 관계없이 내부 네트워크로 접근합니다 |

## 애플리케이션 데이터베이스 {#application-database}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` | `sqlite:///a2flow.db` | 데이터베이스 URL입니다. SQLite(작업 디렉터리 기준 상대 경로)와 PostgreSQL을 지원합니다 |
| `DB_POOL_SIZE` | `5` | PostgreSQL 전용입니다. 백엔드 프로세스의 연결 풀 두 개가 각각 열어 두는 연결 수입니다. 최소 `1`입니다. 레플리카 전체에서 합산되는 방식은 [연결 풀링](./scaling.md#connection-pooling)을 참조하세요 |
| `DB_MAX_OVERFLOW` | `10` | PostgreSQL 전용입니다. 부하가 높을 때 각 풀이 `DB_POOL_SIZE`에 더해 추가로 열 수 있는 연결 수이며, 부하가 지나가면 다시 닫힙니다. 최소 `0`입니다 |

비동기 드라이버 접미사(`sqlite+aiosqlite` / `postgresql+asyncpg`)는 자동으로 추가되므로 일반 스킴만으로 충분합니다.

```env
DB_URL=postgresql://user:password@localhost:5432/a2flow
```

스키마 변경은 버전이 지정된 [Alembic](https://alembic.sqlalchemy.org/) 마이그레이션으로 관리되며 시작 시 자동으로 적용되므로, 앱을 다시 배포하면 스키마가 최신 상태가 됩니다. 백엔드 레플리카를 둘 이상 실행하려면 PostgreSQL이 필요합니다. [수평 확장](./scaling.md)을 참조하세요. 각 테이블의 내용은 [데이터베이스](../architecture/database.md)에 있습니다.

## 초기 사용자 {#seeded-users}

시작 시 백엔드는 숨겨진 **시스템 사용자**와 실제 계정 두 개를 생성합니다. 각 계정은 대상 레코드가 없음을 발견한 최초의 시작에서만 생성됩니다.

- **슈퍼 관리자** 역할을 가진 초기 **`root`** 사용자입니다([권한 부여](../concepts/authorization.md) 참조). 플랫폼 범위입니다(`tenantId: null`). 실제(시스템 외) 사용자가 *한 명이라도* 있으면 건너뛰므로 맨 처음 시작할 때만 실행됩니다.
- **Default** 테넌트(`slug: default`)와 그 안에서 **관리자** 역할을 가진 초기 **`admin`** 사용자입니다. 테넌트(`slug` 기준)와 사용자(해당 테넌트 내 `username` 기준)는 각각 따로 확인하므로, 어느 한쪽을 다시 만들어도 다른 쪽이 중복되지 않습니다.

숨겨진 **시스템 사용자**는 부트스트랩 레코드를 소유합니다(로그인할 수 없으며 사용자 목록에서 제외됩니다).

| 변수 | 기본값 | 설명 |
|---|---|---|
| `ROOT_PASSWORD` | 자동 생성 | 초기 `root` 사용자의 비밀번호 |
| `ADMIN_PASSWORD` | 자동 생성 | Default 테넌트에 있는 초기 `admin` 사용자의 비밀번호 |

둘 중 하나라도 설정되지 않았거나 비어 있으면 임의의 비밀번호가 생성되어, 해당 사용자를 만들 때 `WARNING` 수준으로 **한 번만** 로그에 기록됩니다. 그 로그 줄이 지나가고 나면 복구할 수 없습니다. 로컬 시험 이상의 용도라면 첫 실행 전에 둘 다 명시적으로 설정하거나, 시작 로그에서 생성된 비밀번호를 즉시 확보한 뒤 나중에 변경하세요. 사용자 이름은 `root`와 `admin`으로 고정되어 있습니다.

## 세션 수명 {#session-lifetime}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SESSION_IDLE_TIMEOUT_SECONDS` | `28800`(8시간) | 요청마다 연장되는 유휴 타임아웃입니다. 인증된 요청은 세션의 마지막 활동 시각을 갱신하는데, 갱신은 최대 5분에 한 번(이 값의 절반이 더 짧으면 그 간격에 한 번)이므로 세션이 그만큼 일찍 끝날 수 있습니다. 이 시간보다 오래 유휴 상태로 둔 세션은 거부되고 삭제됩니다 |
| `SESSION_COOKIE_SECURE` | `false` | 세션 쿠키와 CSRF 쿠키에 `Secure`(HTTPS 전용)를 표시합니다. HTTPS 뒤에 있는 모든 배포에서는 `true`로 설정하세요 |

쿠키 자체는 세션 쿠키(`Max-Age`/`Expires` 없음)이므로 브라우저를 닫을 때도 지워집니다. 브라우저는 프런트엔드와 같은 오리진으로 백엔드에 접근하므로(`/api/*`가 리버스 프록시 또는 프런트엔드 자체에서 경로 기준으로 백엔드로 라우팅됩니다) 쿠키는 퍼스트 파티가 되고 `SameSite=Lax`가 문제없이 적용됩니다.

## CORS {#cors}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | 백엔드 API를 호출할 수 있는 오리진의 쉼표로 구분된 목록 |

프런트엔드를 제공하는 오리진을 모두 추가하세요.

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*`는 시작 시 거부됩니다. `allow_credentials=True`가 항상 활성화되어 있으며, 와일드카드 오리진과 함께 쓰는 것은 CORS 사양상 유효하지 않기 때문입니다.

## 싱글 사인온 {#single-sign-on}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `OIDC_ALLOWED_PRIVATE_HOSTS` | 비어 있음 | 쉼표로 구분한 호스트 이름(예: `keycloak.internal,localhost`). 테넌트의 [싱글 사인온](../guides/single-sign-on.md) 발급자 URL이 사설 주소로 확인되더라도 이 호스트는 쓸 수 있습니다. 온프레미스 IdP용입니다. 그 밖의 발급자는 공개 주소로 확인되어야 합니다 |

싱글 사인온은 배포의 기본 URL에도 의존합니다. `APP_BASE_URL`([알림 이메일](#notification-email) 참조) 또는 [시스템 설정](../guides/system-settings.md)의 **애플리케이션 기본 URL**입니다. 없으면 싱글 사인온을 사용할 수 없고 **테넌트 설정**에 **리디렉션 URI** 대신 경고가 표시됩니다. 요건은 두 가지입니다.

- **기본 URL은 오리진만 씁니다.** 스킴, 호스트, 필요하면 포트까지이며 `https://a2flow.example.com`처럼 경로는 붙이지 않습니다. 경로가 있으면 모든 SSO 로그인이 실패합니다.
- **백엔드가 공개 오리진을 볼 수 있어야 합니다.** 리버스 프록시 뒤에서는 프록시가 요청을 전달할 때 원래의 `Host` 헤더를 유지하고 `X-Forwarded-Proto`를 원래 스킴으로 설정하게 하며, 프록시 주소를 `FORWARDED_ALLOW_IPS`에 적어 백엔드가 프록시를 신뢰하게 하세요(기본값으로는 `127.0.0.1`만 신뢰합니다). 그러지 않으면 SSO 로그인마다 리디렉션이 한 번 더 일어납니다.

## 에이전트 스킬 스토어 {#agent-skill-store}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SKILLS_DIR` | `backend/.skills` | 에이전트 스킬 저장소를 얕은 복제로 가져오는 스토어의 루트입니다. `docker compose`에서는 `/var/lib/a2flow/skills`이며 `skills` 명명된 볼륨을 사용합니다 |
| `SKILLS_PRUNE_GRACE_SECONDS` | `3600` | 참조 여부와 관계없이 리비전 디렉터리가 유지되는 시간입니다. 풀을 하면 어떤 실행도 고정하지 않은 리비전을 정리하는데, 이 유예 시간은 실행이 현재 리비전을 읽은 뒤 그것을 가리키는 행을 삽입하기까지의 틈을 메웁니다 |
| `SKILLS_CLONE_TIMEOUT_SECONDS` | `120` | 복제의 개별 HTTP 요청에 걸 수 있는 시간의 상한입니다. 이 값이 없으면 응답하지 않는 원격 저장소 때문에 복제가 무기한 멈추고 스킬이 `복제 중` 상태로 남습니다 |

스토어는 리비전마다 변경되지 않는 디렉터리를 하나씩 가지며, 게시된 리비전은 이후 수정되지 않으므로 풀이 기존 리비전을 로드 중인 에이전트를 방해하지 않습니다.

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

이것은 **캐시가 아니라 지속되는 상태**입니다. 워크플로 실행은 시작 시의 리비전에 고정되므로, 디렉터리를 지우면 관리자가 스킬을 다시 풀할 때까지 기존 실행은 스킬을 로드할 수 없습니다(HTTP 409 `SKILL_NOT_READY`). 게다가 풀은 고정된 리비전이 아니라 저장소의 현재 HEAD를 가져옵니다. 이 디렉터리를 백업하고([백업 및 복원](./backup.md)), 모든 백엔드 레플리카에 같은 디렉터리를 제공하세요([수평 확장](./scaling.md)).

## 지식 베이스 {#knowledge-bases}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `KNOWLEDGE_SOURCE_MAX_BYTES` | `20971520`(20 MiB) | [지식 베이스](../guides/knowledge-bases.md)에 업로드할 수 있는 문서와, 지식 베이스용으로 가져오는 웹 페이지의 최대 크기입니다. 이를 넘는 업로드는 넘는 즉시 거부됩니다 |
| `KNOWLEDGE_INGEST_CHUNK_CHARS` | `40000` | LLM이 한 번에 읽는 소스의 문자 수입니다. 더 긴 소스는 여러 부분으로 나누어 차례로 읽습니다. 컨텍스트 창이 작은 모델에서는 값을 낮추세요 |
| `KNOWLEDGE_FETCH_TIMEOUT_SECONDS` | `30` | 웹 페이지 소스를 가져올 때 요청당 허용되는 시간 |

소스와 페이지는 세션 파일처럼 데이터베이스에 저장되므로 별도의 볼륨이 필요 없습니다. 소스를 읽을 때는 에이전트에 구성된 LLM([LLM 설정](../getting-started/llm-configuration.md))을 호출하며, 큰 문서에서는 여러 번 호출합니다.

## 세션 파일 {#session-files}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SESSION_FILE_MAX_BYTES` | `20971520`(20 MiB) | [워크플로 세션](../guides/workflow-executions.md#files-in-the-session)에 첨부할 수 있는 파일 하나의 최대 크기입니다. 이를 넘는 즉시 업로드가 거부되므로 더 큰 본문이 통째로 메모리에 유지되는 일은 없습니다 |
| `SESSION_FILES_MAX_TOTAL_BYTES` | `209715200`(200 MiB) | 세션 하나가 보유하는 모든 파일의 합계 크기입니다. 파일은 해당 실행이 삭제될 때만 제거되므로, 오래 실행되는 세션의 상한은 이 값으로 정해집니다 |

세션 파일은 디스크가 아니라 데이터베이스에 저장되므로 전용 디렉터리도, 레플리카 간 공유 볼륨도 필요 없으며 데이터베이스 백업 외의 백업 단계도 없습니다([백업 및 복원](./backup.md)). 이 제한을 높이면 실행 하나가 차지할 수 있는 데이터베이스 용량과 업로드나 다운로드 한 번에 드는 메모리가 늘어납니다. 바이트를 통째로 읽기 때문입니다.

## 시크릿 관리 {#secret-management}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SECRET_ENCRYPTION_KEY` | — | `local` [시크릿](../guides/secrets.md)을 저장하기 전에 암호화하는 데 쓰는 Fernet 키 |
| `SECRET_KEY_FILE` | `.secret_key` | 디스크의 키 파일 경로로, SQLite 데이터베이스 파일 옆에 있습니다. `docker compose`에서는 `/var/lib/a2flow/secret-key/.secret_key`이며, 백엔드와 이메일 워커가 공유하는 `secret-key` 명명된 볼륨을 사용합니다 |

암호화 키는 처음 사용할 때 다음 순서로 결정됩니다.

1. `SECRET_ENCRYPTION_KEY`. 유효한 Fernet 키여야 합니다.
2. `SECRET_KEY_FILE`의 키 파일.
3. 둘 다 없으면 키를 생성해 그 파일에 저장하고 WARNING을 로그에 남깁니다.

**키를 백업하세요.** 키를 잃으면 저장된 로컬 시크릿을 모두 복호화할 수 없으며, [승인 CA](../architecture/approvals.md)의 서명 키도 같은 키로 보호됩니다.

HashiCorp Vault용 환경 변수는 없습니다. 테넌트 전용 Vault는 해당 테넌트의 관리자가 [테넌트 설정](../guides/users-and-groups.md#tenant-vault)에서, 전역 Vault의 주소는 슈퍼 관리자가 [시스템 설정](../guides/system-settings.md#global-vault)에서 설정하며, 전역 Vault에 대한 각 테넌트의 [자격 증명](../guides/users-and-groups.md#global-vault-credential)은 테넌트 페이지에서 설정합니다. 테넌트 전용 Vault 주소는 사용자가 입력하는 다른 URL과 같은 SSRF 검사를 거치므로 공개 주소여야 합니다. 전역 Vault 주소는 슈퍼 관리자만 설정할 수 있고 Vault는 보통 사설 주소에 있으므로 이 검사에서 제외됩니다.

## MCP 도구와 승인 {#mcp-tools-and-approvals}

모든 MCP 도구 호출은 호출하는 작업을 위해 발급된 수명이 짧은 X.509 인증서를 제시해야 합니다. 인증서는 작업의 [승인](../guides/approvals.md#human-approval)이 부여될 때, 또는 아무도 승인을 요청받지 않은 작업이 시작될 때 부여됩니다. 서명 루트는 처음 사용할 때 생성되어 로컬 시크릿과 같은 키로 암호화되어 저장되므로, 이 기능을 쓰기 위해 여기서 구성할 것은 없습니다.

| 변수 | 기본값 | 제한 대상 |
|---|---|---|
| `MCP_TOOL_CERT_TTL_SECONDS` | `3600` | 작업의 인증서가 유효한 시간으로, 작업이 도구를 호출할 수 있는 기간입니다 |
| `MCP_TOOL_CERT_SIGNATURE_WINDOW_SECONDS` | `60` | 프록시를 거치는 각 호출에 첨부되는 소유 증명 서명에 허용되는 시계 오차 |
| `MCP_CA_COMMON_NAME` / `MCP_CA_VALIDITY_DAYS` | `A2Flow MCP Approval CA` / `3650` | 생성되는 루트의 주체와 유효 기간입니다. 루트를 처음 생성할 때만 읽으며, 나중에 바꿔도 기존 루트에는 영향이 없습니다 |
| `MCP_REGISTRY_URL` | `https://registry.modelcontextprotocol.io` | [레지스트리 찾아보기](../guides/mcp-servers.md#registering-from-the-mcp-registry) 대화 상자가 검색하는 레지스트리의 기본 URL |
| `MCP_ELICITATION_TIMEOUT_SECONDS` | `900` | MCP 서버의 [확인 요청](../guides/workflow-executions.md#mcp-server-confirmations)에 실행 시작자가 답하기를 도구 호출이 기다리는 시간으로, 이 시간이 지나면 질문이 만료됩니다. 시작자는 방금 작업을 재개한 상태이므로 이 값은 방치된 질문에만 적용됩니다 |
| `AGENT_TURN_TIMEOUT_SECONDS` | `3600` | 실행의 에이전트 턴 하나가 지속될 수 있는 최대 시간으로, 대기 시간도 포함됩니다. 도구 호출이 사람을 기다리는 턴도 여전히 실행 중이므로 `MCP_ELICITATION_TIMEOUT_SECONDS`보다 충분히 크게 유지하세요 |

## MCP 프록시 {#mcp-sandbox}

등록된 MCP 서버는 A2Flow의 코드가 아니므로 에이전트 및 그 시크릿과 [분리된 곳](../architecture/mcp-gateway-and-proxy.md#the-sandbox)에서 실행됩니다. Docker Compose 배포는 이 모든 것을 설정해 둡니다. 컨테이너를 직접 구성하는 배포는 여기서 설정합니다.

설정하지 않으면(일반 로컬 실행이 이 경우입니다) 에이전트가 자체 프로세스 안에서 MCP 서버에 직접 접근합니다. 개발에는 편리하지만, 누구나 서버를 등록할 수 있는 환경에서는 바람직하지 않습니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `MCP_PROXY_URL` | 미설정 | 프록시의 위치입니다. 이 값을 설정하면 MCP 서버가 에이전트 프로세스 밖으로 옮겨집니다 |
| `MCP_PROXY_SERVER_NAME` / `MCP_PROXY_PORT` | `mcp-proxy` / `8443` | 프록시에 접근할 때 쓰는 이름과 프록시가 수신 대기하는 포트입니다. 이름은 인증서의 일부이므로 양쪽이 일치해야 합니다 |
| `MCP_PROXY_TLS_DIR` | 애플리케이션 옆의 디렉터리 | 프록시가 자신을 증명하는 데 필요한 자료를 에이전트가 게시하는 위치입니다. 프록시는 같은 디렉터리를 읽기 전용으로 읽습니다 |
| `MCP_BACKEND_TLS_DIR` | 애플리케이션 옆의 디렉터리 | 에이전트가 *자신의* 키를 보관하는 위치입니다. 의도적으로 위의 디렉터리와 분리되어 있으며, 프록시에서 실행되는 어떤 것도 이 키를 읽을 수 없어야 합니다 |
| `MCP_TRANSPORT_CERT_VALIDITY_DAYS` | `365` | 그 자료의 수명입니다. 남은 기간이 30일 미만이 되면 자동으로 재발급되므로 신경 쓸 필요가 없습니다 |
| `MCP_SANDBOX_DIR` | 미설정 | [샌드박스화된 서버 실행](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox)에 쓰이는 테넌트별 홈 디렉터리의 위치입니다. 테넌트의 서버가 다운로드한 패키지가 테넌트별 디렉터리로 나뉘어 이곳에 보관됩니다. 설정하면 로컬에서 시작하는 모든 서버가 각자의 샌드박스에서 실행되며, 프록시는 이 값 없이 시작하지 않습니다. 일반 로컬 실행에서는 설정하지 않으며, 이때 서버는 샌드박스 없이 시작됩니다 |

## 알림 이메일 {#notification-email}

이 값들은 관리 UI의 [시스템 설정](../guides/system-settings.md)에서 편집하는 값과 같으며, 배포가 메일 구성을 수동 단계로 남겨 두지 않고 함께 제공할 수 있도록 환경 변수로도 설정할 수 있습니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `APP_BASE_URL` | — | 사용자가 브라우저에서 이 배포에 접근하는 기본 URL입니다(예: `https://a2flow.example.com`). 발신 알림 이메일의 딥 링크를 만드는 데 쓰이며, 없으면 앱으로 돌아가는 링크 없이 메시지가 전송됩니다 |
| `SMTP_ENABLED` | `false` | 이메일 전송의 마스터 스위치입니다. 명시적으로 `true`여야 하며, 다른 변수가 설정되어 있다고 해서 자동으로 추론되지 않습니다 |
| `SMTP_HOST` / `SMTP_PORT` | — / `587` | 메시지를 넘겨줄 릴레이입니다. 여기에는 내부 호스트 이름만 써도 됩니다. 이 값은 SMTP 클라이언트에 넘겨질 뿐 가져오기 대상이 아닙니다 |
| `SMTP_SECURITY` | `starttls` | `none`, `starttls`, `ssl` 중 하나 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | — | SMTP AUTH 자격 증명입니다. 비밀번호는 암호문으로만 저장되며, 로그에 남지 않고 어떤 API 응답으로도 반환되지 않습니다 |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | — | 보내는 주소(전송을 켜면 필수)와 그 옆에 표시되는 선택적 표시 이름 |

이 페이지의 다른 설정과 달리 이 값들은 사용할 때마다 새로 읽지 않고 단일 설정 레코드에 기록됩니다. 그래서 별도의 규칙이 적용됩니다.

- **처음뿐 아니라 시작할 때마다 다시 적용됩니다.** 따라서 릴레이 비밀번호 교체는 재배포로 이루어집니다.
- **실제로 설정한 변수만 기록됩니다.** 설정하지 않은 변수는 관리자가 UI에서 직접 구성한 내용을 포함해 저장된 값을 그대로 유지합니다.
- **잘못된 값은 경고로 로그에 남고 통째로 건너뜁니다.** 잘못된 포트나 주소, 또는 호스트 없는 `SMTP_ENABLED=true`는 저장된 구성을 건드리지 않으며, 앱은 그대로 시작됩니다.

활성화 플래그가 분리되어 있으므로, 릴레이의 호스트와 자격 증명을 한 번의 배포에서 미리 준비해 두고 전송은 이후 배포에서 켤 수 있습니다.

## 발신 이메일 대기열 {#outgoing-email-queue}

릴레이로 내보내는 대기열의 조정 값입니다. 동작은 [전송 대기열](../guides/notifications.md#the-delivery-queue)을 참조하세요. 일반적인 배포에서는 여기서 설정할 것이 없습니다.

| 변수 | 기본값 | 설명 |
|---|---|---|
| `EMAIL_WORKER_IN_PROCESS` | `true` | API 프로세스가 대기열 처리 워커도 실행할지 여부입니다. 켜져 있으면 `uvicorn main:app`만으로 메일이 전송됩니다. 전용 워커 프로세스를 실행할 때는 false로 설정하세요. [프로세스 구성](./deployment.md#process-layout)을 참조하세요. 둘 다 켜 두어도 안전하지만 의미는 없습니다. 권고 잠금이 배포 전체에서 정확히 하나의 발신자를 선출합니다 |
| `EMAIL_SEND_RATE_PER_SECOND` | `5.0` | 릴레이에 넘기는 초당 메시지 수입니다. 워커는 보내기 전마다 `1 / rate`만큼 쉽니다. 릴레이 제한이 더 엄격하면 그 아래로 낮추세요 |
| `EMAIL_QUEUE_BATCH_SIZE` / `EMAIL_QUEUE_POLL_INTERVAL_SECONDS` | `20` / `5.0` | 대기열 처리 한 번에 가져오는 메시지 수와, 대기열이 비어 있을 때 워커가 잠자는 시간입니다. 폴링 간격은 워커가 잠든 동안 생성된 알림의 전송 지연 하한입니다 |
| `EMAIL_MAX_ATTEMPTS` | `9` | 메시지가 데드 레터가 되기 전까지의 전송 시도 횟수입니다. 백오프는 15초, 30초, 1분, 2분 순으로 늘어나 1시간에서 멈추므로, 기본값이면 약 1시간의 릴레이 중단을 버틸 수 있습니다. 릴레이가 영구 실패로 보고한 경우는 횟수와 상관없이 첫 시도에서 포기합니다 |
| `EMAIL_SENT_RETENTION_DAYS` | `30` | 전송된 메시지를 워커가 삭제하기 전까지 보관하는 기간입니다. 대기열 상태가 아니라 무엇을 보냈는지에 대한 기록입니다. 데드 레터는 삭제되지 않습니다 |

## 에이전트 {#agent}

| 변수 | 기본값 | 설명 |
|---|---|---|
| `EXECUTION_MAX_PARALLEL_SESSIONS` | `4` | 워크플로 실행 하나가 동시에 작업하는 세션의 최대 수로, 기본 세션과 작업 그래프가 분기할 때 포크되는 분기 세션을 합한 수입니다. 한도에 도달하면 준비된 작업은 새로 포크하지 않고 자신의 세션을 기다립니다. `1`은 포크를 끕니다. 최소 `1`입니다 |
| `ROLE_DESCRIPTION` | 일반적인 어시스턴트 설명 | 에이전트의 시스템 프롬프트를 구성하는 기반이 되는 역할 텍스트로, 워크플로 규칙 및 인터페이스 스키마와 함께 쓰입니다 |
| `SESSION_RUNNER_CONCURRENCY` | `4` | 레플리카 하나가 실행 자체를 위해 동시에 처리하는 턴의 수입니다. 대상은 시작 턴과 승인 결정 후의 재개입니다. 각 턴은 모델과의 실시간 대화이므로, 이 값은 아무도 보고 있지 않은 실행에 대해 레플리카가 하는 모델 호출을 제한합니다. 최소 `1`입니다 |
