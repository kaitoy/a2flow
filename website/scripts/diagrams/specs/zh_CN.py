"""Per-diagram replacement specs: English light HTML -> Simplified Chinese light HTML.

See :mod:`specs.common` for the entry format. Conventions the translations follow,
mirroring the Simplified Chinese prose:

* node names, edge labels, notes and legends are Simplified Chinese, with full-width
  punctuation in prose and half-width punctuation inside code;
* status values and UI button names use the exact wording of the Simplified Chinese GUI
  catalog (``frontend/src/i18n/messages/zh-CN.ts``), e.g. ``草稿``, ``运行中``, ``发布``,
  ``停用``, and core terms follow the glossary in ``frontend/README.md``;
* technical strings (``name/key``, ``POST /AGENT``, ``HTTPS``) stay English, so their 9px
  mono labels are left untouched;
* a translated edge label goes from 9px mono to 12px sans, so its background mask is
  resized with :func:`specs.common.mask` — budget 1em per full-width glyph, 0.3em per space,
  plus 8px;
* zone-title chips stay anchored to the zone's top-left corner rather than re-centred;
* each ``<desc>`` equals the image's alt text on the translated page.
"""

from specs.common import head, label, mask

SPECS: dict[str, list[tuple]] = {}


# ---------------------------------------------------------------- guides/secrets-usage
SPECS["guides/secrets-usage"] = head(
    "Where a secret entry is used", "密钥条目的使用位置",
    "Flowchart showing a secret's entry referenced either in an MCP server's headers and environment variables, or as an Agent Skill repository's auth password.",
    "流程图：密钥的条目要么在 MCP 服务器的标头和环境变量中被引用，要么作为代理技能仓库的认证密码被引用。",
) + [
    mask(423, 56, 54, 32),
    label("HEADERS", "标头"),
    label("Secret", "密钥"),
    label("Entry", "条目"),
    label("MCP server", "MCP 服务器"),
    label("headers + env vars", "标头 + 环境变量"),
    label("Agent Skill", "代理技能"),
    label("repo auth password", "仓库认证密码"),
    mask(430, 164, 40, 32),
    label("AUTH", "认证"),
]

# ---------------------------------------------------------------- guides/admin-ui-navigation
SPECS["guides/admin-ui-navigation"] = head(
    "Admin UI navigation", "管理界面导航",
    "Flowchart of the admin UI navigation model: the welcome page leads to a section list, which opens a create form or a detail page by clicking a name, and a breadcrumb on the detail page returns to the list.",
    "管理界面导航模型的流程图：从欢迎页进入分区列表，再从列表打开创建表单，或点击名称打开详情页；详情页上的面包屑导航可返回列表。",
) + [
    mask(492, 84, 40, 56),
    label("NAME", "点击名称"),
    mask(382, 180, 32, 32),
    label("ADD", "添加"),
    mask(476, 134, 72, 68),
    label("BREADCRUMB", "面包屑导航"),
    label("Welcome page", "欢迎页"),
    label("quick-action cards", "快捷操作卡片"),
    label("Section list", "分区列表"),
    label("e.g. Workflows", "例如 工作流"),
    label("Create form", "创建表单"),
    label("Detail page", "详情页"),
    label("titled by name", "以名称为标题"),
]

# ---------------------------------------------------------------- guides/agent-skills-lifecycle
SPECS["guides/agent-skills-lifecycle"] = head(
    "Agent Skill lifecycle", "代理技能的生命周期",
    "State machine showing an Agent Skill registered, cloning in the background, becoming ready or failed, pulling to retry from either state, and a ready skill generating a new workflow.",
    "代理技能的状态机图：注册后在后台克隆，然后变为“就绪”或“失败”；从任一状态都可以拉取重试；“就绪”的技能可以生成新工作流。",
) + [
    mask(376, 176, 40, 32),
    mask(394, 18, 52, 32),
    (">PULL</text>", ">拉取</text>", 2),
    mask(534, 176, 64, 32),
    label("GENERATE", "生成"),
    label("Cloning", "克隆中"),
    label("ready", "就绪"),
    label("failed", "失败"),
    label("Register", "注册"),
    label("returns immediately", "立即返回"),
    label("in the background", "在后台进行"),
    label("revision published", "修订版本已发布"),
    label("reason on record", "已记录原因"),
    label("New workflow", "新工作流"),
]

# ---------------------------------------------------------------- guides/approvals-sequence
SPECS["guides/approvals-sequence"] = head(
    "Requesting a human approval", "请求人工审批",
    "Sequence diagram of an approval request: the execution agent asks for approval, A2Flow notifies the approver and the run pauses, the approver decides, and A2Flow grants a certificate to each covered step and resumes the run.",
    "审批请求的时序图：执行代理请求审批，A2Flow 通知审批人，运行暂停；审批人作出决定后，A2Flow 向涵盖的每个步骤授予证书并恢复运行。",
) + [
    mask(221, 156, 118, 56),
    label("REQUEST APPROVAL", "请求审批"),
    mask(539, 216, 52, 32),
    label("NOTIFY", "通知"),
    mask(539, 276, 52, 32),
    label("DECIDE", "决定"),
    mask(238, 336, 84, 56),
    label("RUN RESUMES", "运行恢复"),
    label("the whole run", "整个运行"),
    label("pauses to wait", "暂停等待"),
    label("a certificate is", "为每个步骤"),
    label("granted per step", "授予一份证书"),
    label("Execution", "执行"),
    label("agent", "代理"),
    label("Approver", "审批人"),
    label("LEGEND", "图例"),
    label("Call", "调用"),
    label("Run resumes", "运行恢复"),
]

# ---------------------------------------------------------------- guides/notifications-routing
SPECS["guides/notifications-routing"] = head(
    "Where a notification goes", "通知的去向",
    "Flowchart showing a workflow event routing to the one concerned user, or every eligible approver-group member, and fanning out to the bell, the Notifications page, and email if it is enabled.",
    "流程图：工作流事件被路由到相关的那一位用户，或审批组中每位符合条件的成员，再分发到铃铛、通知页面，以及（如已启用）电子邮件。",
) + [
    label("Workflow event", "工作流事件"),
    label("Concerned user(s)", "相关用户"),
    label("or approver group", "或审批组"),
    label("Bell", "铃铛"),
    label("unread notifications", "未读通知"),
    label("Notifications page", "通知页面"),
    label("full history", "完整历史记录"),
    label("Email", "电子邮件"),
    label("if enabled", "如已启用"),
]

# ---------------------------------------------------------------- guides/tags-vocabulary
SPECS["guides/tags-vocabulary"] = head(
    "One vocabulary, seven registries", "一套词汇，七个注册表",
    "Flowchart showing one shared tag vocabulary per tenant applied to seven taggable registries: Secrets, MCP Servers, Agent Skills, Knowledge Bases, Workflows, Tool Mocks, and User Groups.",
    "流程图：每个租户共用一套标签词汇，应用于七个可加标签的注册表（密钥、MCP 服务器、代理技能、知识库、工作流、工具模拟和用户组）。",
    page_title="Tag vocabulary", svg_title="Tag vocabulary",
) + [
    label("Tag vocabulary", "标签词汇"),
    label("one per tenant", "每个租户一套"),
    label("Secrets", "密钥"),
    label("MCP Servers", "MCP 服务器"),
    label("Agent Skills", "代理技能"),
    label("Knowledge Bases", "知识库"),
    label("Workflows", "工作流"),
    label("Tool Mocks", "工具模拟"),
    label("User Groups", "用户组"),
]

# ---------------------------------------------------------------- guides/tool-mocks-decision
SPECS["guides/tool-mocks-decision"] = head(
    "Where a tool mock intercepts", "工具模拟的拦截位置",
    "Flowchart showing the agent calling a tool, checking whether it is mocked for this run, and either reaching the real MCP server or receiving the mock's next response with no server contacted.",
    "流程图：代理调用工具时，检查此次运行是否模拟了该工具，然后要么访问真实的 MCP 服务器，要么不联系任何服务器、直接收到模拟的下一个响应。",
) + [
    mask(468, 148, 28, 20),
    label("NO", "否"),
    mask(376, 236, 32, 20),
    label("YES", "是"),
    label("The agent", "代理"),
    label("calls a tool", "调用工具"),
    label("Mocked for", "此次运行"),
    label("this run?", "是否模拟？"),
    label("MCP server", "MCP 服务器"),
    label("real side effect", "真实副作用"),
    label("Mock's next response", "模拟的下一个响应"),
    label("no server contacted", "不联系任何服务器"),
    label("LEGEND", "图例"),
    label("Start / end", "开始 / 结束"),
    label("Decision", "判断"),
]

# ---------------------------------------------------------------- guides/users-groups-relationship
SPECS["guides/users-groups-relationship"] = head(
    "Tenant, users, and groups", "租户、用户和用户组",
    "Flowchart showing a tenant containing users and user groups, group membership granting a user its group, and both the user's own roles and its groups' roles feeding the user's effective roles.",
    "流程图：租户包含用户和用户组，用户通过成员身份加入用户组，用户自身的角色和所属用户组的角色共同构成该用户的有效角色。",
) + [
    mask(244, 166, 52, 56),
    label("MEMBER", "成员身份"),
    mask(420, 162, 44, 32),
    mask(244, 232, 44, 32),
    (">ROLES</text>", ">角色</text>", 2),
    label("Tenant", "租户"),
    label("org boundary", "组织边界"),
    label("User Group", "用户组"),
    label("named bundle", "命名集合"),
    label("User", "用户"),
    label("one account", "一个账户"),
    label("Effective roles", "有效角色"),
]

# ---------------------------------------------------------------- guides/workflow-executions-status
SPECS["guides/workflow-executions-status"] = head(
    "Run status", "运行状态",
    "State machine showing a run starting as running, moving to scheduled while it only waits on a time and back when it resumes, then settling completed once every task has ended with none failed, or failed once every task has ended with at least one failure.",
    "状态机图：运行以“运行中”开始，只等待某个时间时变为“已计划”，恢复后回到“运行中”；所有任务结束且无失败时定为“已完成”，所有任务结束且至少有一个失败时定为“失败”。",
) + [
    mask(244, 130, 72, 44),
    label("NONE FAILED", "无失败"),
    mask(404, 130, 72, 80),
    label("1+ FAILED", "至少一个失败"),
    label("WAITS ON A TIME", "等待某个时间"),
    label("RESUMES", "恢复"),
    label("running", "运行中"),
    label("scheduled", "已计划"),
    label("completed", "已完成"),
    label("failed", "失败"),
]

# ---------------------------------------------------------------- guides/workflow-executions-layout
SPECS["guides/workflow-executions-layout"] = head(
    "The workflow session screen", "工作流会话界面",
    "Flowchart showing the workflow session screen layout: the task timeline and the messages grouped by task sit side by side, and messages lead into the chat input.",
    "流程图，展示工作流会话界面的布局：任务时间线与按任务分组的消息并排显示，消息下方通向聊天输入框。",
) + [
    label("Task timeline", "任务时间线"),
    label("collapsible, left edge", "位于左侧，可折叠"),
    label("Messages", "消息"),
    label("grouped by task", "按任务分组"),
    label("Chat input", "聊天输入框"),
]

# ---------------------------------------------------------------- guides/workflows-lifecycle
SPECS["guides/workflows-lifecycle"] = head(
    "From skill to running workflow", "从技能到运行中的工作流",
    "Flowchart showing an Agent Skill generating a Workflow, refined into an adjusted draft, published, and run as a Workflow execution.",
    "流程图：由代理技能生成工作流，经调整形成草稿，发布后作为工作流执行运行。",
) + [
    label("Agent Skill", "代理技能"),
    (">Workflow</text>", ">工作流</text>", 2),
    label("AI-designed templates", "AI 设计的模板"),
    label("Adjusted draft", "调整后的草稿"),
    label("Published", "已发布"),
    label("design is frozen", "设计已冻结"),
    label("execution", "执行"),
]

# ---------------------------------------------------------------- guides/workflows-status
SPECS["guides/workflows-status"] = head(
    "Detailed workflow status", "工作流详细状态",
    "State machine of a workflow's detailed status: generating leads to draft or failed, failed can be rewritten back to draft, draft publishes to published, published and modified toggle on further edits and publishes, and either can be deactivated back to draft.",
    "工作流详细状态的状态机图：生成中变为草稿或失败，失败可重新编写后回到草稿，草稿发布后变为已发布，已发布和已修改随着进一步编辑和发布相互切换，两者都可以停用回到草稿。",
) + [
    mask(168, 162, 54, 32),
    label("FAILED", "失败"),
    mask(294, 154, 62, 32),
    label("BY HAND", "手动"),
    mask(663, 54, 54, 32),
    label("EDITED", "编辑"),
    mask(445, 70, 50, 32),
    mask(663, 116, 54, 32),
    (">PUBLISH</text>", ">发布</text>", 2),
    mask(445, 302, 70, 32),
    mask(579, 322, 70, 32),
    (">DEACTIVATE</text>", ">停用</text>", 2),
    label("generating", "生成中"),
    label("draft", "草稿"),
    label("published", "已发布"),
    label("modified", "已修改"),
    label("failed", "失败"),
]

# ---------------------------------------------------------------- guides/workflows-snapshot
SPECS["guides/workflows-snapshot"] = head(
    "Running a workflow makes a snapshot", "运行工作流时生成快照",
    "Flowchart showing the published Workflow and its chosen tool mocks copied by value onto a new Workflow execution snapshot, which opens a Workflow session.",
    "流程图：已发布的工作流及所选工具模拟按值复制到新的工作流执行快照上，该快照打开工作流会话。",
) + [
    mask(328, 126, 68, 56),
    label("COPIED", "按值复制"),
    mask(174, 126, 32, 32),
    label("RUN", "运行"),
    label("Workflow", "工作流"),
    label("published version", "已发布版本"),
    label("Chosen tool mocks", "所选工具模拟"),
    label("Workflow execution", "工作流执行"),
    label("the snapshot", "快照"),
    label("Workflow session", "工作流会话"),
]

# ---------------------------------------------------------------- guides/workflows-tool-binding
SPECS["guides/workflows-tool-binding"] = head(
    "Tool binding: design time vs run time", "工具绑定：设计时与运行时",
    "Flowchart showing a design-time tool binding copied at run onto the task, then checked at call time: if the tool is bound to an in-progress task the call goes through, otherwise it is refused with the tools that are allowed.",
    "流程图：设计时的工具绑定在运行时复制到任务上，然后在调用时检查：如果工具绑定到进行中的任务，调用通过；否则调用被拒绝，并列出允许的工具。",
) + [
    mask(253, 70, 54, 32),
    label("COPIED", "复制"),
    mask(752, 70, 36, 20),
    label("YES", "是"),
    mask(670, 177, 32, 20),
    label("NO", "否"),
    label("Design time", "设计时"),
    label("binds server + tool", "绑定服务器和工具"),
    label("Run time", "运行时"),
    label("task carries binding", "任务携带绑定"),
    label("Bound to a task", "是否绑定到"),
    label("in progress?", "进行中的任务？"),
    label("Goes through", "调用通过"),
    label("Refused", "已拒绝"),
    label("lists what's allowed", "列出允许的工具"),
]

# ---------------------------------------------------------------- concepts/authorization-effective-roles
SPECS["concepts/authorization-effective-roles"] = head(
    "Resolving effective roles", "解析有效角色",
    "Flowchart showing direct role grants on the user record and roles inherited from user groups both feeding a user's effective roles, the union used by every authorization check.",
    "流程图，显示用户记录上直接授予的角色和从用户组继承的角色共同构成用户的有效角色，所有授权检查都使用这一并集。",
) + [
    mask(254, 83, 52, 32, h=13),
    label("DIRECT", "直接"),
    mask(254, 178, 52, 44, h=13),
    label("GROUP", "用户组"),
    label("Direct grants", "直接授予"),
    label("on the user record", "用户记录上"),
    label("Group grants", "用户组授予"),
    label("inherited", "继承"),
    label("Effective roles", "有效角色"),
    label("Every auth", "所有"),
    label("check", "授权检查"),
]

# ---------------------------------------------------------------- concepts/authorization-session-matrix
SPECS["concepts/authorization-session-matrix"] = head(
    "Who can reach which session", "谁可以进入哪个会话",
    "Access matrix showing that Developers, the workflow's creator, and Super Admin reach a Design session, with Reviewers holding read-only access to it, while the run's initiator, its designated approvers, and Super Admin reach a Workflow session, with Admin holding read-only access to the Workflow session.",
    "访问矩阵，显示开发人员、工作流的创建者和超级管理员可以进入设计会话，审阅者对其拥有只读访问权限；运行的发起人、指定审批人和超级管理员可以进入工作流会话，管理员对工作流会话拥有只读访问权限。",
) + [
    label("Session", "会话"),
    label("vs. actor", "vs. 操作者"),
    label("Developer", "开发人员"),
    label("Reviewer", "审阅者"),
    (">any in tenant</text>", ">租户内任何人</text>", 2),
    label("Creator", "创建者"),
    label("workflow's createdBy", "工作流的创建者"),
    label("Initiator", "发起人"),
    label("started the run", "启动此次运行"),
    label("Approver", "审批人"),
    label("designated for it", "为其指定"),
    label("Admin", "管理员"),
    label("tenant admin", "租户管理员"),
    label("Super Admin", "超级管理员"),
    label("unrestricted", "不受限制"),
    label("Design session", "设计会话"),
    label("Workflow session", "工作流会话"),
    (">Yes</text>", ">完全访问</text>", 6),
    (">No access</text>", ">无权访问</text>", 7),
    (">Read only</text>", ">只读</text>", 3),
    (">can't drive it</text>", ">无法操作</text>", 2),
    label("LEGEND", "图例"),
    label("Full access", "完全访问"),
]

# ---------------------------------------------------------------- operations/deployment-topology
SPECS["operations/deployment-topology"] = head(
    "Deployment topology", "部署拓扑",
    "Architecture diagram showing the browser reaching a reverse proxy that routes API requests (/api/*) straight to the backend API and page requests to the frontend, and the backend API — which also runs the email worker — reaching durable state (database, skill store, secret key), external services (LLM provider, MCP servers), and an SMTP relay.",
    "架构图：浏览器访问反向代理，反向代理将 API 请求（/api/*）直接路由到后端 API，将页面请求路由到前端；后端 API 同时运行邮件工作进程，并访问持久状态（数据库、技能存储库、加密密钥）、外部服务（LLM 提供商、MCP 服务器）和 SMTP 中继。",
) + [
    ('<rect x="52" y="484" width="112" height="12"', '<rect x="52" y="483" width="64" height="14"'),
    ('<text x="108" y="493"', '<text x="84" y="493"'),
    label("DURABLE STATE", "持久状态"),
    ('<rect x="452" y="484" width="128" height="12"', '<rect x="452" y="483" width="64" height="14"'),
    ('<text x="516" y="493"', '<text x="484" y="493"'),
    label("EXTERNAL SERVICES", "外部服务"),
    label("Browser", "浏览器"),
    label("Reverse proxy", "反向代理"),
    label("load balancer", "负载均衡器"),
    label("Frontend", "前端"),
    label("chat UI", "聊天界面"),
    mask(690, 158, 52, 32, h=12),
    label("pages", "页面"),
    label("Backend API", "后端 API"),
    label("uvicorn + email worker", "uvicorn + 邮件工作进程"),
    label("Database", "数据库"),
    label("records", "记录"),
    label("Skill store", "技能存储库"),
    label("cloned repos", "克隆的仓库"),
    label("Secret key", "加密密钥"),
    label("encrypts", "用于加密"),
    label("LLM provider", "LLM 提供商"),
    label("MCP servers", "MCP 服务器"),
    label("SMTP relay", "SMTP 中继"),
    label("LEGEND", "图例"),
    label("A2Flow component", "A2Flow 组件"),
    label("External system", "外部系统"),
    label("Data store", "数据存储"),
]

# ---------------------------------------------------------------- operations/scaling-lock-race
SPECS["operations/scaling-lock-race"] = head(
    "One driver per conversation", "每个对话一个驱动方",
    "Sequence diagram of two replicas racing to run the same session: Replica 1 takes a PostgreSQL advisory lock and opens the stream for Client A, while Replica 2's later request for the same session is refused with 409 while the lock is held, and the lock is released only when Replica 1's stream ends.",
    "两个副本争相运行同一会话的时序图：副本 1 获取 PostgreSQL 咨询锁并为客户端 A 打开流；在锁被持有期间，副本 2 收到的同一会话的后续请求被以 409 拒绝；只有当副本 1 的流结束时，锁才会释放。",
) + [
    mask(401, 188, 78, 44, h=12),
    mask(621, 364, 78, 44, h=12),
    (">TAKE LOCK</text>", ">获取锁</text>", 2),
    mask(401, 232, 78, 44, h=12),
    label("ACQUIRED", "已获取"),
    mask(147, 276, 146, 84, h=12),
    label("SSE STREAM OPENS", "SSE 流打开"),
    mask(609, 408, 102, 80, h=12),
    label("HELD ELSEWHERE", "已被他处持有"),
    mask(833, 452, 94, 68, h=12),
    label("409 REFUSED", "409 拒绝"),
    mask(161, 496, 118, 44, h=12),
    label("STREAM ENDS", "流结束"),
    mask(401, 540, 78, 56, h=12),
    label("RELEASED", "锁已释放"),
    label("Client A", "客户端 A"),
    label("Replica 1", "副本 1"),
    label("Replica 2", "副本 2"),
    label("Client B", "客户端 B"),
    label("LEGEND", "图例"),
    label("Call", "调用"),
    label("Return", "返回"),
    label("Refused", "已拒绝"),
]

# ---------------------------------------------------------------- architecture/approvals-sequence
SPECS["architecture/approvals-sequence"] = head(
    "How an approval gate runs", "审批门禁如何运行",
    "Sequence diagram of an approval: the execution agent requests approval, A2Flow notifies the approver while the covered steps stay blocked, the approver decides, and A2Flow grants a certificate to each covered step as it starts and lets the run continue.",
    "审批的时序图：执行代理请求审批，A2Flow 通知审批人，同时被涵盖的步骤保持阻塞；审批人作出决定后，A2Flow 在每个被涵盖的步骤启动时向其授予证书，并让运行继续。",
) + [
    mask(222, 160, 116, 56, h=12),
    label("REQUEST APPROVAL", "请求审批"),
    mask(536, 220, 58, 32, h=12),
    label("NOTIFY", "通知"),
    mask(536, 280, 58, 32, h=12),
    label("DECIDE", "决定"),
    mask(222, 340, 116, 56, h=12),
    label("RUN CONTINUES", "运行继续"),
    label("the covered steps", "被涵盖的步骤"),
    label("stay blocked", "保持阻塞"),
    label("a certificate is", "为每个步骤"),
    label("granted per step", "授予一份证书"),
    label("Execution", "执行"),
    label("agent", "代理"),
    label("Approver", "审批人"),
    label("LEGEND", "图例"),
    label("Call", "调用"),
    label("Run continues", "运行继续"),
]

# ---------------------------------------------------------------- architecture/approvals-step-coverage
SPECS["architecture/approvals-step-coverage"] = head(
    "What one approval covers", "一个审批涵盖的范围",
    "Flowchart of a five-step task chain where Approval A covers the first three steps and Approval B takes over from the fourth step onward, showing that an approval covers its named step and everything after it up to the next approval.",
    "五步任务链的流程图：审批 A 涵盖前三个步骤，审批 B 从第四个步骤起接管，说明审批涵盖其指定的步骤及之后直到下一个审批的所有步骤。",
) + [
    label("Approval A", "审批 A"),
    label("Approval B", "审批 B"),
    (">gate</text>", ">门禁</text>", 2),
    label("Ask for a go-ahead", "请求批准"),
    label("Launch instance", "启动实例"),
    label("Tag instance", "为实例加标签"),
    label("Ask again", "再次请求"),
    label("Delete snapshot", "删除快照"),
    label("APPROVAL A COVERS", "审批 A 涵盖"),
    label("APPROVAL B COVERS", "审批 B 涵盖"),
    label("LEGEND", "图例"),
    label("Approval gate", "审批门禁"),
]

# ---------------------------------------------------------------- architecture/overview-lifecycle
SPECS["architecture/overview-lifecycle"] = head(
    "How a workflow moves", "工作流如何流转",
    "Flowchart showing an Agent Skill generated into a Workflow, run as a Workflow execution inside a Workflow session, whose Tasks request human approval or call an MCP tool through the MCP gateway to reach an MCP server.",
    "流程图，显示代理技能生成工作流，工作流以工作流执行的形式在工作流会话中运行，其任务请求人工审批，或通过 MCP 网关调用 MCP 工具以访问 MCP 服务器。",
) + [
    ('<rect x="508" y="118" width="90" height="12"', '<rect x="508" y="117" width="40" height="14"'),
    label("GENERATE", "生成"),
    ('<rect x="508" y="222" width="100" height="12"', '<rect x="508" y="221" width="76" height="14"'),
    label("PUBLISH/RUN", "发布并运行"),
    mask(315, 520, 120, 80, h=12),
    label("NEEDS A PERSON", "需要人工处理"),
    mask(565, 520, 120, 56, h=12),
    label("NEEDS A TOOL", "需要工具"),
    mask(460, 560, 80, 32, h=12),
    label("CERTIFICATE", "证书"),
    label("Agent Skill", "代理技能"),
    label("a Git repository", "Git 仓库"),
    label("Workflow", "工作流"),
    label("templates + tool bindings", "模板 + 工具绑定"),
    label("Workflow execution", "工作流执行"),
    label("a snapshot of the design", "设计的快照"),
    label("Workflow session", "工作流会话"),
    label("the run's shared chat", "运行共享的聊天"),
    label("Tasks", "任务"),
    label("one at a time", "一次一个"),
    label("Approval gate", "审批门禁"),
    label("MCP gateway", "MCP 网关"),
    label("MCP server", "MCP 服务器"),
]

# ---------------------------------------------------------------- architecture/secrets-resolution
SPECS["architecture/secrets-resolution"] = head(
    "How a secret reference resolves", "密钥引用如何解析",
    "Flowchart showing a name/key secret reference branching by storage type: local secrets are decrypted from the stored value, Vault secrets are read live, and both feed an MCP server connection or a skill repository clone.",
    "流程图，显示密钥引用按类型分支：本地类型解密已存储的值，Vault 类型从 Vault 实时读取，两者都用于 MCP 服务器连接或技能仓库克隆。",
    page_title="Secret reference resolution", svg_title="Secret reference resolution",
) + [
    mask(305, 160, 48, 32, h=12),
    label("LOCAL", "本地"),
    label("A reference", "引用"),
    label("Which type?", "哪种类型？"),
    label("Decrypt the", "解密"),
    label("stored value", "已存储的值"),
    label("Read it live", "从 Vault"),
    label("from Vault", "实时读取"),
    label("MCP server connection", "MCP 服务器连接"),
    label("or a skill repository clone", "或技能仓库克隆"),
]

_POLICY_MASKS = [
    mask(612, 140, 56, 44, h=12),
    label("DENIED", "已拒绝"),
    mask(508, 234, 64, 44, h=12),
    label("ALLOWED", "已允许"),
    mask(698, 300, 32, 20, h=12),
    label("YES", "是"),
    mask(508, 390, 28, 20, h=12),
    label("NO", "否"),
    label("calls a tool", "调用工具"),
    label("Policy chain", "策略链"),
    label("Refused", "已拒绝"),
    label("Mocked for", "此次运行"),
    label("this run?", "是否模拟？"),
    label("Mock's response", "模拟的响应"),
    label("no server contacted", "不联系服务器"),
    label("MCP server", "MCP 服务器"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-policy-chain
SPECS["architecture/mcp-gateway-and-proxy-policy-chain"] = head(
    "The policy chain", "策略链",
    "Flowchart showing how the MCP gateway decides a tool call: a policy chain either refuses it or allows it, an allowed call is either answered from a mock or goes through credential injection and the MCP proxy to the real MCP server, and both the refusal and the real call produce an audit record.",
    "流程图，显示策略链如何裁决工具调用：被拒绝的调用会被驳回，并告知允许的内容；被允许的调用由模拟应答，或经过凭据注入和 MCP 代理服务器到达 MCP 服务器；拒绝和真实调用都会产生审计记录。",
    page_title="Policy chain", svg_title="Policy chain",
) + _POLICY_MASKS + [
    label("Execution agent", "执行代理"),
    label("lists what is allowed", "列出允许的内容"),
    label("Credential injection", "凭据注入"),
    label("MCP proxy", "MCP 代理服务器"),
    label("Audit record", "审计记录"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-tool-mocks
SPECS["architecture/mcp-gateway-and-proxy-tool-mocks"] = head(
    "Where the mock sits", "模拟所处的位置",
    "Flowchart showing that a tool mock is consulted only after the same policy chain a production call faces: a denied call is refused exactly as in production, and an allowed call is answered from a mock's next response or the real MCP server.",
    "流程图，显示工具模拟只在经过与生产调用相同的策略链之后才被查询：被拒绝的调用与生产环境一样被拒绝，被允许的调用由模拟的下一个响应或真实的 MCP 服务器应答。",
) + _POLICY_MASKS + [
    label("The agent", "代理"),
    label("exactly as production", "与生产环境完全相同"),
    label("the real side effect", "真实副作用"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-trust-boundary
SPECS["architecture/mcp-gateway-and-proxy-trust-boundary"] = head(
    "Crossing the trust boundary", "跨越信任边界",
    "Architecture diagram showing the MCP gateway, which decides whether a call is allowed, mocked, and which credentials it needs, handing exactly one authorized call across a trust boundary into the MCP proxy, which starts or connects to the real MCP server.",
    "架构图，显示 MCP 网关决定调用是否被允许、是否被模拟以及需要哪些凭据，然后把恰好一个已授权的调用跨越信任边界交给 MCP 代理服务器，由后者启动或连接真实的 MCP 服务器。",
) + [
    ('<rect x="52" y="64" width="112" height="12"', '<rect x="52" y="63" width="64" height="14"'),
    ('<text x="108" y="73"', '<text x="84" y="73"'),
    label("RUNS THE AGENT", "运行代理"),
    ('<rect x="412" y="64" width="64" height="12"', '<rect x="412" y="63" width="40" height="14"'),
    ('<text x="444" y="73"', '<text x="432" y="73"'),
    label("SANDBOX", "沙箱"),
    mask(328, 104, 84, 56, h=12),
    label("AUTHORIZED", "已授权"),
    label("MCP gateway", "MCP 网关"),
    label("allowed, mocked, credentials", "允许、模拟、凭据"),
    label("MCP proxy", "MCP 代理服务器"),
    label("starts or connects", "启动或连接"),
    label("MCP server", "MCP 服务器"),
    label("outside our control", "不受我方控制"),
    label("LEGEND", "图例"),
    label("Trust boundary", "信任边界"),
]

# ---------------------------------------------------------------- architecture/sessions-turn-flow
SPECS["architecture/sessions-turn-flow"] = head(
    "How a turn runs", "一个轮次如何运行",
    "Sequence diagram of one chat turn: the user's message travels from Frontend to Backend to the Model, the model's streamed reply and any render_a2ui surface flow back, and the user's filled-in surface makes the same round trip again.",
    "一个聊天轮次的时序图：用户的消息从前端传到后端再传到模型，模型的流式回复和任何 render_a2ui 界面传回，用户填写完的界面再走一遍同样的往返。",
) + [
    mask(190, 160, 100, 56, h=12),
    label("WRITES MESSAGE", "编写消息"),
    mask(396, 200, 144, 104, h=12),
    label("MESSAGE + TOOL SCHEMA", "消息 + 工具架构"),
    mask(640, 240, 104, 68, h=12),
    label("BRIDGE TO AGENT", "桥接到代理"),
    mask(632, 280, 120, 104, h=12),
    label("TEXT + TOOL CALLS", "文本 + 工具调用"),
    mask(414, 320, 108, 80, h=12),
    label("STREAMED ONWARD", "继续流式传输"),
    mask(192, 360, 96, 56, h=12),
    label("DRAWS SURFACE", "绘制界面"),
    mask(186, 400, 108, 68, h=12),
    label("FILLS + SUBMITS", "填写并提交"),
    mask(414, 440, 108, 80, h=12),
    label("FULL DATA MODEL", "完整数据模型"),
    mask(638, 480, 108, 68, h=12),
    label("MATCHED TO CALL", "与调用匹配"),
    mask(412, 520, 112, 56, h=12),
    label("RESPONDS TO USER", "响应用户"),
    label("a render_a2ui call is", "render_a2ui 调用"),
    label("forwarded, never executed", "只转发，不执行"),
    label("User", "用户"),
    label("Browser", "浏览器"),
    label("Frontend", "前端"),
    label("chat UI", "聊天界面"),
    label("Backend", "后端"),
    label("Model", "模型"),
    label("LLM provider", "LLM 提供商"),
    label("LEGEND", "图例"),
    label("Call", "调用"),
    label("Streamed return", "流式返回"),
    label("Response to user", "对用户的响应"),
]

# ---------------------------------------------------------------- architecture/workflow-design-status
SPECS["architecture/workflow-design-status"] = head(
    "Workflow status lifecycle", "工作流状态生命周期",
    "State machine showing a workflow moving from a published Agent Skill through generating to draft or failed, then from draft through published and modified, with publish looping back from modified.",
    "状态机，显示工作流从已发布的代理技能开始，经过生成中到达草稿或失败，再从草稿进入已发布和已修改，并可从已修改通过发布返回已发布。",
) + [
    mask(196, 96, 48, 32, h=12),
    label("GENERATE", "生成"),
    mask(366, 180, 56, 44, h=12),
    label("NO STEPS", "无步骤"),
    mask(568, 180, 48, 32, h=12),
    label("REVISED", "修订"),
    mask(596, 96, 48, 32, h=12),
    mask(676, 180, 48, 32, h=12),
    label("EDITED", "编辑"),
    mask(736, 180, 48, 32, h=12),
    (">PUBLISH</text>", ">发布</text>", 2),
    label("generating", "生成中"),
    label("draft", "草稿"),
    label("published", "已发布"),
    label("failed", "失败"),
    label("modified", "已修改"),
    label("Agent Skill", "代理技能"),
    label("published revision", "已发布的修订版本"),
    label("design run in progress", "设计运行进行中"),
    label("templates + bindings", "模板 + 绑定"),
    label("design is frozen", "设计已冻结"),
    label("reason on record", "已记录原因"),
    label("runs use published", "运行使用已发布版本"),
    label("LEGEND", "图例"),
    label("Precondition", "前提条件"),
    label("Status", "状态"),
    label("Live version", "实际运行的版本"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-snapshot
SPECS["architecture/workflow-execution-snapshot"] = head(
    "Running a workflow copies its design", "运行工作流会复制其设计",
    "Flowchart showing a published workflow and its chosen tool mocks copied by value onto a new workflow execution snapshot, which opens a workflow session containing tasks that all start pending.",
    "流程图，显示已发布的工作流及所选的工具模拟被复制到新的工作流执行快照上，随后打开工作流会话，开始时所有任务都处于待处理状态。",
    page_title="Running a workflow", svg_title="Running a workflow copies its design",
) + [
    mask(404, 136, 32, 32, h=12),
    label("RUN", "运行"),
    mask(556, 136, 96, 56, h=12),
    label("COPIED BY VALUE", "按值复制"),
    label("Workflow", "工作流"),
    label("published version", "已发布版本"),
    label("Chosen tool mocks", "所选工具模拟"),
    label("test runs only", "仅限测试运行"),
    label("Workflow execution", "工作流执行"),
    label("the snapshot", "快照"),
    label("Workflow session", "工作流会话"),
    label("the run's chat", "运行的聊天"),
    label("Tasks", "任务"),
    label("all pending at the start", "开始时全部待处理"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-run-loop
SPECS["architecture/workflow-execution-run-loop"] = head(
    "How the run advances", "运行如何推进",
    "Flowchart showing the task-advancement loop: list tasks, pick one whose dependencies have completed, mark it in progress, do the work, mark it ended, and repeat until every task has ended and the run settles.",
    "运行推进循环的流程图：列出运行的任务，选取依赖已完成的任务，将其标记为进行中，完成工作，再标记为已完成、失败或已跳过，然后循环，直到所有任务都结束后运行定局。",
) + [
    mask(484, 222, 32, 20, h=12),
    label("YES", "有"),
    mask(644, 154, 24, 20, h=12),
    label("NO", "无"),
    label("List the run's tasks", "列出运行的任务"),
    label("A pending task whose", "有依赖已完成的"),
    label("deps have completed?", "待处理任务吗？"),
    label("Mark it in_progress", "标记为进行中"),
    label("Do the work", "完成工作"),
    label("tools, approvals, conversation", "工具、审批、对话"),
    label("Mark it completed,", "标记为已完成、"),
    label("failed, or skipped", "失败或已跳过"),
    label("Run settles", "运行定局"),
    label("every task has ended", "所有任务都已结束"),
    label("LEGEND", "图例"),
    label("Step (rectangle)", "步骤（矩形）"),
    label("Decision (diamond)", "判断（菱形）"),
    label("Loop exit (oval)", "循环出口（椭圆）"),
    label("Continues the loop", "继续循环"),
]
