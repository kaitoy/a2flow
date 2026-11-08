---
title: 数据库
sidebar_position: 7
---

# 数据库

所有持久化数据都保存在一个关系型数据库中，由 `backend/.env` 中的 `DB_URL` 选择：

| 后端 | `DB_URL` | 备注 |
|---|---|---|
| SQLite（默认） | `sqlite:///a2flow.db` | 零配置的本地文件 |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Docker Compose 部署使用 |

异步驱动后缀（`aiosqlite` / `asyncpg`）会自动添加。架构变更以带版本的 [Alembic](https://alembic.sqlalchemy.org/) 迁移进行跟踪，并在启动时自动应用：重新部署应用（重启容器）就会执行所有待处理的迁移，因此不需要单独的迁移步骤。

数据库同时也负责协调多副本的后端：代理运行在其 SSE 流存续期间持有一个 PostgreSQL 咨询锁，因此同一段对话绝不会同时由两个副本驱动。有关它保护的内容以及它对连接池的限制，请参阅[水平扩展](../operations/scaling.md)。

## 保存的内容 {#what-it-holds}

| 表 | 保存的内容 |
|---|---|
| `users` | 应用用户及授予他们的角色，请参阅[用户和用户组](../guides/users-and-groups.md) |
| `auth_sessions` | 服务器端的登录会话 |
| `login_failures` | 最近的[登录失败](../guides/users-and-groups.md#failed-sign-ins)，通过计数锁定账户以防反复猜测；超过一天的行会被移除 |
| `impersonation_events` | [代理登录](../concepts/impersonation.md)会话的审计跟踪 |
| `agent_skills` | [代理技能](../guides/agent-skills.md)定义及其克隆来源仓库 |
| `mcp_servers` | 已注册的 [MCP 服务器](../guides/mcp-servers.md)及其访问方式 |
| `knowledge_bases`、`knowledge_sources`、`knowledge_pages` | [知识库](../guides/knowledge-bases.md)：每个知识库上传的文档和注册的 URL，以及据此编写的页面 |
| `secrets` | 具名的[凭据集合](../guides/secrets.md)，要么在本地加密，要么在 Vault 中引用 |
| `workflows` | [工作流](../guides/workflows.md)定义及其生命周期状态 |
| `workflow_task_templates` | 工作流预先设计好的任务列表 |
| `workflow_published_versions` | 发布时冻结的设计，`已修改` 的工作流按此运行 |
| `workflow_executions` | 每次[运行](../guides/workflow-executions.md)一行，含执行时的工作流和技能元数据快照 |
| `workflow_tasks` | 运行的各个任务，从模板复制而来 |
| `workflow_task_tool_bindings` | 绑定到任务的 MCP 工具 |
| `message_meta` | 两种共享聊天中每条消息的相关信息：谁发送了消息，以及当时正在进行哪个任务 |

删除工作流时会级联删除其模板，但保留其过去的运行：运行是对所发生事情的记录，而不是产生它的设计的一部分。
