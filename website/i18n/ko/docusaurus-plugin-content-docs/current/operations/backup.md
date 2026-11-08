---
title: 백업 및 복원
sidebar_position: 4
---

# 백업 및 복원

[세 가지](./deployment.md#state-that-has-to-persist)는 컨테이너가 사라져도 남아 있어야 합니다. 그 밖의 모든 것(등록된 MCP 서버, 워크플로, 사용자, 시스템 설정)은 데이터베이스의 행이므로 데이터베이스를 백업하면 함께 보호됩니다.

| 대상 | 백업 방법 | 복원 방법 |
|---|---|---|
| 데이터베이스 | `pg_dump` 또는 SQLite 파일 복사 | `pg_restore` 또는 파일을 제자리에 되돌리기 |
| 에이전트 스킬 스토어 | `SKILLS_DIR` 트리 복사 | 원래 위치에 다시 압축 해제 |
| 시크릿 암호화 키 | `SECRET_ENCRYPTION_KEY`의 값 또는 `SECRET_KEY_FILE`의 파일 | 같은 값을 설정하거나 같은 파일을 되돌리기 |

**데이터베이스와 키는 반드시 함께 복원하세요.** 이 키는 로컬 시크릿과 승인 CA의 서명 키를 *모두* 복호화하며, 둘 다 데이터베이스에 저장되어 있습니다. 다른 키와 함께 복원한 데이터베이스는 모든 시크릿을 읽을 수 없는 상태로 시작됩니다.

## 데이터베이스 {#the-database}

PostgreSQL의 경우입니다.

```bash
pg_dump --format=custom --file=a2flow-$(date +%F).dump "postgresql://user:password@host:5432/a2flow"
pg_restore --clean --if-exists --dbname="postgresql://user:password@host:5432/a2flow" a2flow-2026-01-31.dump
```

Docker Compose에서는 `db` 서비스에 직접 접속합니다.

```bash
docker compose exec -T db pg_dump -U a2flow -Fc a2flow > a2flow-$(date +%F).dump
docker compose exec -T db pg_restore -U a2flow -d a2flow --clean --if-exists < a2flow-2026-01-31.dump
```

SQLite는 `DB_URL`에 지정된 경로에 있는 파일 하나입니다. 앱이 실행 중일 때는 파일을 복사하지 말고 `sqlite3 a2flow.db ".backup out.db"`를 사용하세요.

복원한 데이터베이스에는 별도의 마이그레이션 단계가 필요 없습니다. 백엔드가 시작할 때 아직 적용되지 않은 [Alembic](https://alembic.sqlalchemy.org/) 마이그레이션을 적용하므로, 오래된 덤프를 새 빌드에 복원하고 시작하면 스키마가 최신 상태로 올라옵니다.

## 에이전트 스킬 스토어 {#the-agent-skill-store}

`SKILLS_DIR`는 스킬을 다시 등록해도 재구성할 수 없습니다. 스킬을 풀하면 저장소의 *현재* HEAD를 복제하므로, 이전 리비전에 고정된 실행은 그 리비전을 되찾지 못하고 스킬을 로드할 수 없는 상태로 남습니다. 이 디렉터리를 백업하세요.

게시된 리비전 디렉터리는 이후 수정되지 않으므로, 앱이 실행 중일 때 만든 복사본도 일관성이 유지됩니다.

```bash
tar -czf skills-$(date +%F).tgz -C /var/lib/a2flow/skills .
```

Docker Compose에서 스토어는 `skills` 명명된 볼륨입니다.

```bash
docker run --rm -v a2flow_skills:/skills -v "$PWD:/backup" alpine \
  tar -czf /backup/skills-$(date +%F).tgz -C /skills .
```

복원할 때는 빈 스토어에 아카이브를 다시 압축 해제한 뒤 백엔드를 시작합니다.

## 시크릿 암호화 키 {#the-secret-encryption-key}

`SECRET_ENCRYPTION_KEY`를 명시적으로 설정했다면 키는 이미 배포 구성을 보관하는 곳에 있으므로 여기서 더 할 일은 없습니다. 그 저장 위치 자체가 백업되는지만 확인하세요.

설정하지 않았다면 백엔드가 처음 사용할 때 키를 생성해 `SECRET_KEY_FILE`의 파일(기본값 `.secret_key`, SQLite 데이터베이스 파일 옆)에 기록해 둡니다. 이 파일이 유일한 사본입니다. 파일이 있는 머신이 아닌 다른 곳에 백업하고, 자격 증명으로 취급하세요.

Docker Compose에서 이 파일은 `secret-key` 명명된 볼륨에 있습니다.

```bash
docker run --rm -v a2flow_secret-key:/key -v "$PWD:/backup" alpine   cp /key/.secret_key /backup/secret_key-$(date +%F)
```

키 교체는 지원되지 않습니다. 기존 시크릿이 이전 키로 암호화되어 있기 때문입니다. [시크릿 관리](./configuration.md#secret-management)를 참조하세요.

## 복원 확인 {#checking-a-restore}

1. 백엔드를 시작하고 [`GET /api/v1/health`](./health.md)가 200을 반환하는지 확인합니다. 이는 데이터베이스에 접근할 수 있고 스키마가 최신이라는 증거입니다.
2. 관리 UI에서 `local` 유형의 [시크릿](../guides/secrets.md)을 엽니다. 오류 없이 열리면 키와 데이터베이스가 일치한다는 증거입니다.
3. 진행 중이던 [워크플로 실행](../guides/workflow-executions.md)을 엽니다. `SKILL_NOT_READY`를 보고하지 않고 재개되면 사용 중인 리비전과 함께 스킬 스토어가 복원되었다는 증거입니다.
