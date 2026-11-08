---
title: 데모 데이터
sidebar_position: 4
---

# 데모 데이터

백엔드에 `DEMO_DATA=true`를 설정하면, 승인을 거쳐 실제로 상태를 변경하는 세 가지 예제인 "EC2 인스턴스 시작", "GKE Pod 재시작", "Azure Key Vault 시크릿 교체"에 필요한 모든 것이 초기 생성되는 **Default** 테넌트에 등록됩니다. 따라서 항목을 하나하나 직접 등록하지 않아도 바로 실행해 볼 수 있습니다. [워크플로](../guides/workflows.md) 자체는 일부러 등록하지 않습니다. 이 레코드들은 워크플로를 생성하는 재료이며, 실제로 생성하는 과정은 [따라 하기](./walkthrough.mdx)에서 안내합니다.

## 활성화 {#enabling-it}

`backend/.env`에 플래그를 추가하고 백엔드를 다시 시작합니다. [Docker Compose](./docker-compose.md)에서는 `compose.yml`이 `DEMO_DATA: ${DEMO_DATA:-true}`를 설정하므로 이미 활성화되어 있습니다.

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
DEMO_GCP_CREDENTIALS_JSON='{"type":"service_account",...}'
DEMO_AZURE_TENANT_ID=...
DEMO_AZURE_CLIENT_ID=...
DEMO_AZURE_CLIENT_SECRET=...
```

- `DEMO_PASSWORD`는 데모 사용자 11명이 모두 함께 사용하며, `ROOT_PASSWORD` / `ADMIN_PASSWORD`와 마찬가지로 설정하지 않으면 자동으로 생성되어 로그에 한 번만 출력됩니다. 이 값은 계정 중 하나가 없을 때만 참조됩니다.
- AWS 자격 증명, Google Cloud 자격 증명, Azure 자격 증명은 선택 사항입니다. 설정하지 않으면 `REPLACE_ME` 자리 표시자가 대신 저장되므로 데모의 형태는 갖춰지며, 실제 값은 [시크릿](../guides/secrets.md) 페이지에서 입력하면 됩니다.
- `DEMO_AWS_REGION`은 데모 AWS MCP 서버의 도구가 작업할 리전입니다. 기본값은 `us-east-1`입니다.
- `DEMO_GCP_CREDENTIALS_JSON`은 한 줄로 작성한 Google Cloud 자격 증명 JSON입니다. 서비스 계정 키이거나, OAuth 클라이언트 ID와 시크릿으로 한 번 로그인한 뒤 `gcloud`가 작성하는 authorized-user JSON입니다. GKE MCP 서버는 이 값으로 액세스 토큰을 발급합니다. Google의 MCP 서버는 API 키를 받지 않습니다. 둘 중 하나를 얻는 방법은 [Google Cloud MCP 서버](../guides/mcp-servers.md#google-cloud-mcp-servers)를 참조하세요.
- `DEMO_AZURE_TENANT_ID`, `DEMO_AZURE_CLIENT_ID`, `DEMO_AZURE_CLIENT_SECRET`은 Azure 서비스 주체입니다. 테넌트, 앱의 클라이언트 ID, 앱의 클라이언트 시크릿 하나를 `az ad sp create-for-rbac`가 출력하는 그대로 넣습니다. 데모에서 시크릿을 교체할 볼트에 대해 `Microsoft.KeyVault/vaults/secrets/readMetadata/action` 및 `Microsoft.KeyVault/vaults/secrets/setSecret/action` 데이터 작업만 있는 사용자 지정 역할을 부여하세요. 액세스 정책을 사용하는 볼트라면 시크릿 권한 중 **List**와 **Set**만 부여합니다. 기본 제공 **Key Vault Secrets Officer** 역할도 사용할 수 있지만, 이 역할은 모든 시크릿의 값까지 읽을 수 있습니다.

⚠️ AWS, GKE, Azure MCP 서버는 읽기뿐 아니라 **상태를 변경하는** 작업도 실행할 수 있습니다. AWS MCP 서버의 자격 증명은 실제 AWS 리소스를 만들고 삭제할 수 있고, GKE MCP 서버의 ID는 실제 클러스터에서 워크로드를 롤링 재시작하거나 Pod를 삭제할 수 있으며, Azure MCP 서버의 서비스 주체는 Key Vault 시크릿을 쓸 수 있습니다. 세 가지 모두 일회용 계정이나 범위를 엄격히 제한한 자격 증명을 사용하세요. 실제 제공자를 전혀 건드리지 않고 사용해 보려면 아래의 [사용해 보기](#trying-it-out)를 참조하세요.

## 등록되는 항목 {#what-gets-registered}

- **[에이전트 스킬](../guides/agent-skills.md) `Demo AWS EC2 Launch`** — 인스턴스 구성을 수집하고, 그 구성에 대해 매니저의 명시적인 승인을 받은 다음, MCP 도구로 인스턴스를 시작합니다. 저장소는 시작 후 백그라운드에서 복제되므로, 스킬을 사용할 수 있게 되기까지 잠시 `복제 중`으로 표시됩니다.
- **[에이전트 스킬](../guides/agent-skills.md) `Demo GKE Pod Restart`** — 정확한 대상(프로젝트, 클러스터, 네임스페이스, 그리고 Deployment/StatefulSet 이름 또는 단일 Pod 이름)을 사용자와 합의하고, 바로 그 대상에 대해 매니저의 명시적인 승인을 받습니다. 그런 다음 기본적으로 GKE MCP Server로 워크로드를 롤링 재시작하고, 사용자가 Pod 하나만 없애기를 원하면 해당 Pod를 삭제하여 소유 컨트롤러가 다시 만들게 한 뒤, 결과를 보고합니다. 저장소도 같은 방식으로 복제되므로 처음에는 마찬가지로 `복제 중`으로 표시됩니다.
- **[에이전트 스킬](../guides/agent-skills.md) `Demo Azure Key Vault Secret Rotation`** — Key Vault와 그 안의 기존 시크릿을 사용자와 합의하고, 바로 그 시크릿에 대해 매니저의 명시적인 승인을 받은 다음, 새로 생성한 임의의 값을 Azure MCP Server로 시크릿의 새 버전으로 쓰고, 새 버전이 만들어진 시점을 보고합니다. 값은 채팅에 절대 표시하지 않습니다. 저장소도 같은 방식으로 복제되므로 처음에는 마찬가지로 `복제 중`으로 표시됩니다.
- **[MCP 서버](../guides/mcp-servers.md) `AWS MCP Server`** — AWS의 관리형 AWS MCP Server에 연결하는 `stdio` 서버이며, EC2 도구는 여기에서 제공됩니다.
- **[MCP 서버](../guides/mcp-servers.md) `GKE MCP Server`** — Google Cloud의 관리형 GKE(Google Kubernetes Engine) MCP 서버 전체 엔드포인트에 연결하는 `streamable_http` 서버입니다. `Authorization` 헤더가 `Bearer ${gcp-token:demo-gcp-credentials/GOOGLE_CREDENTIALS_JSON}`이므로, 연결할 때마다 `demo-gcp-credentials` 시크릿으로 새로 발급한 액세스 토큰을 보냅니다. 도구는 클러스터와 Kubernetes 리소스를 관리할 수 있으며, 여기에는 워크로드 롤링 재시작과 Pod 삭제도 포함됩니다.
- **[MCP 서버](../guides/mcp-servers.md) `Azure MCP Server`** — Microsoft의 Azure MCP Server를 Key Vault 도구로만 제한하여 실행하는 `stdio` 서버입니다. `demo-azure-credentials` 시크릿의 서비스 주체로 로그인하며, 도구는 Key Vault의 시크릿, 키, 인증서를 나열하고 쓸 수 있습니다. 시크릿에 대한 작업을 할 때마다 먼저 동의를 구하며, 이 질문은 [채팅의 확인 요청](../guides/workflow-executions.md#mcp-server-confirmations)으로 실행 요청자에게 전달됩니다. 이는 교체에 대한 매니저의 승인과 별도입니다. 데모 스킬은 디자인 에이전트에게 이 도구를 질문하는 도구로 표시하도록 지시하므로, 도구를 사용하는 각 작업은 요청자가 재개할 때까지 기다립니다. 새 시크릿 값은 Key Vault로 가는 과정에서 에이전트의 대화를 거치므로, 실행의 채팅은 시크릿과 동일하게 취급하세요.
- **[MCP 서버](../guides/mcp-servers.md) `EC2 Cost Estimator`** — Python [스크립트 서버](../guides/mcp-servers.md#writing-a-script)입니다. 도구는 지정한 리전의 가격을 AWS Price List에서 실시간으로 가져와 EC2 인스턴스 유형의 월간 온디맨드 비용을 추정하고(`estimate_monthly_cost`), 여러 유형을 비용순으로 나열합니다(`compare_instance_types`). **패키지**에서 `boto3`를 설치하고 같은 `demo-aws-credentials` 시크릿을 읽으므로, **테스트 실행**에서 사용해 보려면 AWS Price List를 읽을 수 있는 자격 증명(`pricing:GetProducts`)이 필요합니다. 읽기만 수행합니다.
- **[MCP 서버](../guides/mcp-servers.md) `Kubernetes Manifest Toolkit`** — JavaScript 스크립트 서버입니다. 도구는 Kubernetes 매니페스트에 누락된 필수 필드가 있는지 확인하고(`validate_manifest`), Deployment, StatefulSet, DaemonSet을 롤링 재시작하는 패치를 만듭니다(`build_restart_patch`). **패키지**에서 `js-yaml`을 설치하고, 자격 증명이 필요 없으며, 클러스터에 전혀 접속하지 않으므로 **테스트 실행**에서 바로 사용할 수 있습니다.
- **[MCP 서버](../guides/mcp-servers.md) `Secret Value Generator`** — JavaScript 스크립트 서버입니다. 도구는 하나뿐이며 암호학적으로 안전한 임의의 시크릿 값을 생성합니다(`generate_secret_value`). 패키지를 설치하지 않고, 자격 증명이 필요 없으며, Azure에 전혀 접속하지 않으므로 **테스트 실행**에서 바로 사용할 수 있습니다.
- **[지식 베이스](../guides/knowledge-bases.md) `AWS EC2 Pricing`** — 소스 `ec2-on-demand-pricing.pdf` 하나를 포함합니다. 이 가격표에는 [따라 하기](./walkthrough.mdx)에서 제시하는 인스턴스 유형 10종의 `us-east-1`, `us-east-2`, `us-west-2` 기준 시간당 및 월간 온디맨드 비용, vCPU, 메모리와 함께 스토리지 및 퍼블릭 IP 요금이 실려 있습니다. 수치는 데모용 참고값입니다. 소스는 **읽지 않음** 상태로 등록되므로, 누군가 **읽기**를 클릭할 때까지 지식 베이스에 페이지가 없습니다. 따라 하기에서는 AWS 개발자가 이 작업을 합니다. EC2 시작 워크플로에 연결하면 에이전트가 요청된 인스턴스의 비용을 답할 수 있습니다.
- **[시크릿](../guides/secrets.md) `demo-aws-credentials`** — AWS MCP Server가 읽는 AWS 액세스 키 ID와 시크릿 액세스 키입니다.
- **[시크릿](../guides/secrets.md) `demo-gcp-credentials`** — GKE MCP Server가 액세스 토큰을 발급할 때 사용하는 Google Cloud 자격 증명 JSON입니다.
- **[시크릿](../guides/secrets.md) `demo-azure-credentials`** — Azure MCP Server가 로그인할 때 사용하는 Azure 서비스 주체의 테넌트 ID, 클라이언트 ID, 클라이언트 시크릿입니다.
- **[도구 모의](../guides/tool-mocks.md)** — 데모 실행에서 부작용이 있는 도구를 대신하는 스텁입니다. AWS MCP Server의 `aws___call_aws`와 `aws___run_script`는 각각 시작 성공을 반환하고, GKE MCP Server의 `patch_k8s_resource`와 `delete_k8s_resource`는 각각 롤링 재시작 성공과 Pod 삭제 성공을 반환하며, Azure MCP Server의 `keyvault_secret_get`과 `keyvault_secret_create`는 각각 볼트의 시크릿 목록과 새 시크릿 버전을 반환하고, 내장 `request_approval`은 승인됨을 반환합니다. 초안 실행의 **실행** 대화 상자에서 이 스텁을 선택하면 AWS, 실제 GKE 클러스터, 실제 Key Vault를 건드리지 않고 매니저를 기다리지도 않은 채 세 워크플로 중 어느 것이든 끝까지 진행할 수 있습니다.
- **[태그](../guides/tags.md)** `AWS`, `GCP`, `Azure` — 각각 [액세스 제어 태그](../guides/tags.md#access-control-tags)이므로, `Demo AWS Group` / `Demo GCP Group` / `Demo Azure Group` 구성원(및 관리자 또는 슈퍼 관리자)만 해당 제공자의 태그가 붙은 위 레코드를 볼 수 있습니다. `EC2 Cost Estimator`와 `AWS EC2 Pricing` 지식 베이스에는 `AWS`, `Kubernetes Manifest Toolkit`에는 `GCP`, `Secret Value Generator`에는 `Azure`가 붙어 있어, 이들이 돕는 제공자 레코드와 나란히 다뤄집니다. `Approval Required`는 세 에이전트 스킬 모두에 붙는 일반 태그로, 아무것도 제한하지 않습니다.
- **데모 사용자와 그룹:**

| 사용자 | 역할 | 액세스 제어 그룹 | 하는 일 |
|---|---|---|---|
| `demo-aws-developer` | 개발자 | `Demo AWS Group` | EC2 시작 워크플로를 생성합니다 |
| `demo-aws-reviewer` | 검토자 | `Demo AWS Group` | EC2 시작 워크플로를 게시합니다 |
| `demo-aws-requester` | 요청자 | `Demo AWS Group` | EC2 시작 워크플로를 실행합니다 |
| `demo-gcp-developer` | 개발자 | `Demo GCP Group` | GKE Pod 재시작 워크플로를 생성합니다 |
| `demo-gcp-reviewer` | 검토자 | `Demo GCP Group` | GKE Pod 재시작 워크플로를 게시합니다 |
| `demo-gcp-requester` | 요청자 | `Demo GCP Group` | GKE Pod 재시작 워크플로를 실행합니다 |
| `demo-azure-developer` | 개발자 | `Demo Azure Group` | 시크릿 교체 워크플로를 생성합니다 |
| `demo-azure-reviewer` | 검토자 | `Demo Azure Group` | 시크릿 교체 워크플로를 게시합니다 |
| `demo-azure-requester` | 요청자 | `Demo Azure Group` | 시크릿 교체 워크플로를 실행합니다 |
| `demo-approver-1`, `demo-approver-2` | 승인자 | `Demo Approvers`(세 태그 모두) | 인스턴스 시작, Pod 재시작 또는 교체를 승인합니다 |

이들 중 역할을 직접 가진 계정은 없습니다. 각 계정은 [사용자 그룹](../guides/users-and-groups.md#user-groups)인 `Demo Developers`, `Demo Reviewers`, `Demo Requesters`, `Demo Approvers`에서 역할을 상속합니다. AWS, GCP, Azure의 세 사람 조는 각각 두 번째 그룹인 `Demo AWS Group`, `Demo GCP Group`, `Demo Azure Group`에도 속합니다. 이 그룹은 자체적으로 역할을 부여하지 않으며, 해당하는 액세스 제어 태그를 보유하는 것이 유일한 목적입니다. 그래서 그 세 사람만 해당 제공자의 태그가 붙은 레코드를 볼 수 있고 다른 사람은 볼 수 없습니다. 다만 관리자(또는 슈퍼 관리자)는 예외로, [액세스 제어 태그를 완전히 우회](../guides/tags.md#access-control-tags)하므로 그룹에 속할 필요가 없습니다. `Demo Approvers` 자체에는 `AWS`, `GCP`, `Azure` 액세스 제어 태그가 직접 붙어 있습니다. 승인자는 특정 제공자에 국한되지 않기 때문입니다. 세 데모 워크플로 중 어디에서 온 요청이든 어느 데모 승인자에게나 보낼 수 있는 것도 이 덕분입니다.

## 사용해 보기 {#trying-it-out}

[따라 하기](./walkthrough.mdx)에서는 `root` 로그인 한 번으로 각 데모 계정을 차례로 [대리 로그인](../concepts/impersonation.md)하면서, 어느 예제든 생성, 게시, 실행, 승인, 확인까지 처음부터 끝까지 진행합니다. `DEMO_PASSWORD`로 각 계정에 직접 로그인해도 똑같이 할 수 있으며, 누가 무엇을 하는지는 위 표에 나와 있습니다.

`Demo AWS Group`, `Demo GCP Group`, `Demo Azure Group`은 각각 자신의 제공자 레코드만 볼 수 있으므로, `demo-aws-developer`는 `Demo GKE Pod Restart`를 열 수 없고 `demo-gcp-developer`는 `Demo Azure Key Vault Secret Rotation`을 열 수 없습니다. `Demo Approvers`에 세 액세스 제어 태그가 모두 직접 붙어 있으므로 승인자 계정은 어느 쪽이든 모든 예제에 사용할 수 있습니다. GKE를 실제로 실행하려면 실제 GKE 클러스터에 접근할 수 있는 ID의 자격 증명을 `DEMO_GCP_CREDENTIALS_JSON`에 설정해야 하고, 실제로 교체하려면 `DEMO_AZURE_*` 서비스 주체에 실제 볼트의 시크릿에 대한 쓰기 권한이 있어야 합니다.

**AWS 계정, GKE 클러스터, Key Vault가 없나요?** 게시하지 말고 워크플로가 아직 `초안`일 때 실행하세요. 해당 제공자의 개발자 계정(`demo-aws-developer`, `demo-gcp-developer`, `demo-azure-developer`)은 개발자 역할이므로 이렇게 실행할 수 있으며, 테넌트의 [도구 모의](../guides/tool-mocks.md)는 초안 실행의 대화 상자에만 제공됩니다. **모의 도구**에 표시되는 미리 등록된 스텁(인스턴스 시작은 `aws___call_aws` 또는 `aws___run_script`, Pod 재시작은 `patch_k8s_resource` 또는 `delete_k8s_resource`, 교체는 `keyvault_secret_get`과 `keyvault_secret_create`, 그리고 `request_approval`)을 선택하면, 실제 제공자에 접속하거나 사람을 기다리지 않고 워크플로 전체가 진행됩니다. 교체용 모의를 선택하면 볼트의 시크릿 목록도 가상의 것이 되므로, 그 목록에서 `db-password`를 선택하세요.

## 제거 {#removing-it}

`DEMO_DATA=false`로 설정하면(또는 해당 줄을 제거하면) 다음 시작 시 **이 레코드들이 다시 제거됩니다**. 이 플래그는 양방향으로 선언적으로 작동합니다.

의도적으로 남는 것이 두 가지 있습니다. 다른 항목이 의존하게 된 데모 레코드(예: 데모 스킬을 바탕으로 만든 워크플로)는 삭제되지 않고 로그에 기록된 채 유지되며, 레코드를 만든 데모 사용자는 해당 레코드에서 이름을 계속 확인할 수 있도록 소프트 삭제됩니다.
