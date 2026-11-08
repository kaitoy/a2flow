---
title: 配置参考
sidebar_position: 2
---

# 配置参考

以下所有设置都是环境变量。后端从 `backend/.env` 读取（带注释的模板见 [backend/.env.example](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example)）；两个前端变量从前端自身的进程环境读取。模型和 API 密钥的设置单独成页，请参阅 [LLM 配置](../getting-started/llm-configuration.md)。

## 服务器设置 {#server-settings}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `HOST` | `0.0.0.0` | 后端绑定的地址 |
| `PORT` | `8000` | 后端绑定的端口 |
| `RELOAD` | `false` | 用于本地开发的 uvicorn 自动重载。仅在以 `python -m backend.main` 启动后端时读取；无论取值如何，Docker 镜像自身的启动命令都不受影响 |
| `TIMEZONE` | `UTC` | 部署所在本地时区的 IANA 名称。它决定[运维指标](./metrics.md)中一个自然日从何时开始（影响“今天”的计数以及前置时间趋势的每日分桶）；当任务的时间要求未注明时区时，工作流代理也按此时区解读。无法识别的名称会回退到 `UTC`，而不会导致启动失败，因此拼写错误只会使本地时间出现偏差，不会让应用停止运行 |

## 前端设置 {#frontend-settings}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | 没有反向代理先把 `/api/*` 路由到后端时（不使用容器运行），前端转发 `/api/*` 的目标地址；API 文档页面也通过它检查已登录的会话。仅在进程启动时读取一次。在 Docker Compose 部署中，这是后端在内部网络上的地址，而不是公开地址 |
| `APP_PORT` | `3000` | 仅限 Docker Compose：应用发布到主机上的端口，即同时提供界面和 API 的 `ingress` 服务的端口。后端的 `CORS_ORIGINS` 会自动跟随此值 |
| `OPENBAO_PORT` | `8200` | 仅限 Docker Compose 且使用 `--profile openbao` 时：OpenBao 界面发布到主机上的端口，请参阅[使用 OpenBao 试用 Vault 密钥](../getting-started/docker-compose.md#openbao)。无论此值如何，A2Flow 都通过内部网络访问它 |

## 应用数据库 {#application-database}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `DB_URL` | `sqlite:///a2flow.db` | 数据库 URL。支持 SQLite（相对于工作目录）和 PostgreSQL |
| `DB_POOL_SIZE` | `5` | 仅限 PostgreSQL。后端进程的两个连接池各自保持打开的连接数。最小为 `1`。各副本合计的连接数请参阅[连接池](./scaling.md#connection-pooling) |
| `DB_MAX_OVERFLOW` | `10` | 仅限 PostgreSQL。负载较高时，每个连接池可在 `DB_POOL_SIZE` 之外额外打开的连接数，负载下降后会再次关闭。最小为 `0` |

异步驱动后缀（`sqlite+aiosqlite` / `postgresql+asyncpg`）会自动添加，因此使用普通协议名即可：

```env
DB_URL=postgresql://user:password@localhost:5432/a2flow
```

架构变更以带版本的 [Alembic](https://alembic.sqlalchemy.org/) 迁移进行管理，并在启动时自动应用，因此重新部署应用就能让架构更新到最新。运行多个后端副本需要 PostgreSQL，请参阅[水平扩展](./scaling.md)。各张表保存的内容请参阅[数据库](../architecture/database.md)。

## 预置用户 {#seeded-users}

启动时，后端会预置一个隐藏的**系统用户**和两个真实账户，每个账户仅在首次发现目标记录不存在的那次启动时创建：

- 初始的 **`root`** 用户，拥有**超级管理员**角色（请参阅[授权](../concepts/authorization.md)），作用范围为整个平台（`tenantId: null`）。只要已存在*任何*真实（非系统）用户就会跳过，因此只会在最初的那次启动时执行。
- **Default** 租户（`slug: default`），以及其中拥有**管理员**角色的初始 **`admin`** 用户。租户（按 `slug`）和用户（按该租户内的 `username`）分别独立检查，因此可以单独重新创建其中一个，而不会造成另一个重复。

隐藏的**系统用户**拥有引导记录（它无法登录，也不会出现在用户列表中）。

| 变量 | 默认值 | 作用 |
|---|---|---|
| `ROOT_PASSWORD` | 自动生成 | 预置的 `root` 用户的密码 |
| `ADMIN_PASSWORD` | 自动生成 | Default 租户中预置的 `admin` 用户的密码 |

如果其中任何一个未设置（或为空），系统会改为生成随机密码，并在创建该用户时以 `WARNING` 级别记录到日志中，且**仅此一次**。这行日志一旦滚动过去，密码就无法找回。如果不只是在本地试用，请在首次运行前显式设置这两个变量，或者立即从启动日志中记下生成的密码，并在之后修改。用户名固定为 `root` 和 `admin`。

## 会话有效期 {#session-lifetime}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `SESSION_IDLE_TIMEOUT_SECONDS` | `28800`（8 小时） | 滑动式空闲超时。已认证的请求会刷新会话的最后活动时间，但最多每 5 分钟刷新一次（如果此值的一半更短，则按其一半），因此会话可能最多提前这么长时间结束；空闲超过此时长的会话会被拒绝并删除 |
| `SESSION_COOKIE_SECURE` | `false` | 将会话和 CSRF Cookie 标记为 `Secure`（仅限 HTTPS）。凡是位于 HTTPS 之后的部署，都请将其设为 `true` |

这些 Cookie 本身是会话 Cookie（没有 `Max-Age`/`Expires`），因此关闭浏览器时也会被清除。浏览器通过与前端相同的源访问后端（`/api/*` 按路径路由到后端，由反向代理或前端自身完成），因此这些 Cookie 属于第一方 Cookie，`SameSite=Lax` 可以正常生效。

## CORS {#cors}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | 允许调用后端 API 的源，以逗号分隔 |

添加提供前端的每个源：

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` 会在启动时被拒绝：`allow_credentials=True` 始终处于启用状态，而根据 CORS 规范，它不能与通配符源搭配使用。

## 代理技能存储库 {#agent-skill-store}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `SKILLS_DIR` | `backend/.skills` | 存储库的根目录，代理技能仓库会浅克隆到这里。在 `docker compose` 下为 `/var/lib/a2flow/skills`，由名为 `skills` 的命名卷提供 |
| `SKILLS_PRUNE_GRACE_SECONDS` | `3600` | 无论是否被引用，修订版本目录都会保留的时长。拉取时会清理没有任何执行固定使用的修订版本，而这段宽限期覆盖了运行读取当前修订版本到插入引用该版本的行之间的间隙 |
| `SKILLS_CLONE_TIMEOUT_SECONDS` | `120` | 限制克隆过程中单个 HTTP 请求可用的时长。没有这个限制时，无响应的远程仓库会让克隆无限期停滞，技能一直处于 `克隆中` 状态 |

存储库为每个修订版本保存一个不可变的目录，修订版本一经发布就不会再被修改，因此拉取绝不会干扰正在加载现有版本的代理：

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

这是**持久状态，不是缓存**：工作流执行会固定使用其启动时的修订版本，因此清空该目录后，现有执行将无法加载其技能（HTTP 409 `SKILL_NOT_READY`），直到管理员重新拉取该技能；而且拉取获取的是仓库当前的 HEAD，并不是固定的修订版本。请备份该目录（[备份与恢复](./backup.md)），并让每个后端副本都使用同一个目录（[水平扩展](./scaling.md)）。

## 知识库 {#knowledge-bases}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `KNOWLEDGE_SOURCE_MAX_BYTES` | `20971520`（20 MiB） | 可上传到[知识库](../guides/knowledge-bases.md)的文档以及为其抓取的网页的最大大小。上传内容一旦超过此值，就会被立即拒绝 |
| `KNOWLEDGE_INGEST_CHUNK_CHARS` | `40000` | LLM 每次读取的来源字符数。更长的来源会分成几部分依次读取。如果模型的上下文窗口较小，请调低此值 |
| `KNOWLEDGE_FETCH_TIMEOUT_SECONDS` | `30` | 抓取网页来源时每个请求可用的时长 |

来源和页面与会话文件一样存储在数据库中，因此不需要专门的卷。读取来源时调用的是为代理配置的 LLM（[LLM 配置](../getting-started/llm-configuration.md)），对于大型文档会调用多次。

## 会话文件 {#session-files}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `SESSION_FILE_MAX_BYTES` | `20971520`（20 MiB） | 可附加到[工作流会话](../guides/workflow-executions.md#files-in-the-session)的单个文件的最大大小。上传内容一旦超过此值，就会被立即拒绝，因此过大的内容绝不会被完整保留在内存中 |
| `SESSION_FILES_MAX_TOTAL_BYTES` | `209715200`（200 MiB） | 一个会话中所有文件的总大小。文件只有在其运行被删除时才会移除，因此长时间运行的会话就靠这个值来限制 |

会话文件存储在数据库中，而不是磁盘上，因此不需要专门的目录，不需要在副本之间共享卷，除数据库本身的备份外也不需要额外的备份步骤（[备份与恢复](./backup.md)）。提高这些限制，会增加一次运行可占用的数据库空间，也会增加单次上传或下载占用的内存，因为这些字节会被完整读取。

## 密钥管理 {#secret-management}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `SECRET_ENCRYPTION_KEY` | — | Fernet 加密密钥，用于在存储前加密 `local` 类型的[密钥](../guides/secrets.md) |
| `SECRET_KEY_FILE` | `.secret_key` | 磁盘上加密密钥文件的路径，与 SQLite 数据库文件相邻。在 `docker compose` 下为 `/var/lib/a2flow/secret-key/.secret_key`，由后端和邮件工作进程共享的命名卷 `secret-key` 提供 |

加密密钥在首次使用时按以下顺序确定：

1. `SECRET_ENCRYPTION_KEY`，必须是有效的 Fernet 密钥。
2. `SECRET_KEY_FILE` 指向的密钥文件。
3. 如果两者都不可用，则生成一个密钥并保存到该文件，同时记录一条 WARNING 日志。

**请备份加密密钥**。一旦丢失，所有已存储的本地密钥都将无法解密，而且[审批 CA](../architecture/approvals.md) 的签名密钥也由同一个加密密钥保护。

HashiCorp Vault 没有对应的环境变量：租户自己的 Vault 由其管理员在[租户设置](../guides/users-and-groups.md#tenant-vault)中配置，全局 Vault 的地址由超级管理员在[系统设置](../guides/system-settings.md#global-vault)中配置，每个租户[访问全局 Vault 的凭据](../guides/users-and-groups.md#global-vault-credential)则在该租户的页面上配置。租户自己的 Vault 地址与其他用户提供的 URL 一样要经过 SSRF 检查，因此必须是公网地址。全局 Vault 地址不受此限制，因为只有超级管理员才能设置它，而且 Vault 通常位于私有地址上。

## MCP 工具与审批 {#mcp-tools-and-approvals}

每次调用 MCP 工具都必须出示为发起调用的任务签发的短期 X.509 证书。证书在任务的[审批](../guides/approvals.md#human-approval)获得批准时授予，或者在无需任何人审批的任务启动时授予。签名根证书在首次使用时生成，并使用与本地密钥相同的加密密钥加密存储，因此无需在此配置任何内容，该功能即可工作。

| 变量 | 默认值 | 限制的内容 |
|---|---|---|
| `MCP_TOOL_CERT_TTL_SECONDS` | `3600` | 任务证书的有效时长，也就是任务可以调用其工具的时间窗口 |
| `MCP_TOOL_CERT_SIGNATURE_WINDOW_SECONDS` | `60` | 每次经代理服务器转发的调用都附带持有证明签名，此值是该签名允许的时钟偏差 |
| `MCP_CA_COMMON_NAME` / `MCP_CA_VALIDITY_DAYS` | `A2Flow MCP Approval CA` / `3650` | 所生成根证书的主题和有效期。仅在首次生成根证书时读取；之后更改不会影响现有的根证书 |
| `MCP_REGISTRY_URL` | `https://registry.modelcontextprotocol.io` | [浏览注册表](../guides/mcp-servers.md#registering-from-the-mcp-registry)对话框所搜索的注册表的基础 URL |
| `MCP_ELICITATION_TIMEOUT_SECONDS` | `900` | 工具调用等待运行发起人回复 MCP 服务器[确认请求](../guides/workflow-executions.md#mcp-server-confirmations)的时长，超时后问题即过期。发起人刚刚恢复了任务，因此这个时长只对被搁置的问题起作用 |
| `AGENT_TURN_TIMEOUT_SECONDS` | `3600` | 运行中代理的一个轮次可持续的最长时间，包括等待时间。请将其设置为远高于 `MCP_ELICITATION_TIMEOUT_SECONDS`，因为工具调用在等人回复时，该轮次仍在运行 |

## MCP 代理服务器 {#mcp-sandbox}

已注册的 MCP 服务器不是 A2Flow 自己的代码，因此它运行在与代理及其密钥[相隔离的地方](../architecture/mcp-gateway-and-proxy.md#the-sandbox)。Docker Compose 部署已经完成了所有这些设置；自行组装容器的部署则在此处设置。

如果不设置（普通的本地运行就是这样），代理会在自己的进程中直接访问 MCP 服务器。这在开发时很方便，但在任何人都能注册服务器的环境中并不可取。

| 变量 | 默认值 | 作用 |
|---|---|---|
| `MCP_PROXY_URL` | 未设置 | MCP 代理服务器的地址。设置后，MCP 服务器才会移出代理的进程 |
| `MCP_PROXY_SERVER_NAME` / `MCP_PROXY_PORT` | `mcp-proxy` / `8443` | 访问 MCP 代理服务器所用的名称及其监听的端口。名称是其证书的一部分，因此两端必须一致 |
| `MCP_PROXY_TLS_DIR` | 应用旁边的一个目录 | 代理将 MCP 代理服务器标识自身所需的材料发布到这里。MCP 代理服务器以只读方式读取同一目录 |
| `MCP_BACKEND_TLS_DIR` | 应用旁边的一个目录 | 代理存放*自己的*密钥的位置。特意与上面的目录分开，因为在 MCP 代理服务器中运行的任何程序都不应能够读取它 |
| `MCP_TRANSPORT_CERT_VALIDITY_DAYS` | `365` | 这些材料的有效期。剩余不足 30 天时会自动重新签发，无需人工关注 |
| `MCP_SANDBOX_DIR` | 未设置 | [沙箱化服务器启动](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox)所用的各租户主目录的位置，租户的服务器下载的软件包保存在这里，每个租户一个目录。设置后，每个本地启动的服务器都在自己的沙箱中运行；未设置时 MCP 代理服务器会拒绝启动。在普通的本地运行中不设置，此时服务器不使用沙箱启动 |

## 通知邮件 {#notification-email}

这些值与管理界面中[系统设置](../guides/system-settings.md)所编辑的值相同。它们也可以通过环境变量设置，这样部署就能自带邮件配置，而不必留作手动步骤。

| 变量 | 默认值 | 作用 |
|---|---|---|
| `APP_BASE_URL` | — | 用户在浏览器中访问此部署所用的基础 URL，例如 `https://a2flow.example.com`。用于生成外发通知邮件中的深层链接；未设置时，邮件发出时不带返回应用的链接 |
| `SMTP_ENABLED` | `false` | 邮件投递的总开关。必须显式设为 `true`；绝不会因为设置了其他变量而被推断为启用 |
| `SMTP_HOST` / `SMTP_PORT` | — / `587` | 接收邮件的中继。这里可以使用内部主机名，因为该值是交给 SMTP 客户端的，不会被用于发起抓取 |
| `SMTP_SECURITY` | `starttls` | `none`、`starttls` 或 `ssl` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | — | SMTP AUTH 凭据。密码仅以密文形式存储，绝不会写入日志，也绝不会由任何 API 响应返回 |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | — | 发件人地址（启用投递后必填），以及旁边显示的可选名称 |

与本页其他设置不同，这些值不是每次使用时重新读取，而是写入唯一的那条设置记录。因此它们有自己的规则：

- **每次启动都会重新应用**，而不只是首次启动，因此轮换中继密码只需重新部署。
- **只写入实际设置的变量**，因此未设置的变量会保留已存储的值，包括管理员在界面中手动配置的内容。
- **格式错误的值会记录一条警告，并被整体跳过**。端口错误、地址无效，或 `SMTP_ENABLED=true` 却没有主机，都不会改动已存储的配置；应用仍会启动。

由于启用标志是独立的，可以在一次部署中先准备好中继的主机和凭据，在之后的部署中再开启投递。

## 外发邮件队列 {#outgoing-email-queue}

这些是向中继发送邮件的队列的调节项，其行为请参阅[投递队列](../guides/notifications.md#the-delivery-queue)。常规部署无需设置其中任何一项。

| 变量 | 默认值 | 作用 |
|---|---|---|
| `EMAIL_WORKER_IN_PROCESS` | `true` | API 进程是否同时运行排空队列的工作进程，这样单独运行 `uvicorn main:app` 也能投递邮件。运行专用工作进程时请将其设为 false，请参阅[进程布局](./deployment.md#process-layout)。两者都保持开启是安全的，只是没有意义：咨询锁会在整个部署中选出唯一的发送者 |
| `EMAIL_SEND_RATE_PER_SECOND` | `5.0` | 每秒交给中继的邮件数；工作进程在每次发送前暂停 `1 / rate`。如果中继的限制更严格，请调低此值 |
| `EMAIL_QUEUE_BATCH_SIZE` / `EMAIL_QUEUE_POLL_INTERVAL_SECONDS` | `20` / `5.0` | 一轮排空所领取的邮件数，以及队列为空时工作进程休眠的时长。对于工作进程休眠期间产生的通知，轮询间隔就是投递延迟的下限 |
| `EMAIL_MAX_ATTEMPTS` | `9` | 邮件变为死信之前的投递尝试次数。退避时间依次为 15 秒、30 秒、1 分钟、2 分钟，以此类推，上限为一小时，因此默认值大约能撑过一小时的中继停机。中继报告为永久性失败的邮件，无论次数如何，都会在第一次尝试时放弃 |
| `EMAIL_SENT_RETENTION_DAYS` | `30` | 已投递的邮件在工作进程清除之前的保留时长。它们是已发送内容的记录，而不是队列状态。死信永远不会被清除 |

## 代理 {#agent}

| 变量 | 默认值 | 作用 |
|---|---|---|
| `EXECUTION_MAX_PARALLEL_SESSIONS` | `4` | 一次工作流运行同时使用的会话数上限，包括其主会话以及任务图分支时分叉出的分支会话。达到上限后，就绪的任务会等待其会话，而不再分叉新的会话。设为 `1` 可关闭分叉。最小为 `1` |
| `ROLE_DESCRIPTION` | 通用的助手描述 | 构建代理系统提示词时所围绕的角色文本，与工作流规则和界面架构一起使用 |
| `SESSION_RUNNER_CONCURRENCY` | `4` | 一个副本同时代表运行本身执行的轮次数，包括启动以及审批作出决定后的恢复。每个轮次都是与模型的实时对话，因此这个值限制了一个副本为无人查看的运行发起的模型调用数。最小为 `1` |
