---
title: 密钥
sidebar_position: 9
---

# 密钥

密钥是**一组带名称的键值条目**，形式与 [HashiCorp Vault 的 KV 引擎](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)相同：一个路径保存一个由键到值的映射。相互关联的凭据（例如 AWS 访问密钥 ID 及其秘密访问密钥）应作为两个条目放在同一个密钥中，而不是分成两个密钥。

在管理侧边栏中打开**密钥**即可进行管理。每条记录都有**名称**、可选的**描述**、[标签](./tags.md)和类型。

## 密钥的使用位置 {#where-a-secret-is-used}

![流程图：密钥的条目要么在 MCP 服务器的标头和环境变量中被引用，要么作为代理技能仓库的认证密码被引用。](./img/secrets-usage.svg#gh-light-mode-only)
![流程图：密钥的条目要么在 MCP 服务器的标头和环境变量中被引用，要么作为代理技能仓库的认证密码被引用。](./img/secrets-usage-dark.svg#gh-dark-mode-only)

- **[MCP 服务器](./mcp-servers.md)**：任何标头值或环境变量值都可以嵌入 `${secret:name/key}`，在连接时展开。
- **[代理技能](./agent-skills.md)**：技能的**认证密码**是对某个条目的引用，从下拉列表中选择，而不是手动输入。

单个条目始终以 **`name/key`** 表示。即使密钥只有一个条目，键也是必需的，因为单独的名称标识的是映射，而不是值。因此不带键的 `${secret:name}` 会解析失败，而不会作为字面字符串传递。

## 两种类型 {#the-two-types}

| | **本地（已加密）** | **HashiCorp Vault** |
|---|---|---|
| **存储内容** | 条目本身，每个值都经过加密 | 仅 KV v2 引用，即 **Vault 挂载点**和 **Vault 路径** |
| **值的来源** | 加密存储 | 每次解析时实时从 Vault 读取 |
| **详情页显示** | 所有已存储的键，值为空 | 挂载点和路径 |
| **编辑条目** | 值留空则保留，重新输入则替换，移除该行则删除条目 | 在 Vault 中进行 |

两种类型的值都**绝不会返回**，无论明文还是密文，所以本地类型的详情页只显示键、值留空。只有键是可读的，因此选择器可以列出它们：本地密钥的键来自存储的映射，Vault 密钥的键则在当时从 Vault 读取。

Vault 密钥从**其所属租户的** Vault 读取，由租户管理员在[租户设置](./users-and-groups.md#tenant-vault)中连接。没有自有 Vault 的租户使用[其自有凭据](./users-and-groups.md#global-vault-credential)从[全局 Vault](./system-settings.md#global-vault) 读取，该凭据的 Vault 策略决定可读取的内容。两者都没有时，Vault 类型的密钥无法解析。本地密钥所用的加密密钥只需设置一次，详见[配置参考](../operations/configuration.md#secret-management)。

## 重命名和删除 {#renaming-and-deleting}

密钥**按名称**引用，并在使用时才解析。重命名或删除仍被引用的密钥不会在编辑时失败，而是在下次使用时失败，并指明找不到的密钥。引用已失效的[代理技能](./agent-skills.md)会在下次拉取时把原因记录到自己的记录中。

不过，保存引用时会做检查。保存标头或环境变量中指定了密钥的 MCP 服务器、对脚本执行**测试运行**，或保存技能的**认证密码**时，该密钥必须存在，并且是您能打开的。被[访问控制标签](./tags.md#access-control-tags)向您隐藏的密钥，会与不存在的密钥一样被拒绝。编辑已引用此类密钥的记录时也是如此，即使您只更改了其他字段。
