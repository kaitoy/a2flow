---
title: 备份与恢复
sidebar_position: 4
---

# 备份与恢复

即使容器丢失，也必须保留下来的内容有[三项](./deployment.md#state-that-has-to-persist)。其余内容（已注册的 MCP 服务器、工作流、用户、系统设置）都是数据库中的行，备份数据库时会一并保留。

| 内容 | 备份方式 | 恢复方式 |
|---|---|---|
| 数据库 | `pg_dump`，或复制 SQLite 文件 | `pg_restore`，或把文件放回原处 |
| 代理技能存储库 | 复制 `SKILLS_DIR` 目录树 | 解压回原处 |
| 密钥加密密钥 | `SECRET_ENCRYPTION_KEY` 的值，或 `SECRET_KEY_FILE` 指向的文件 | 设置相同的值，或放回同一个文件 |

**数据库和加密密钥必须一起恢复**。这个加密密钥既用于解密本地密钥，*也*用于解密审批 CA 的签名密钥，而这两者都存放在数据库中。如果恢复的数据库搭配了另一个加密密钥，启动后所有密钥都将无法读取。

## 数据库 {#the-database}

PostgreSQL：

```bash
pg_dump --format=custom --file=a2flow-$(date +%F).dump "postgresql://user:password@host:5432/a2flow"
pg_restore --clean --if-exists --dbname="postgresql://user:password@host:5432/a2flow" a2flow-2026-01-31.dump
```

使用 Docker Compose 时，直接访问 `db` 服务：

```bash
docker compose exec -T db pg_dump -U a2flow -Fc a2flow > a2flow-$(date +%F).dump
docker compose exec -T db pg_restore -U a2flow -d a2flow --clean --if-exists < a2flow-2026-01-31.dump
```

SQLite 只有一个文件，路径由 `DB_URL` 指定。应用运行期间请使用 `sqlite3 a2flow.db ".backup out.db"`，不要直接复制文件。

恢复后的数据库无需单独执行迁移：后端启动时会应用所有待执行的 [Alembic](https://alembic.sqlalchemy.org/) 迁移，因此把旧的转储恢复到新版本后再启动，架构就会自动升级到最新。

## 代理技能存储库 {#the-agent-skill-store}

重新注册技能无法重建 `SKILLS_DIR`。拉取技能时克隆的是仓库*当前的* HEAD，因此固定在旧修订版本上的运行拿不回那个修订版本，会一直无法加载其技能。请备份这个目录。

已发布的修订版本目录此后不会再被修改，因此在应用运行期间复制的内容也是一致的：

```bash
tar -czf skills-$(date +%F).tgz -C /var/lib/a2flow/skills .
```

使用 Docker Compose 时，存储库是名为 `skills` 的命名卷：

```bash
docker run --rm -v a2flow_skills:/skills -v "$PWD:/backup" alpine \
  tar -czf /backup/skills-$(date +%F).tgz -C /skills .
```

恢复时，把归档解压到空的存储库中，然后启动后端。

## 密钥加密密钥 {#the-secret-encryption-key}

如果显式设置了 `SECRET_ENCRYPTION_KEY`，加密密钥已经保存在存放部署配置的地方，这里无需额外操作，只需确保该配置存储本身有备份。

如果没有设置，后端会在首次使用时生成一个，并写入 `SECRET_KEY_FILE` 指向的文件（默认为 `.secret_key`，与 SQLite 数据库文件相邻）。这个文件是唯一的副本。请把它备份到所在机器以外的地方，并像对待凭据一样妥善保管，因为它本身就是凭据。

使用 Docker Compose 时，该文件位于名为 `secret-key` 的命名卷中：

```bash
docker run --rm -v a2flow_secret-key:/key -v "$PWD:/backup" alpine   cp /key/.secret_key /backup/secret_key-$(date +%F)
```

不支持轮换加密密钥，因为现有的密钥都是用旧加密密钥加密的。请参阅[密钥管理](./configuration.md#secret-management)。

## 检查恢复结果 {#checking-a-restore}

1. 启动后端，确认 [`GET /api/v1/health`](./health.md) 返回 200。这说明数据库可以访问，且架构是最新的。
2. 在管理界面中打开一个 `local` 类型的[密钥](../guides/secrets.md)。能正常加载而不报错，说明加密密钥与数据库匹配。
3. 打开一个原本正在进行的[工作流执行](../guides/workflow-executions.md)。能够继续运行而不报告 `SKILL_NOT_READY`，说明技能存储库已恢复，且仍在使用的修订版本都在。
