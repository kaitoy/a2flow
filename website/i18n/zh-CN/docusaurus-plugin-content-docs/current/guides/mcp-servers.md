---
title: MCP 服务器
sidebar_position: 7
---

# MCP 服务器

[MCP](https://modelcontextprotocol.io/) 服务器提供代理可以调用的工具。这里就是它们的注册表：在此注册服务器后，其工具即可绑定到工作流的任务模板，详见[任务的 MCP 工具](./workflows.md#mcp-tools-for-tasks)。

在管理侧边栏中打开 **MCP 服务器** 即可管理注册表。每条记录都有唯一的**名称**、可选的**描述**、[标签](./tags.md)，以及决定表单其余内容的**传输方式**。

## 传输方式 {#transports}

| 传输方式 | 字段 | 说明 |
|---|---|---|
| **Streamable HTTP**（默认） | **URL**、**HTTP 标头** | 远程服务器。每次请求都会发送标头，通常是 `Authorization: Bearer …`。不支持仅提供 SSE 的服务器。 |
| **stdio** | **命令**、**参数**、**环境变量** | 作为后端子进程启动的服务器，例如向 `npx` 传入 `["-y", "@modelcontextprotocol/server-everything"]`。`npx` 和 `uvx` 均可使用。 |
| **脚本** | **语言**、**来源**、**软件包**、**环境变量** | 您自己编写的 Python 或 JavaScript 代码。其中每个公开函数都会成为一个工具，详见[编写脚本](#writing-a-script)。 |

切换现有服务器的传输方式时，会清除原传输方式的字段。混用多种形式的记录（stdio 服务器带 URL、远程服务器带命令，或者这两者带源代码）会被拒绝。

⚠️ **注册 stdio 服务器意味着在后端容器内运行所选命令**，运行身份是容器的非特权用户。与其他 MCP 服务器写操作一样，这需要开发人员角色。参数以列表形式传给进程，绝不经过 shell；子进程只继承一小组安全的环境变量以及您配置的变量，看不到后端自身的 API 密钥和数据库 URL。

## 编写脚本 {#writing-a-script}

脚本服务器无需发布软件包，就能把您编写的函数变成工具。将**传输方式**选为**脚本**，选择**语言**，然后把代码粘贴到**来源**中。

**来源**是一个代码编辑器。它会按所选**语言**为代码着色、标注行号，并用 **Tab** 键缩进；要用 **Tab** 键移到下一个字段，请先按 **Esc** 键。输入时，编辑器会在出问题的位置画下划线，将鼠标悬停在下划线上即可查看问题所在。

| 下划线 | 含义 | 示例 |
|---|---|---|
| 红色波浪线 | 语法错误，脚本无法运行 | 括号未闭合、关键字拼写错误 |
| 琥珀色波浪线 | 可能有误 | 没有任何函数会成为工具；Python 函数缺少文档字符串，或参数缺少类型注解；**软件包**为空却从标准库以外导入；JavaScript 函数缺少 `description` |
| 强调色波浪线 | 提示 | JavaScript 函数缺少 `inputSchema` |

下划线只是建议，绝不会阻止保存；保存时的检查见下文。

| | Python | JavaScript |
|---|---|---|
| 会成为工具的函数 | 在顶层定义且名称不以 `_` 开头的每个函数。导入的函数不会公开。 | 名称不以 `_` 开头的每个导出函数（`export function`、`export async function`）。默认导出不会公开。 |
| 工具名称 | 函数名 | 导出名 |
| 描述 | 文档字符串 | 函数的 `description` 属性 |
| 参数 | 从类型注解读取：`str`、`int`、`float`、`bool`、`list`、`dict`、`Literal[...]` 和 `X \| None`。其他类型的参数或没有类型注解的参数接受任意值。 | 函数的 `inputSchema` 属性，是一个 JSON Schema。没有该属性时，工具接受任意参数。 |
| 工具的调用方式 | 按名称传递参数 | 传入一个包含所有参数的对象 |
| 代理得到的结果 | 返回值：字符串原样返回，其他内容转为 JSON | 返回值：字符串原样返回，其他内容转为 JSON |

```python
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

```js
export function add({ a, b }) {
  return a + b;
}
add.description = "Add two numbers.";
add.inputSchema = {
  type: "object",
  properties: { a: { type: "number" }, b: { type: "number" } },
  required: ["a", "b"],
};
```

两种语言都遵循以下规则：

- 标准库始终可用，即 Python 自带的模块或 Node.js 内置的 `node:` 模块。其他一切都必须列在[软件包](#adding-packages)中。
- 函数抛出的错误会以工具调用失败的形式连同错误消息传给代理。
- `print()` 或 `console.log()` 的输出写入服务器日志，不会传给代理。
- **环境变量**可通过 `os.environ["NAME"]` 或 `process.env.NAME` 读取，并可使用[不在记录中保存凭据](#keeping-credentials-out-of-the-record)一节介绍的占位符。
- **来源**最多 30,000 个字符。
- Python 代码有语法错误时，保存会被拒绝并提示行号。JavaScript 在保存时不做检查，请在保存前先[测试](#testing-a-script)，以发现无法加载的脚本。
- 加载失败的脚本（软件包无法安装、语法错误，或顶层抛出错误）仍会启动。对它的每次工具调用都会失败，并返回导致加载中止的错误；[检查其工具](#checking-a-servers-tools)时，该服务器会显示为不可用。

⚠️ 脚本与 stdio 服务器在同一位置运行，受相同的限制。

### 添加软件包 {#adding-packages}

与其他服务通信的脚本通常需要该服务的客户端库，例如 AWS 的 `boto3`。在**软件包**中逐行列出，每行一个，然后照常在**来源**中导入。

| 语言 | 软件包写法 | 示例 |
|---|---|---|
| Python | PyPI 上的名称，可附带版本 | `boto3`、`boto3==1.40.0`、`requests>=2.32` |
| JavaScript | npm 注册表中的名称，可附带 `@version` | `is-number`、`@aws-sdk/client-s3@3` |

```python
import boto3


def list_buckets() -> list[str]:
    """List the S3 buckets the configured credentials can see."""
    return [b["Name"] for b in boto3.client("s3").list_buckets()["Buckets"]]
```

- 软件包在脚本首次以该列表启动时安装，可能需要一些时间；之后的启动会复用已安装的副本。列出完全相同软件包的脚本共享同一份副本。
- 无法安装的软件包（名称拼写错误、版本不存在）会使脚本无法加载。[加载工具](#testing-a-script)会显示安装程序的错误。
- 一个服务器最多 20 个软件包，每个不超过 200 个字符，且须以字母、数字或 `@` 开头。
- 安装时，脚本运行环境必须能够访问软件包注册表。要改从私有索引安装，请在**环境变量**中设置安装程序自身的变量：Python 用 `UV_INDEX_URL`，JavaScript 用 `NPM_CONFIG_REGISTRY`。

## 测试脚本 {#testing-a-script}

**环境变量**下方的**测试运行**面板会按表单当前内容运行脚本，不做保存。可借此在代理尝试使用之前，发现无法加载的脚本。

1. 点击**加载工具**。脚本会以表单中当前的**来源**、**软件包**和**环境变量**启动。
2. 从**工具**中选择一个工具。**参数**中会填入该工具声明的所有参数，值均为 `null`。
3. 编辑**参数**（一个 JSON 对象），然后点击**运行**。

| 您看到的内容 | 含义 |
|---|---|
| 工具列表 | 脚本已加载；这些就是它将公开的工具 |
| 工具列表的位置显示红色文字 | 脚本无法加载。文字内容是导致加载中止的错误 |
| **此脚本未公开任何工具。** | 脚本已加载，但没有函数会成为工具 |
| **输出**中显示工具的输出 | 调用成功 |
| **输出**中显示红色文字 | 工具抛出了错误；文字内容是错误消息 |
| **参数必须是 JSON 对象。** 或 **JSON 无效：…** | **参数**不是 JSON 对象；未运行任何内容 |

**环境变量**中的占位符会像已保存的服务器一样展开，因此测试运行会用相同的凭据访问相同的服务。测试运行是真实调用：工具执行的任何操作都会实际发生。

## 不在记录中保存凭据 {#keeping-credentials-out-of-the-record}

⚠️ 直接填写的标头值和环境变量值会**以明文**存储，并在详情页上显示。不要直接输入凭据，请引用已注册[密钥](./secrets.md)中的一个条目：

| 占位符 | 适用位置 | 示例 |
|---|---|---|
| `${secret:name/key}` | 任意标头值或环境变量值 | `Authorization: Bearer ${secret:github/token}`<br/>`AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}` |
| `${gcp-token:name/key}` | 与 `${secret:…}` 相同，用于保存 Google Cloud 凭据 JSON 的条目 | `Authorization: Bearer ${gcp-token:gcp-credentials/GOOGLE_CREDENTIALS_JSON}` |
| `${env:NAME}` | **参数**中的条目，指明此服务器自身的某个环境变量 | `--token ${env:API_KEY}` |

占位符仅在连接时展开，因此凭据绝不会出现在存储的记录中。

`${env:NAME}` 在该环境变量自身的 `${secret:…}` 之后展开，这样就能将来自密钥的值复用为命令行标志，适用于要求以参数形式传入、而不是从进程环境中读取的启动器。`NAME` 必须是**环境变量**中的键；引用不存在的键（包括移除该键后遗留的引用）会在保存时被拒绝。

### Google Cloud MCP 服务器 {#google-cloud-mcp-servers}

Google 托管的 MCP 服务器（例如 GKE 的）不接受 API 密钥。每个请求都必须携带 Google Cloud 身份的 OAuth 2.0 访问令牌，而令牌的有效期只有一小时，因此也无法粘贴到密钥中保存。`${gcp-token:name/key}` 解决了这个问题：它展开后不是条目的值，而是**用该值生成的新访问令牌**，并在到期时自动刷新。条目中保存凭据 JSON，有以下两种形式：

| 凭据 | 获取方式 | 令牌范围 |
|---|---|---|
| **服务账号密钥** | 创建服务账号，授予 **MCP Tool User** 以及其工具所需的权限，然后下载 JSON 密钥 | `cloud-platform` |
| **OAuth 客户端 ID 和密钥** | 创建 OAuth 客户端（桌面应用）并下载其 JSON，然后在您自己的机器上运行一次 `gcloud auth application-default login --client-id-file=<该 JSON> --scopes=https://www.googleapis.com/auth/cloud-platform` 并登录。粘贴生成的 `application_default_credentials.json` 的内容 | 您同意的范围 |

无论哪种方式，都请将整个 JSON 作为[密钥](./secrets.md)的一个条目粘贴，并按上面的示例在服务器的 `Authorization` 标头中引用。无论谁启动工作流，每次工具调用都以这一个身份运行。格式错误的凭据或 Google 不再接受的凭据，会像悬空的 `${secret:…}` 引用一样导致连接失败。

## 从 MCP 注册表注册 {#registering-from-the-mcp-registry}

列表页的**浏览注册表**按钮会打开一个搜索对话框，数据来自官方 [MCP 注册表](https://registry.modelcontextprotocol.io/)。

1. 按名称搜索。结果只列出 A2Flow 能注册的服务器：具有 Streamable HTTP 端点的服务器，以及以 npm 或 PyPI 包发布、可通过 stdio 启动的服务器。
2. 选择一个。创建表单随即打开，并已预填连接信息以及该服务器所需的标头键或环境变量键。
3. 填写密钥值并保存。

从软件包到启动命令的映射只是尽力而为，请在保存前检查。A2Flow 搜索的注册表可在[配置参考](../operations/configuration.md#mcp-tools-and-approvals)中改为其他地址。

## 检查服务器的工具 {#checking-a-servers-tools}

任务模板表单会向服务器查询其提供的工具（名称、描述和输入架构），但只查询您选中的那一台服务器，绝不会一次查询整个注册表。无法连接或无法启动的服务器会在工具列表的位置说明这一情况。

## 删除服务器 {#deleting-a-server}

只要还有任务或任务模板绑定了服务器的某个工具，就无法删除该服务器。请先移除这些绑定。
