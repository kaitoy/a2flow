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

在 `.env` 中设置 `APP_PORT`，即可把应用发布到主机上的其他端口；应用的基础 URL 会自动跟随此值。若要让应用以其他地址（例如某个主机名）打开，请改为在 `.env` 中把 `APP_BASE_URL` 设为该地址，例如 `http://a2flow.internal:3000`。应用仍发布在 `APP_PORT` 上，因此地址中带有端口时，请把 `APP_PORT` 设为相同的值。

## 启动的容器 {#what-comes-up}

| 容器 | 作用 |
|---|---|
| **db** | PostgreSQL 17。A2Flow 记录的所有内容都保存在这里 |
| **backend** | 代理和 API |
| **worker** | 发送后端排队的[通知邮件](../guides/notifications.md#the-delivery-queue) |
| **mcp-proxy** | 运行您注册的 [MCP 服务器](../guides/mcp-servers.md)，参阅[为什么要单独运行](../architecture/mcp-gateway-and-proxy.md#the-sandbox) |
| **ingress** | 浏览器访问的入口。把界面请求发送给前端，把 API 请求直接发送给后端 |
| **frontend** | 您所操作的界面 |
| **caddy** | 仅在使用 `compose.https.yml` 时启动，参阅[通过 HTTPS 提供服务](#https) |
| **openbao** | 仅在使用 `--profile openbao` 时启动，参阅[使用 OpenBao 试用 Vault 密钥](#openbao) |
| **keycloak** | 仅在使用 `--profile keycloak` 时启动，参阅[使用 Keycloak 试用单点登录](#keycloak) |

只有 ingress（使用 `compose.https.yml` 时改为 Caddy；启用相应 profile 时还有 OpenBao 的 UI 和 Keycloak）可以从外部访问；其余容器通过 Docker 内部网络相互通信。

首次启动比之后的启动耗时更长：需要构建镜像、创建数据库架构，而且 MCP 代理服务器要等后端发给它所需的证书之后才会开始接受请求。

## 通过 HTTPS 提供服务 {#https}

加上 `compose.https.yml` 后，[Caddy](https://caddyserver.com/) 会放在 ingress 前面。它成为唯一的入口，监听 80 和 443 端口，为 `APP_BASE_URL` 中的地址获取证书，并把明文 HTTP 重定向到 HTTPS。地址为 `https://` 时，登录用的 Cookie 也会带上 Secure，[单点登录](../guides/single-sign-on.md)的**重定向 URI** 也由它生成。

```bash
echo APP_BASE_URL=https://a2flow.example.com >> .env
docker compose -f compose.yml -f compose.https.yml up --build
```

打开你设置的地址。地址中不能带端口：只发布了 80 和 443，地址带端口时 Caddy 不会启动。之后的行为取决于主机名：

| `APP_BASE_URL` | 证书 | 开始之前 |
|---|---|---|
| 公网主机名，例如 `https://a2flow.example.com` | 从 Let's Encrypt 获取并自动续期 | 将该名称的 DNS 指向本主机，并确保 80 和 443 端口可从互联网访问 |
| 未设置（`https://localhost`） | 由 Caddy 自行创建的证书颁发机构签发 | 无需准备，但在信任该颁发机构之前，浏览器会显示证书警告（见下文） |

要让浏览器信任 `https://localhost`，请取出该颁发机构的根证书，并添加到操作系统或浏览器的受信任根证书中：

```bash
docker compose -f compose.yml -f compose.https.yml cp caddy:/data/caddy/pki/authorities/local/root.crt .
```

证书和本地颁发机构保存在 `caddy-data` 卷中。请保留它：删除后会重新签发证书，已经信任的根证书也将不再匹配。

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

## 使用 Keycloak 试用单点登录 {#keycloak}

[Keycloak](https://www.keycloak.org/) 是开源的身份提供者。这套服务可以在 A2Flow 旁边启动一个已为 A2Flow 配置好的 Keycloak，因此即使没有自己的 IdP，也能试用[单点登录](../guides/single-sign-on.md)。

```bash
docker compose --profile keycloak up --build
```

Keycloak 发布在 [http://keycloak.localhost:8180](http://keycloak.localhost:8180)，其管理控制台使用 `admin` / `admin` 登录（在 `.env` 中设置 `KEYCLOAK_ADMIN_PASSWORD` 可更改密码）。Chrome、Edge 和 Firefox 能自行找到 `keycloak.localhost`；使用其他浏览器时，请先在 hosts 文件中添加一行 `127.0.0.1 keycloak.localhost`。重新创建容器后 Keycloak 不会保留任何内容，而是从下面的设置重新开始，因此在其控制台中所做的更改会丢失。

启动时以下内容已经就绪：

| 项目 | 值 |
|---|---|
| Realm | `a2flow` |
| 颁发者 URL | `http://keycloak.localhost:8180/realms/a2flow` |
| 客户端 ID | `a2flow` |
| 客户端密钥 | `a2flow-dev-secret` |
| 重定向 URI | `http://localhost:3000`（或你的 `APP_BASE_URL`）和 `https://localhost`，后面各自接 A2Flow 的回调路径 |
| 组声明 | `groups` |
| 用户 | `alice` 属于组 `a2flow-admins`，`bob` 属于组 `a2flow-users`。两人的密码都是 `password` |

### 1. 连接 A2Flow {#1-connect-a2flow}

1. 以 `admin` 身份登录 A2Flow，打开管理侧边栏的**租户设置**。
2. 在**单点登录**部分，用上表的值填写**颁发者 URL**、**客户端 ID** 和**客户端密钥**，勾选**启用单点登录**并保存。
3. 打开**用户组**，打开（或新建）一个带有所需角色的组，在 **IdP 组**中输入 `a2flow-admins` 并保存。

### 2. 登录 {#2-sign-in}

1. 退出登录。在登录界面的**租户**中输入 `default`，点击**使用 SSO 登录**。
2. 在 Keycloak 的登录页面以 `alice` / `password` 登录。你会以 Alice 的身份回到 A2Flow 并处于已登录状态，并且是第 1 步中那个组的成员。
3. 也试试 `bob`：他唯一的组 `a2flow-users` 没有映射到任何用户组，因此登录会被拒绝，直到你把它映射到某个用户组为止。

Keycloak 也支持 SAML，但 A2Flow 只通过 OpenID Connect 登录。
