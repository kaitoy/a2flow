---
title: 演示数据
sidebar_position: 4
---

# 演示数据

在后端设置 `DEMO_DATA=true` 后，系统会在预置的 **Default** 租户中注册三个需要审批且会更改状态的示例（“启动 EC2 实例”“重启 GKE Pod”和“轮换 Azure Key Vault 密钥”）所需的全部内容，这样无需逐项手动注册，就有现成的东西可以运行。[工作流](../guides/workflows.md)本身特意不预置：这些记录是生成工作流的原料，而[操作演练](./walkthrough.mdx)会带您实际走一遍生成过程。

## 启用 {#enabling-it}

将该标志添加到 `backend/.env` 并重启后端。使用 [Docker Compose](./docker-compose.md) 时它已经启用：`compose.yml` 设置了 `DEMO_DATA: ${DEMO_DATA:-true}`。

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

- `DEMO_PASSWORD` 由全部 11 个演示用户共用，未设置时的处理方式与 `ROOT_PASSWORD` / `ADMIN_PASSWORD` 相同：自动生成并在日志中输出一次。只有在某个账户尚不存在时才会用到它。
- AWS 凭据、Google Cloud 凭据和 Azure 凭据都是可选的。未设置时会保存 `REPLACE_ME` 占位符，这样演示在结构上是完整的，真实的值可以之后在[密钥](../guides/secrets.md)页面中填写。
- `DEMO_AWS_REGION` 是演示用 AWS MCP 服务器的工具所操作的区域，默认为 `us-east-1`。
- `DEMO_GCP_CREDENTIALS_JSON` 是写成一行的 Google Cloud 凭据 JSON，可以是服务账号密钥，也可以是使用 OAuth 客户端 ID 和客户端密钥一次性登录后由 `gcloud` 写出的 authorized-user JSON。GKE MCP 服务器用它签发访问令牌；Google 的 MCP 服务器不接受 API 密钥。这两种凭据的获取方式请参阅 [Google Cloud MCP 服务器](../guides/mcp-servers.md#google-cloud-mcp-servers)。
- `DEMO_AZURE_TENANT_ID`、`DEMO_AZURE_CLIENT_ID` 和 `DEMO_AZURE_CLIENT_SECRET` 对应一个 Azure 服务主体，即 `az ad sp create-for-rbac` 输出的租户、应用的客户端 ID 和它的一个客户端密钥。在演示要轮换密钥的 Key Vault 上，为它授予一个自定义角色，只包含 `Microsoft.KeyVault/vaults/secrets/readMetadata/action` 和 `Microsoft.KeyVault/vaults/secrets/setSecret/action` 这两个数据操作；如果该 Key Vault 使用访问策略，则只授予 **List** 和 **Set** 这两项密钥权限。内置的 **Key Vault Secrets Officer** 角色也可以使用，但它还能读取所有密钥的值。

⚠️ AWS、GKE 和 Azure 的 MCP 服务器不仅能读取，还能执行**会更改状态**的操作。AWS MCP 服务器的凭据可以创建和删除真实的 AWS 资源，GKE MCP 服务器的身份可以在真实集群上滚动重启工作负载或删除 Pod，Azure MCP 服务器的服务主体可以写入 Key Vault 密钥。这三者都请使用一次性账户或权限范围严格受限的凭据。要在完全不接触真实提供商的情况下试用，请参阅下方的[试用](#trying-it-out)。

## 注册的内容 {#what-gets-registered}

- **[代理技能](../guides/agent-skills.md) `Demo AWS EC2 Launch`**：收集实例配置，获得经理对该配置的明确批准，然后通过 MCP 工具启动实例。它的仓库会在启动后于后台克隆，因此该技能在可以使用之前会短暂显示为 `克隆中`。
- **[代理技能](../guides/agent-skills.md) `Demo GKE Pod Restart`**：与用户商定确切的目标（项目、集群、命名空间，以及 Deployment/StatefulSet 名称或单个 Pod 名称），获得经理对该确切目标的明确批准，然后默认通过 GKE MCP Server 滚动重启该工作负载；如果用户只想去掉某一个 Pod，则删除该 Pod，由其所属的控制器重新创建。最后报告结果。它的仓库以同样的方式克隆，因此一开始同样显示为 `克隆中`。
- **[代理技能](../guides/agent-skills.md) `Demo Azure Key Vault Secret Rotation`**：与用户商定 Key Vault 及其中一个现有密钥，获得经理对该确切密钥的明确批准，然后通过 Azure MCP Server 将新生成的随机值写入为该密钥的新版本，并报告新版本的创建时间。它绝不会在聊天中显示该值。它的仓库以同样的方式克隆，因此一开始同样显示为 `克隆中`。
- **[MCP 服务器](../guides/mcp-servers.md) `AWS MCP Server`**：连接 AWS 托管的 AWS MCP Server 的 `stdio` 服务器，EC2 工具就来自那里。
- **[MCP 服务器](../guides/mcp-servers.md) `GKE MCP Server`**：连接 Google Cloud 托管的 GKE（Google Kubernetes Engine）MCP 服务器完整端点的 `streamable_http` 服务器。它的 `Authorization` 标头是 `Bearer ${gcp-token:demo-gcp-credentials/GOOGLE_CREDENTIALS_JSON}`，因此每次连接都会发送一个根据 `demo-gcp-credentials` 密钥新签发的访问令牌。它的工具可以管理集群及其 Kubernetes 资源，包括滚动重启工作负载或删除 Pod。
- **[MCP 服务器](../guides/mcp-servers.md) `Azure MCP Server`**：运行 Microsoft 的 Azure MCP Server 的 `stdio` 服务器，仅限其 Key Vault 工具。它使用 `demo-azure-credentials` 密钥中的服务主体登录，其工具可以列出和写入 Key Vault 中的密钥（secret）、加密密钥（key）和证书。在对密钥执行每项操作之前，它都会征求同意，这个问题会以[聊天中的确认](../guides/workflow-executions.md#mcp-server-confirmations)形式发给这次运行的请求者，这是在经理批准轮换之外的又一道确认。演示技能会告诉设计代理把这些工具标记为“询问”，因此使用这些工具的每个任务都会等待请求者继续。新的密钥值在发送到 Key Vault 的途中会经过代理的对话，因此请像对待密钥本身一样对待这次运行的聊天。
- **[MCP 服务器](../guides/mcp-servers.md) `EC2 Cost Estimator`**：Python [脚本服务器](../guides/mcp-servers.md#writing-a-script)，其工具根据从 AWS Price List 实时获取的所询问区域的价格，估算某个 EC2 实例类型的按需月费用（`estimate_monthly_cost`），并按费用对多个实例类型排序（`compare_instance_types`）。它在**软件包**下安装 `boto3`，并读取同一个 `demo-aws-credentials` 密钥，因此要在**测试运行**中试用，需要有权读取 AWS Price List（`pricing:GetProducts`）的凭据。它只执行读取操作。
- **[MCP 服务器](../guides/mcp-servers.md) `Kubernetes Manifest Toolkit`**：JavaScript 脚本服务器，其工具检查 Kubernetes 清单是否缺少必填字段（`validate_manifest`），并构建用于滚动重启 Deployment、StatefulSet 或 DaemonSet 的补丁（`build_restart_patch`）。它在**软件包**下安装 `js-yaml`，不需要凭据，也从不连接集群，因此可以直接在**测试运行**中使用。
- **[MCP 服务器](../guides/mcp-servers.md) `Secret Value Generator`**：JavaScript 脚本服务器，其唯一的工具用于生成加密安全的随机密钥值（`generate_secret_value`）。它不安装任何软件包，不需要凭据，也从不连接 Azure，因此可以直接在**测试运行**中使用。
- **[知识库](../guides/knowledge-bases.md) `AWS EC2 Pricing`**：包含一个来源 `ec2-on-demand-pricing.pdf`。这是一份价格表，列出了[操作演练](./walkthrough.mdx)提供的十种实例类型在 `us-east-1`、`us-east-2` 和 `us-west-2` 的按需小时费用和月费用、vCPU 和内存，以及存储和公有 IP 费用。这些数字是演示用的参考值。该来源注册时的状态为**未读取**，因此在有人点击**读取**之前，知识库中没有任何页面；在操作演练中，这一步由 AWS 开发人员完成。将它关联到 EC2 启动工作流后，代理就能回答所请求的实例要花多少钱。
- **[密钥](../guides/secrets.md) `demo-aws-credentials`**：AWS MCP Server 读取的 AWS 访问密钥 ID 和秘密访问密钥。
- **[密钥](../guides/secrets.md) `demo-gcp-credentials`**：GKE MCP Server 用来签发访问令牌的 Google Cloud 凭据 JSON。
- **[密钥](../guides/secrets.md) `demo-azure-credentials`**：Azure MCP Server 登录时使用的 Azure 服务主体的租户 ID、客户端 ID 和客户端密钥。
- **[工具模拟](../guides/tool-mocks.md)**：演示运行中有副作用的工具的桩：AWS MCP Server 上的 `aws___call_aws` 和 `aws___run_script`，都返回启动成功；GKE MCP Server 上的 `patch_k8s_resource` 和 `delete_k8s_resource`，分别返回滚动重启成功和 Pod 删除成功；Azure MCP Server 上的 `keyvault_secret_get` 和 `keyvault_secret_create`，分别返回 Key Vault 的密钥列表和新的密钥版本；以及内置的 `request_approval`，返回已批准。在草稿运行的**运行**对话框中选择它们后，三个工作流中的任何一个都能运行到底，既不会接触 AWS、真实的 GKE 集群或真实的 Key Vault，也不用等待经理。
- **[标签](../guides/tags.md)** `AWS`、`GCP` 和 `Azure`：它们都是[访问控制标签](../guides/tags.md#access-control-tags)，因此只有 `Demo AWS Group` / `Demo GCP Group` / `Demo Azure Group` 的成员（以及管理员或超级管理员）才能看到上述带有相应提供商标签的记录。`EC2 Cost Estimator` 和 `AWS EC2 Pricing` 知识库带有 `AWS`，`Kubernetes Manifest Toolkit` 带有 `GCP`，`Secret Value Generator` 带有 `Azure`，与它们所协助的提供商记录相同。`Approval Required` 是三个代理技能都带有的普通标签，不限制任何内容。
- **演示用户和用户组：**

| 用户 | 角色 | 访问控制用户组 | 职责 |
|---|---|---|---|
| `demo-aws-developer` | 开发人员 | `Demo AWS Group` | 生成 EC2 启动工作流 |
| `demo-aws-reviewer` | 审阅者 | `Demo AWS Group` | 发布 EC2 启动工作流 |
| `demo-aws-requester` | 请求者 | `Demo AWS Group` | 运行 EC2 启动工作流 |
| `demo-gcp-developer` | 开发人员 | `Demo GCP Group` | 生成 GKE Pod 重启工作流 |
| `demo-gcp-reviewer` | 审阅者 | `Demo GCP Group` | 发布 GKE Pod 重启工作流 |
| `demo-gcp-requester` | 请求者 | `Demo GCP Group` | 运行 GKE Pod 重启工作流 |
| `demo-azure-developer` | 开发人员 | `Demo Azure Group` | 生成密钥轮换工作流 |
| `demo-azure-reviewer` | 审阅者 | `Demo Azure Group` | 发布密钥轮换工作流 |
| `demo-azure-requester` | 请求者 | `Demo Azure Group` | 运行密钥轮换工作流 |
| `demo-approver-1`、`demo-approver-2` | 审批人 | `Demo Approvers`（全部三个标签） | 批准启动、Pod 重启或轮换 |

他们都不直接持有角色，而是从[用户组](../guides/users-and-groups.md#user-groups) `Demo Developers`、`Demo Reviewers`、`Demo Requesters` 和 `Demo Approvers` 继承。AWS、GCP 和 Azure 的三人组还各自属于第二个用户组 `Demo AWS Group`、`Demo GCP Group` 或 `Demo Azure Group`。这个用户组本身不授予任何角色，唯一的用途是持有对应的访问控制标签，使该三人组能看到该提供商带标签的记录，而其他人看不到。管理员（或超级管理员）除外，他们会完全[绕过访问控制标签](../guides/tags.md#access-control-tags)，无需为此加入任何用户组。`Demo Approvers` 本身直接带有 `AWS`、`GCP` 和 `Azure` 这三个访问控制标签，因为审批人不限于某一家提供商；也正因如此，无论请求来自三个演示工作流中的哪一个，都可以把它发给任一演示审批人。

## 试用 {#trying-it-out}

[操作演练](./walkthrough.mdx)会从头到尾走完任一示例：生成、发布、运行、批准、确认。整个过程只需以 `root` 登录一次，再依次[代理登录](../concepts/impersonation.md)到各个演示账户。用 `DEMO_PASSWORD` 分别登录各个账户也同样可行；上表说明了谁负责什么。

`Demo AWS Group`、`Demo GCP Group` 和 `Demo Azure Group` 都只能看到自己提供商的记录，因此 `demo-aws-developer` 打不开 `Demo GKE Pod Restart`，`demo-gcp-developer` 也打不开 `Demo Azure Key Vault Secret Rotation`。两个审批人账户都适用于所有示例，因为 `Demo Approvers` 直接带有全部三个访问控制标签。要真实运行 GKE 示例，需要把 `DEMO_GCP_CREDENTIALS_JSON` 设置为其身份可访问真实 GKE 集群的凭据；要真实执行轮换，`DEMO_AZURE_*` 服务主体需要拥有真实 Key Vault 中密钥的写入权限。

**没有 AWS 账户、GKE 集群或 Key Vault？** 不要发布，而是在工作流仍为 `草稿` 时运行它：作为开发人员，该提供商的开发人员账户（`demo-aws-developer`、`demo-gcp-developer` 或 `demo-azure-developer`）可以这样做，而且只有草稿运行的对话框才会提供租户的[工具模拟](../guides/tool-mocks.md)。在**模拟工具**下，勾选其中列出的预置桩（启动用的 `aws___call_aws` 或 `aws___run_script`，Pod 重启用的 `patch_k8s_resource` 或 `delete_k8s_resource`，轮换用的 `keyvault_secret_get` 和 `keyvault_secret_create`，以及 `request_approval`）；这样整个工作流都能运行到底，既不会连接真实的提供商，也不用等待人工处理。勾选轮换的模拟后，Key Vault 的密钥列表也是虚构的：从中选择 `db-password` 即可。

## 移除 {#removing-it}

设置 `DEMO_DATA=false`（或删除这一行）后，下次启动时会**再次移除这些记录**：该标志在两个方向上都是声明式的。

有两类内容会按设计保留：已被其他内容依赖的演示记录（例如基于演示技能构建的工作流）会保留并记入日志，而不会被删除；创建过记录的演示用户会被软删除，这样他们的名字在这些记录上仍能正常显示。
