---
title: 데이터베이스
sidebar_position: 7
---

# 데이터베이스

모든 영구 데이터는 `backend/.env`의 `DB_URL`로 선택한 하나의 관계형 데이터베이스에 저장됩니다.

| 백엔드 | `DB_URL` | 참고 |
|---|---|---|
| SQLite(기본값) | `sqlite:///a2flow.db` | 설정이 필요 없는 로컬 파일 |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Docker Compose 스택에서 사용 |

비동기 드라이버 접미사(`aiosqlite` / `asyncpg`)는 자동으로 추가됩니다. 스키마 변경은 버전이 지정된 [Alembic](https://alembic.sqlalchemy.org/) 마이그레이션으로 추적되며 시작 시 자동으로 적용됩니다. 앱을 다시 배포(컨테이너 재시작)하면 대기 중인 마이그레이션이 실행되므로 별도의 마이그레이션 단계가 필요 없습니다.

데이터베이스는 다중 레플리카 백엔드를 조정하는 역할도 합니다. 에이전트 실행은 SSE 스트림이 유지되는 동안 PostgreSQL 권고 잠금을 보유하므로, 하나의 대화를 두 레플리카가 동시에 구동하는 일은 없습니다. 이것이 무엇을 보호하는지, 연결 풀링에 어떤 제약을 주는지는 [수평 확장](../operations/scaling.md)을 참조하세요.

## 저장되는 내용 {#what-it-holds}

| 테이블 | 저장 내용 |
|---|---|
| `users` | 애플리케이션 사용자와 부여된 역할. [사용자와 그룹](../guides/users-and-groups.md) 참조 |
| `auth_sessions` | 서버 측 로그인 세션 |
| `login_failures` | 최근의 [로그인 실패](../guides/users-and-groups.md#failed-sign-ins). 반복적인 추측 시도에 대비해 계정을 잠그기 위해 집계하며, 하루가 지난 행은 제거됩니다 |
| `impersonation_events` | [대리 로그인](../concepts/impersonation.md) 세션의 감사 추적 |
| `agent_skills` | [에이전트 스킬](../guides/agent-skills.md) 정의와 각 스킬을 복제해 오는 저장소 |
| `mcp_servers` | 등록된 [MCP 서버](../guides/mcp-servers.md)와 그 연결 방법 |
| `knowledge_bases`, `knowledge_sources`, `knowledge_pages` | [지식 베이스](../guides/knowledge-bases.md): 각 지식 베이스의 업로드된 문서와 등록된 URL, 그리고 이를 바탕으로 작성된 페이지 |
| `secrets` | 로컬에 암호화되거나 Vault에서 참조되는, 이름이 붙은 [자격 증명 묶음](../guides/secrets.md) |
| `workflows` | [워크플로](../guides/workflows.md) 정의와 수명 주기 상태 |
| `workflow_task_templates` | 워크플로에 미리 디자인된 작업 목록 |
| `workflow_published_versions` | 게시 시점에 고정된 디자인. `수정됨` 워크플로는 이를 기준으로 실행됩니다 |
| `workflow_executions` | [실행](../guides/workflow-executions.md)당 한 행. 실행 시점의 워크플로와 스킬 메타데이터 스냅샷을 포함합니다 |
| `workflow_tasks` | 템플릿에서 복사된, 실행의 개별 작업 |
| `workflow_task_tool_bindings` | 작업에 연결된 MCP 도구 |
| `message_meta` | 두 공유 채팅의 메시지별 정보: 누가 메시지를 보냈고 어떤 작업이 진행 중이었는지 |

워크플로를 삭제하면 그 템플릿까지 함께 삭제되지만 과거의 실행은 그대로 남습니다. 실행은 일어난 일의 기록이지, 그 원본 디자인의 일부가 아니기 때문입니다.
