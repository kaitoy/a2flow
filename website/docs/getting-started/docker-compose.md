---
title: Run with Docker Compose
sidebar_position: 2
---

# Run with Docker Compose

Alternatively, the whole stack can be built and started with Docker Compose ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)):

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). Database data persists in the `pgdata` volume across restarts.

Set `APP_PORT` in `.env` to publish the app on a different host port; the app's base URL follows it automatically. To have the app address itself differently — by a host name, say — set `APP_BASE_URL` in `.env` to that address instead, such as `http://a2flow.internal:3000`. The app is still published on `APP_PORT`, so when that address carries a port, set `APP_PORT` to match.

## What comes up

| Container | What it does |
|---|---|
| **db** | PostgreSQL 17. Everything A2Flow records lives here |
| **backend** | The agent and the API |
| **worker** | Sends the [notification email](../guides/notifications.md#the-delivery-queue) the backend queues |
| **mcp-proxy** | Runs the [MCP servers](../guides/mcp-servers.md) you register — see [why it is separate](../architecture/mcp-gateway-and-proxy.md#the-sandbox) |
| **ingress** | The entry point your browser talks to. Sends the screens' requests to the frontend and API requests straight to the backend |
| **frontend** | The screens you use |
| **caddy** | Only with `compose.https.yml` — see [Serve over HTTPS](#https) |
| **openbao** | Only with `--profile openbao` — see [Try Vault secrets with OpenBao](#openbao) |
| **keycloak** | Only with `--profile keycloak` — see [Try single sign-on with Keycloak](#keycloak) |

Only the ingress — or Caddy in its place, with `compose.https.yml` — (and, with their profiles, OpenBao's UI and Keycloak) is reachable from outside; the rest talk to each other on Docker's internal network.

The first start takes longer than later ones: the images are built, the database schema is created, and the MCP proxy waits for the backend to hand it the certificate it needs before it will accept anything.

## Serve over HTTPS {#https}

Adding `compose.https.yml` puts [Caddy](https://caddyserver.com/) in front of the ingress. It takes over as the only entry point, on ports 80 and 443, obtains a certificate for the address in `APP_BASE_URL`, and redirects plain HTTP to HTTPS. An `https://` address also makes the sign-in cookies secure, and [single sign-on](../guides/single-sign-on.md) builds its **Redirect URI** from it.

```bash
echo APP_BASE_URL=https://a2flow.example.com >> .env
docker compose -f compose.yml -f compose.https.yml up --build
```

Open the address you set. It must carry no port — only 80 and 443 are published, and Caddy refuses to start on an address with one. What happens next depends on the host name:

| `APP_BASE_URL` | Certificate | Before you start |
|---|---|---|
| A public host name, such as `https://a2flow.example.com` | Obtained from Let's Encrypt and renewed automatically | Point the name's DNS at this host and make ports 80 and 443 reachable from the internet |
| Not set (`https://localhost`) | Issued by a certificate authority Caddy creates for itself | Nothing — but the browser warns about the certificate until you trust that authority (below) |

To make the browser trust `https://localhost`, copy out the authority's root certificate and add it to your operating system's or browser's trusted root certificates:

```bash
docker compose -f compose.yml -f compose.https.yml cp caddy:/data/caddy/pki/authorities/local/root.crt .
```

Certificates and the local authority live in the `caddy-data` volume. Keep it: deleting it issues new certificates, and a root certificate you already trusted stops matching.

## Try Vault secrets with OpenBao {#openbao}

[OpenBao](https://openbao.org/) is an open-source Vault fork that A2Flow connects to exactly as it does to HashiCorp Vault. The stack can start one next to A2Flow, so [Vault-type secrets](../guides/secrets.md) can be tried without a Vault of your own.

```bash
docker compose --profile openbao up --build
```

OpenBao keeps its data in the same PostgreSQL as A2Flow, so it survives restarts, and it unseals itself on every start. The key it unseals with lives in the `openbao-unseal` volume: back it up together with `pgdata`, since the data cannot be read without it. This setup is for trying the integration, not for production.

### 1. Initialize OpenBao (first start only)

```bash
docker compose exec openbao bao operator init -recovery-shares=1 -recovery-threshold=1
```

Note the **Initial Root Token** it prints — it is shown only once.

### 2. Create an AppRole for A2Flow

The UI cannot create an AppRole role, so this step runs on the command line. Replace `<root-token>` with the token from step 1:

```bash
docker compose exec -e BAO_TOKEN=<root-token> openbao sh -c '
  bao secrets enable -path=secret kv-v2
  bao auth enable approle
  printf "path \"secret/data/a2flow/*\" { capabilities = [\"read\"] }" | bao policy write a2flow -
  bao write auth/approle/role/a2flow token_policies=a2flow token_ttl=1h
  bao read -field=role_id auth/approle/role/a2flow/role-id; echo
  bao write -f -field=secret_id auth/approle/role/a2flow/secret-id; echo'
```

The last two lines print the **role id** and the **secret id**. The policy lets A2Flow read only paths under `a2flow/`.

### 3. Create a secret in the OpenBao UI

1. Open [http://localhost:8200/ui](http://localhost:8200/ui) and sign in with the **Token** method and the root token. OpenBao does not keep a root-token sign-in across a page reload, so move around by clicking rather than by typing URLs.
2. Open the **secret/** engine and choose **Create secret**.
3. Enter `a2flow/demo` as the path, add the entries `username` and `password`, and save.

### 4. Connect A2Flow

1. Sign in to A2Flow as `root`. Under **System Settings**, set **Global Vault Address** to `http://openbao:8200` and save.
2. Open **Tenants**, then **Default**. Tick **Log in to the global Vault**, choose **AppRole** as the **Vault Auth Method**, enter the role id and secret id from step 2, and save.
3. Sign in as `admin`. Under **Secrets**, create a secret of type **HashiCorp Vault** with **Vault Mount** `secret` and **Vault Path** `a2flow/demo`.

Reference it like any other secret, for example as `${secret:<name>/password}` in an [MCP server](../guides/mcp-servers.md)'s environment variable. Wherever you pick the secret, its keys `username` and `password` are listed — read from OpenBao at that moment, which shows the connection works.

Set `OPENBAO_PORT` in `.env` to publish OpenBao's UI on a host port other than 8200. A2Flow itself always reaches it as `http://openbao:8200` on the internal network.

## Try single sign-on with Keycloak {#keycloak}

[Keycloak](https://www.keycloak.org/) is an open-source identity provider. The stack can start one next to A2Flow, already set up for it, so [single sign-on](../guides/single-sign-on.md) can be tried without an IdP of your own.

```bash
docker compose --profile keycloak up --build
```

Keycloak is published at [http://keycloak.localhost:8180](http://keycloak.localhost:8180), and its admin console signs in as `admin` / `admin` (set `KEYCLOAK_ADMIN_PASSWORD` in `.env` to change the password). Chrome, Edge and Firefox find `keycloak.localhost` on their own; in another browser, add the line `127.0.0.1 keycloak.localhost` to your hosts file first. Keycloak keeps nothing across a re-created container: it starts over from the setup below, so changes made in its console are lost.

It comes up with this already in place:

| What | Value |
|---|---|
| Realm | `a2flow` |
| Issuer URL | `http://keycloak.localhost:8180/realms/a2flow` |
| Client ID | `a2flow` |
| Client secret | `a2flow-dev-secret` |
| Redirect URIs | `http://localhost:3000` (or your `APP_BASE_URL`) and `https://localhost`, each followed by A2Flow's callback path |
| Groups claim | `groups` |
| Users | `alice` in group `a2flow-admins`, `bob` in group `a2flow-users`. Both have the password `password` |

### 1. Connect A2Flow

1. Sign in to A2Flow as `admin` and open **Tenant Settings** in the admin sidebar.
2. In the **Single sign-on** section, fill in **Issuer URL**, **Client ID** and **Client secret** from the table above, tick **Enable single sign-on** and save.
3. Open **User Groups**, open a group — or create one — that holds the roles you want, enter `a2flow-admins` in **IdP group** and save.

### 2. Sign in

1. Sign out. On the sign-in screen, enter `default` in **Tenant** and press **Sign in with SSO**.
2. On Keycloak's sign-in page, sign in as `alice` / `password`. You come back signed in to A2Flow as Alice, a member of the group from step 1.
3. Try `bob` too: his only group, `a2flow-users`, is mapped to no user group, so the sign-in is refused — until you map it to one.

Keycloak also speaks SAML, but A2Flow signs in through OpenID Connect only.
