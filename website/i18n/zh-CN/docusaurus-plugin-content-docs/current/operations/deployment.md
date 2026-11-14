---
title: 部署
sidebar_position: 1
---

# 部署

一个部署由前端、后端和一个关系型数据库组成；[使用 Docker Compose 运行](../getting-started/docker-compose.md)是同时启动这三者的最快途径。下文介绍的是，当这套系统位于代理服务器之后并保存了值得保留的数据时，有哪些地方需要改变。

![架构图：浏览器访问反向代理，反向代理将 API 请求（/api/*）直接路由到后端 API，将页面请求路由到前端；后端 API 同时运行邮件工作进程，并访问持久状态（数据库、技能存储库、加密密钥）、外部服务（LLM 提供商、MCP 服务器）和 SMTP 中继。](./img/deployment-topology.svg#gh-light-mode-only)
![架构图：浏览器访问反向代理，反向代理将 API 请求（/api/*）直接路由到后端 API，将页面请求路由到前端；后端 API 同时运行邮件工作进程，并访问持久状态（数据库、技能存储库、加密密钥）、外部服务（LLM 提供商、MCP 服务器）和 SMTP 中继。](./img/deployment-topology-dark.svg#gh-dark-mode-only)

浏览器只与一个源通信，由反向代理按路径进行路由：`/api/*` 和 `/openapi.json` 路由到后端，其余全部路由到前端。两者位于同一域名下，因此认证 Cookie 仍是第一方 Cookie，而且每个打开的聊天的长连接流都会直接到达后端，不经过前端。`compose.yml` 中的 `ingress` 服务（Envoy）就是这种路由方式的可用示例。

如果没有这条路由，则由前端自行把 `/api/*` 转发到后端，不使用容器运行时就是这样。行为相同，但每个打开的聊天都还会占用前端的一个连接，因此前端也必须随并发聊天数量进行扩展。这里提到的每个变量都在[配置参考](./configuration.md)中有说明。

## 反向代理和负载均衡器 {#reverse-proxy-and-load-balancer}

**不需要粘性会话（会话亲和性）**。请参阅[水平扩展](./scaling.md)：让同一个对话在同一时间只由一个驱动方处理的，是 PostgreSQL 咨询锁，而不是路由亲和性，而且只在单个 SSE 流持续期间生效。

SSE 代理路由（`POST /api/v1/workflow-executions/{id}/agent` 和 `POST /api/v1/workflows/{id}/agent`）要求将其路由到后端的反向代理具备以下设置：

| 设置 | 要求的值 | 原因 |
|---|---|---|
| 响应缓冲 | 对这两个路径关闭 | 应用会发送 `X-Accel-Buffering: no`，即使全局开启了缓冲，nginx 也会按响应遵循此设置。其他代理服务器都需要在自身配置中禁用 |
| 压缩 | 绝不应用于 `text/event-stream` | 应用从不压缩响应，因此客户端看到的任何压缩都来自这一层 |
| 读取 / 空闲超时 | 远高于预期最长的代理运行时间 | 代理运行没有服务器端的时间限制，因此代理服务器的读取超时是唯一能够结束流的因素，而过低的超时会悄无声息地截断合法的长响应。请根据最长的运行时间来设定，而不是根据一般的请求 |

滚动部署会在容器收到 SIGTERM 30 秒后，强制结束仍处于打开状态的所有 SSE 流（`--timeout-graceful-shutdown 30`，在后端 `Dockerfile` 的 `CMD` 中设置）。这是安全的：咨询锁会随连接一起释放，客户端会用新的请求恢复，与流被放弃时的行为完全一致。

## 位于 HTTPS 之后 {#behind-https}

有三项设置的默认值只适合本地 HTTP 开发。在部署面向真实用户之前，请全部修改：

| 变量 | 设置为 | 保持默认值的后果 |
|---|---|---|
| `SESSION_COOKIE_SECURE` | `true` | 会话和 CSRF Cookie 发出时不带 `Secure`，因此浏览器也会通过明文 HTTP 发送它们 |
| `CORS_ORIGINS` | 面向浏览器的源，例如 `https://a2flow.example.com` | 只有 `http://localhost:3000` 可以调用 API |
| `APP_BASE_URL` | 同一个源 | 通知邮件发出时不带返回应用的深层链接，请参阅[通知邮件](./configuration.md#notification-email) |

Docker Compose 栈中有一个可用的示例：[通过 HTTPS 提供服务](../getting-started/docker-compose.md#https)在 `ingress` 服务前放置一个终止 TLS 的代理，并设置全部三项。

## 进程布局 {#process-layout}

除 API 之外，部署还要运行 [MCP 代理服务器](../architecture/mcp-gateway-and-proxy.md#the-sandbox)：这个进程负责实际启动或连接租户注册的 MCP 服务器。将它分离出来正是目的所在：第三方代码在这里运行，因此它没有数据库访问权限，也不持有密钥加密密钥和 LLM API 密钥。`compose.yml` 将它作为 `mcp-proxy` 容器运行，所在网络只与 API 共享，因此根本无法访问数据库；自行组装容器的部署同样应让 MCP 代理服务器远离数据库所在的网络，并在 [MCP 代理服务器](./configuration.md#mcp-sandbox)下进行配置。

有几点需要做好：

- **API 必须先启动**。两端用于互相识别的材料由 API 签发，因此在这些材料写入之前，MCP 代理服务器不会接受任何内容。请像 `compose.yml` 那样，等 API 的健康检查通过后再启动 MCP 代理服务器。
- **两者需要一个共享目录**。`MCP_PROXY_TLS_DIR` 在两端必须是同一存储：API 可写，MCP 代理服务器只读。这里不保存任何持久内容：只要内容缺失或临近过期，就会重新写入。
- **MCP 代理服务器必须能够构建沙箱**。它在[专属的沙箱](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox)中启动每个服务器，并在启动时检查自己能否做到；如果不能，它会报错并停止，而不是在没有沙箱的情况下运行服务器。在容器内，这需要三个安全选项，`compose.yml` 只为 `mcp-proxy` 服务提供这些选项：`seccomp=unconfined`、`apparmor=unconfined` 和 `systempaths=unconfined`。在 Ubuntu 24.04 或更高版本的主机上，还必须允许非特权用户命名空间：`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`。

也可以不使用 MCP 代理服务器：不设置 `MCP_PROXY_URL`，API 就会自行访问 MCP 服务器，本地开发运行就是这样。这意味着已注册的服务器与部署的凭据运行在一起，因此在任何人都能注册服务器的环境中不应这样选择。

后端还提供两个入口点，它们使用同一个数据库。运行哪一个，决定了通知邮件从何处投递：

| 布局 | 方式 | 适用场景 |
|---|---|---|
| 仅 API | 默认方式：`EMAIL_WORKER_IN_PROCESS` 为 `true`，因此 `uvicorn main:app` 也会排空邮件队列 | 单进程部署，或规模足够小、可以接受中继停滞影响请求路径的部署 |
| API + 工作进程 | 在 API 旁边运行 `python -m worker`，并在 API 上设置 `EMAIL_WORKER_IN_PROCESS=false` | 中继挂起绝不能影响任何处理请求的组件的场景。`compose.yml` 采用的就是这种方式 |

关于工作进程，有两点需要注意：

- **它不执行迁移，也不预置数据**。这两项都由 API 的启动过程负责，因此工作进程必须在 API 启动之后再启动，`compose.yml` 会等 API 的健康检查通过后再启动它。
- **增加副本带来的是故障转移，而不是吞吐量**。它们争用 `email-queue` 咨询锁，除一个之外其余都按设计处于空闲状态，正因如此发送速率才能保持精确。

## 健康检查 {#health-checks}

请将编排器或负载均衡器指向 `GET /api/v1/health`。请参阅[健康检查](./health.md)。

## 必须持久化的状态 {#state-that-has-to-persist}

有三项内容的生命周期长于容器，必须放在持久存储上，部署才能完整地恢复运行：

| 内容 | 位置 | 丢失的后果 |
|---|---|---|
| **数据库** | `DB_URL` 指定的数据库 | 丢失一切，因为所有记录都在其中。请参阅[数据库](../architecture/database.md) |
| **代理技能存储库** | `SKILLS_DIR` | 执行无法加载其固定使用的技能修订版本（HTTP 409 `SKILL_NOT_READY`）。这是持久状态，不是缓存，请参阅[代理技能存储库](./configuration.md#agent-skill-store) |
| **密钥加密密钥** | `SECRET_ENCRYPTION_KEY`，或 `SECRET_KEY_FILE` 指向的文件 | 所有已存储的本地密钥都将无法解密，证书颁发机构也无法再签发或验证每次 MCP 工具调用所需的证书。请参阅[密钥管理](./configuration.md#secret-management) |

每一项的备份和恢复方法，请参阅[备份与恢复](./backup.md)。
