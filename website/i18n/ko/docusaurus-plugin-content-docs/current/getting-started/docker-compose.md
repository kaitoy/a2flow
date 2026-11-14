---
title: Docker Compose로 실행
sidebar_position: 2
---

# Docker Compose로 실행

또는 Docker Compose([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml))로 전체 스택을 한 번에 빌드하고 시작할 수도 있습니다.

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

[http://localhost:3000](http://localhost:3000)을 엽니다. 데이터베이스의 데이터는 `pgdata` 볼륨에 저장되므로 다시 시작해도 유지됩니다.

`.env`에 `APP_PORT`를 설정하면 앱을 다른 호스트 포트로 공개합니다. 앱의 기본 URL도 자동으로 이를 따릅니다. 호스트 이름 등 다른 주소로 앱을 열게 하려면, 대신 `.env`의 `APP_BASE_URL`에 그 주소(예: `http://a2flow.internal:3000`)를 설정합니다. 앱은 계속 `APP_PORT`로 공개되므로, 주소에 포트를 쓸 때는 `APP_PORT`도 같은 값으로 맞추세요.

## 시작되는 컨테이너 {#what-comes-up}

| 컨테이너 | 역할 |
|---|---|
| **db** | PostgreSQL 17. A2Flow가 기록하는 모든 내용이 여기에 저장됩니다 |
| **backend** | 에이전트와 API |
| **worker** | 백엔드가 대기열에 넣은 [알림 이메일](../guides/notifications.md#the-delivery-queue)을 보냅니다 |
| **mcp-proxy** | 등록한 [MCP 서버](../guides/mcp-servers.md)를 실행합니다. [분리된 이유](../architecture/mcp-gateway-and-proxy.md#the-sandbox)를 참조하세요 |
| **ingress** | 브라우저가 통신하는 진입점입니다. 화면 요청은 프런트엔드로, API 요청은 백엔드로 바로 보냅니다 |
| **frontend** | 사용자가 보는 화면 |
| **caddy** | `compose.https.yml`을 사용할 때만 시작됩니다. [HTTPS로 제공하기](#https)를 참조하세요 |
| **openbao** | `--profile openbao`를 지정한 경우에만 시작됩니다. [OpenBao로 Vault 시크릿 사용해 보기](#openbao)를 참조하세요 |
| **keycloak** | `--profile keycloak`를 지정한 경우에만 시작됩니다. [Keycloak으로 싱글 사인온 사용해 보기](#keycloak)를 참조하세요 |

외부에서 접근할 수 있는 것은 ingress(`compose.https.yml`을 사용하면 대신 Caddy, 프로필을 지정한 경우 OpenBao UI와 Keycloak도)뿐이며, 나머지는 Docker 내부 네트워크에서 서로 통신합니다.

처음 시작할 때는 이후보다 시간이 더 걸립니다. 이미지를 빌드하고 데이터베이스 스키마를 만들어야 하며, MCP 프록시는 필요한 인증서를 백엔드에서 받을 때까지 기다린 뒤에야 요청을 받기 때문입니다.

## HTTPS로 제공하기 {#https}

`compose.https.yml`을 추가하면 ingress 앞에 [Caddy](https://caddyserver.com/)가 놓입니다. Caddy가 포트 80과 443에서 유일한 진입점이 되어 `APP_BASE_URL` 주소의 인증서를 받고, 평문 HTTP를 HTTPS로 리디렉션합니다. 주소가 `https://`이면 로그인 쿠키에도 Secure가 붙고, [싱글 사인온](../guides/single-sign-on.md)의 **리디렉션 URI**도 이 주소로 만들어집니다.

```bash
echo APP_BASE_URL=https://a2flow.example.com >> .env
docker compose -f compose.yml -f compose.https.yml up --build
```

설정한 주소를 엽니다. 주소에 포트는 쓸 수 없습니다. 공개되는 포트는 80과 443뿐이며, 포트가 붙은 주소로는 Caddy가 시작되지 않습니다. 그다음 동작은 호스트 이름에 따라 달라집니다.

| `APP_BASE_URL` | 인증서 | 시작하기 전에 |
|---|---|---|
| 공개 호스트 이름(예: `https://a2flow.example.com`) | Let's Encrypt에서 받고 자동으로 갱신합니다 | 이름의 DNS가 이 호스트를 가리키게 하고, 인터넷에서 포트 80과 443에 접근할 수 있게 합니다 |
| 설정하지 않음(`https://localhost`) | Caddy가 직접 만든 인증 기관이 발급합니다 | 필요 없습니다. 다만 그 인증 기관을 신뢰하기 전까지 브라우저가 인증서 경고를 표시합니다(아래 참조) |

브라우저가 `https://localhost`를 신뢰하게 하려면 인증 기관의 루트 인증서를 꺼내 운영 체제나 브라우저의 신뢰할 수 있는 루트 인증서에 추가합니다.

```bash
docker compose -f compose.yml -f compose.https.yml cp caddy:/data/caddy/pki/authorities/local/root.crt .
```

인증서와 로컬 인증 기관은 `caddy-data` 볼륨에 저장됩니다. 이 볼륨은 지우지 마세요. 지우면 인증서가 새로 발급되고, 이미 신뢰한 루트 인증서와 더 이상 맞지 않게 됩니다.

## OpenBao로 Vault 시크릿 사용해 보기 {#openbao}

[OpenBao](https://openbao.org/)는 오픈 소스 Vault 포크로, A2Flow는 HashiCorp Vault에 연결할 때와 똑같은 방식으로 여기에 연결합니다. 이 스택에서는 A2Flow 옆에 OpenBao를 함께 시작할 수 있으므로, 별도의 Vault 없이도 [Vault 유형 시크릿](../guides/secrets.md)을 사용해 볼 수 있습니다.

```bash
docker compose --profile openbao up --build
```

OpenBao는 A2Flow와 같은 PostgreSQL에 데이터를 저장하므로 다시 시작해도 데이터가 유지되며, 시작할 때마다 스스로 봉인을 해제합니다. 봉인 해제에 쓰는 키는 `openbao-unseal` 볼륨에 있습니다. 이 키가 없으면 데이터를 읽을 수 없으므로 `pgdata`와 함께 백업하세요. 이 구성은 연동을 시험해 보기 위한 것이며 프로덕션용이 아닙니다.

### 1. OpenBao 초기화(최초 시작 시에만) {#1-initialize-openbao-first-start-only}

```bash
docker compose exec openbao bao operator init -recovery-shares=1 -recovery-threshold=1
```

출력되는 **Initial Root Token**을 적어 두세요. 이 토큰은 한 번만 표시됩니다.

### 2. A2Flow용 AppRole 만들기 {#2-create-an-approle-for-a2flow}

UI에서는 AppRole 역할을 만들 수 없으므로 이 단계는 명령줄에서 진행합니다. `<root-token>`을 1단계의 토큰으로 바꾸세요.

```bash
docker compose exec -e BAO_TOKEN=<root-token> openbao sh -c '
  bao secrets enable -path=secret kv-v2
  bao auth enable approle
  printf "path \"secret/data/a2flow/*\" { capabilities = [\"read\"] }" | bao policy write a2flow -
  bao write auth/approle/role/a2flow token_policies=a2flow token_ttl=1h
  bao read -field=role_id auth/approle/role/a2flow/role-id; echo
  bao write -f -field=secret_id auth/approle/role/a2flow/secret-id; echo'
```

마지막 두 줄에서 **role id**와 **secret id**가 출력됩니다. 이 정책으로 A2Flow는 `a2flow/` 아래의 경로만 읽을 수 있습니다.

### 3. OpenBao UI에서 시크릿 만들기 {#3-create-a-secret-in-the-openbao-ui}

1. [http://localhost:8200/ui](http://localhost:8200/ui)를 열고 **Token** 방식과 루트 토큰으로 로그인합니다. OpenBao는 페이지를 새로 고치면 루트 토큰 로그인을 유지하지 않으므로, URL을 직접 입력하지 말고 화면을 클릭하여 이동하세요.
2. **secret/** 엔진을 열고 **Create secret**을 선택합니다.
3. 경로에 `a2flow/demo`를 입력하고 `username`과 `password` 항목을 추가한 뒤 저장합니다.

### 4. A2Flow 연결 {#4-connect-a2flow}

1. A2Flow에 `root`로 로그인합니다. **시스템 설정**에서 **전역 Vault 주소**를 `http://openbao:8200`으로 설정하고 저장합니다.
2. **테넌트**를 열고 **Default**를 엽니다. **전역 Vault에 로그인**을 선택하고, **Vault 인증 방식**으로 **AppRole**을 고른 다음, 2단계의 role id와 secret id를 입력하고 저장합니다.
3. `admin`으로 로그인합니다. **시크릿**에서 유형이 **HashiCorp Vault**이고 **Vault 마운트**가 `secret`, **Vault 경로**가 `a2flow/demo`인 시크릿을 만듭니다.

이 시크릿은 다른 시크릿과 똑같이 참조합니다. 예를 들어 [MCP 서버](../guides/mcp-servers.md)의 환경 변수에 `${secret:<name>/password}`로 지정합니다. 시크릿을 선택하는 곳에는 그 키인 `username`과 `password`가 표시됩니다. 이 목록은 그 순간 OpenBao에서 읽어 온 것이므로, 표시된다면 연결이 정상이라는 뜻입니다.

OpenBao UI를 8200이 아닌 호스트 포트로 공개하려면 `.env`에 `OPENBAO_PORT`를 설정하세요. A2Flow 자체는 항상 내부 네트워크에서 `http://openbao:8200`으로 접속합니다.

## Keycloak으로 싱글 사인온 사용해 보기 {#keycloak}

[Keycloak](https://www.keycloak.org/)은 오픈 소스 IdP입니다. 이 스택에서는 A2Flow용으로 이미 설정된 Keycloak을 A2Flow 옆에 함께 시작할 수 있으므로, 별도의 IdP 없이도 [싱글 사인온](../guides/single-sign-on.md)을 사용해 볼 수 있습니다.

```bash
docker compose --profile keycloak up --build
```

Keycloak은 [http://keycloak.localhost:8180](http://keycloak.localhost:8180)에 공개되며, 관리 콘솔에는 `admin` / `admin`으로 로그인합니다(비밀번호를 바꾸려면 `.env`에 `KEYCLOAK_ADMIN_PASSWORD`를 설정하세요). Chrome, Edge, Firefox는 `keycloak.localhost`를 스스로 찾습니다. 다른 브라우저에서는 먼저 hosts 파일에 `127.0.0.1 keycloak.localhost` 줄을 추가하세요. 컨테이너를 다시 만들면 Keycloak은 아무것도 남기지 않고 아래 설정에서 다시 시작하므로, 관리 콘솔에서 바꾼 내용은 사라집니다.

시작 시점에 다음이 이미 설정되어 있습니다.

| 항목 | 값 |
|---|---|
| 렐름 | `a2flow` |
| 발급자 URL | `http://keycloak.localhost:8180/realms/a2flow` |
| 클라이언트 ID | `a2flow` |
| 클라이언트 시크릿 | `a2flow-dev-secret` |
| 리디렉션 URI | `http://localhost:3000`(또는 `APP_BASE_URL`)과 `https://localhost`. 각각 뒤에 A2Flow의 콜백 경로가 붙습니다 |
| 그룹 클레임 | `groups` |
| 사용자 | `alice`는 그룹 `a2flow-admins`, `bob`은 그룹 `a2flow-users`에 속합니다. 두 사람 모두 비밀번호는 `password`입니다 |

### 1. A2Flow 연결 {#1-connect-a2flow}

1. A2Flow에 `admin`으로 로그인하고 관리 사이드바의 **테넌트 설정**을 엽니다.
2. **싱글 사인온** 섹션에서 위 표의 값으로 **발급자 URL**, **클라이언트 ID**, **클라이언트 시크릿**을 채우고 **싱글 사인온 사용**을 선택한 뒤 저장합니다.
3. **사용자 그룹**을 열고, 원하는 역할을 가진 그룹을 열거나 새로 만든 다음 **IdP 그룹**에 `a2flow-admins`를 입력하고 저장합니다.

### 2. 로그인하기 {#2-sign-in}

1. 로그아웃합니다. 로그인 화면의 **테넌트**에 `default`를 입력하고 **SSO로 로그인**을 누릅니다.
2. Keycloak 로그인 페이지에서 `alice` / `password`로 로그인합니다. 1단계의 그룹 멤버인 Alice로 A2Flow에 로그인된 상태로 돌아옵니다.
3. `bob`으로도 해 보세요. 그의 유일한 그룹 `a2flow-users`는 어떤 사용자 그룹에도 매핑되어 있지 않으므로 로그인이 거부됩니다. 사용자 그룹에 매핑하면 로그인할 수 있게 됩니다.

Keycloak은 SAML도 지원하지만, A2Flow는 OpenID Connect로만 로그인합니다.
