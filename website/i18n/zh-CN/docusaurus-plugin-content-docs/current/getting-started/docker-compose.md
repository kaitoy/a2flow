---
title: 使用 Docker Compose 运行
sidebar_position: 2
---

# 使用 Docker Compose 运行

您也可以用 Docker Compose（[compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)）一次性构建并启动整套服务：

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

打开 [http://localhost:3000](http://localhost:3000)。数据库数据保存在 `pgdata` 卷中，重启后依然存在。

要在其他主机端口上发布应用，请在 `.env` 中设置 `APP_PORT`；后端的 `CORS_ORIGINS` 会自动随之变化。

## 启动的容器 {#what-comes-up}

| 容器 | 作用 |
|---|---|
| **db** | PostgreSQL 17。A2Flow 记录的所有内容都保存在这里 |
| **backend** | 代理和 API |
| **worker** | 发送后端排队的[通知邮件](../guides/notifications.md#the-delivery-queue) |
| **mcp-proxy** | 运行您注册的 [MCP 服务器](../guides/mcp-servers.md)，参阅[为什么要单独运行](../architecture/mcp-gateway-and-proxy.md#the-sandbox) |
| **ingress** | 浏览器访问的入口。把界面请求发送给前端，把 API 请求直接发送给后端 |
| **frontend** | 您所操作的界面 |
| **openbao** | 仅在使用 `--profile openbao` 时启动，参阅[使用 OpenBao 试用 Vault 密钥](#openbao) |

只有 ingress（以及启用该 profile 时 OpenBao 的 UI）可以从外部访问；其余容器通过 Docker 内部网络相互通信。

首次启动比之后的启动耗时更长：需要构建镜像、创建数据库架构，而且 MCP 代理服务器要等后端发给它所需的证书之后才会开始接受请求。

## 使用 OpenBao 试用 Vault 密钥 {#openbao}

[OpenBao](https://openbao.org/) 是 Vault 的开源分支，A2Flow 连接它的方式与连接 HashiCorp Vault 完全相同。这套服务可以在 A2Flow 旁边启动一个 OpenBao，因此即使没有自己的 Vault，也能试用 [Vault 类型的密钥](../guides/secrets.md)。

```bash
docker compose --profile openbao up --build
```

OpenBao 的数据保存在与 A2Flow 相同的 PostgreSQL 中，因此重启后依然存在，并且每次启动时都会自动解封。解封所用的密钥保存在 `openbao-unseal` 卷中：请将它与 `pgdata` 一起备份，因为没有它就无法读取数据。此配置用于试用集成，不适用于生产环境。

### 1. 初始化 OpenBao（仅首次启动时） {#1-initialize-openbao-first-start-only}

```bash
docker compose exec openbao bao operator init -recovery-shares=1 -recovery-threshold=1
```

记下它输出的 **Initial Root Token**，它只显示这一次。

### 2. 为 A2Flow 创建 AppRole {#2-create-an-approle-for-a2flow}

UI 无法创建 AppRole 角色，因此这一步要在命令行中进行。将 `<root-token>` 替换为第 1 步得到的令牌：

```bash
docker compose exec -e BAO_TOKEN=<root-token> openbao sh -c '
  bao secrets enable -path=secret kv-v2
  bao auth enable approle
  printf "path \"secret/data/a2flow/*\" { capabilities = [\"read\"] }" | bao policy write a2flow -
  bao write auth/approle/role/a2flow token_policies=a2flow token_ttl=1h
  bao read -field=role_id auth/approle/role/a2flow/role-id; echo
  bao write -f -field=secret_id auth/approle/role/a2flow/secret-id; echo'
```

最后两行会输出 **role id** 和 **secret id**。该策略只允许 A2Flow 读取 `a2flow/` 下的路径。

### 3. 在 OpenBao UI 中创建密钥 {#3-create-a-secret-in-the-openbao-ui}

1. 打开 [http://localhost:8200/ui](http://localhost:8200/ui)，使用 **Token** 方式和根令牌登录。OpenBao 不会在页面重新加载后保留根令牌登录状态，所以请通过点击来跳转，不要直接输入 URL。
2. 打开 **secret/** 引擎，选择 **Create secret**。
3. 输入 `a2flow/demo` 作为路径，添加 `username` 和 `password` 两个条目，然后保存。

### 4. 连接 A2Flow {#4-connect-a2flow}

1. 以 `root` 身份登录 A2Flow。在**系统设置**中，将**全局 Vault 地址**设置为 `http://openbao:8200` 并保存。
2. 打开**租户**，然后打开 **Default**。勾选**登录全局 Vault**，将 **Vault 认证方式**选为 **AppRole**，输入第 2 步得到的 role id 和 secret id，然后保存。
3. 以 `admin` 身份登录。在**密钥**中，创建一个类型为 **HashiCorp Vault** 的密钥，将 **Vault 挂载点**设为 `secret`，将 **Vault 路径**设为 `a2flow/demo`。

可以像引用其他密钥一样引用它，例如在 [MCP 服务器](../guides/mcp-servers.md)的环境变量中写成 `${secret:<名称>/password}`。无论在哪里选择该密钥，都会列出它的键 `username` 和 `password`；这些键是当场从 OpenBao 读取的，由此可以确认连接正常。

要在 8200 以外的主机端口上发布 OpenBao 的 UI，请在 `.env` 中设置 `OPENBAO_PORT`。A2Flow 本身始终通过内部网络上的 `http://openbao:8200` 访问它。
