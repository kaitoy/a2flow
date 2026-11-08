"""Per-diagram replacement specs: English light HTML -> Korean light HTML.

See :mod:`specs.common` for the entry format. Conventions the translations follow,
mirroring the Korean prose:

* node names, edge labels, notes and legends are Korean, written as short noun phrases;
* status values and UI button names use the exact wording of the Korean GUI catalog
  (``frontend/src/i18n/messages/ko.ts``), e.g. ``초안``, ``실행 중``, ``게시``, ``비활성화``;
* technical strings (``name/key``, ``POST /AGENT``, ``HTTPS``) stay English, so their 9px
  mono labels are left untouched;
* a translated edge label goes from 9px mono to 12px sans, so its background mask is
  resized with :func:`specs.common.mask` — budget 1em per full-width glyph, 0.3em per
  space, plus 8px;
* zone-title chips stay anchored to the zone's top-left corner rather than re-centred;
* each ``<desc>`` equals the alt text of the image on the translated page.
"""

from specs.common import head, label, mask

SPECS: dict[str, list[tuple]] = {}


# ---------------------------------------------------------------- guides/secrets-usage
SPECS["guides/secrets-usage"] = head(
    "Where a secret entry is used", "시크릿 항목이 사용되는 곳",
    "Flowchart showing a secret's entry referenced either in an MCP server's headers and environment variables, or as an Agent Skill repository's auth password.",
    "시크릿 항목이 MCP 서버의 헤더와 환경 변수에서 참조되거나 에이전트 스킬 저장소의 인증 비밀번호로 참조되는 것을 보여 주는 순서도.",
) + [
    mask(423, 56, 54, 32),
    label("HEADERS", "헤더"),
    label("Secret", "시크릿"),
    label("Entry", "항목"),
    label("MCP server", "MCP 서버"),
    label("headers + env vars", "헤더 + 환경 변수"),
    label("Agent Skill", "에이전트 스킬"),
    label("repo auth password", "저장소 인증 비밀번호"),
    mask(430, 164, 40, 32),
    label("AUTH", "인증"),
]

# ---------------------------------------------------------------- guides/admin-ui-navigation
SPECS["guides/admin-ui-navigation"] = head(
    "Admin UI navigation", "관리 UI 탐색",
    "Flowchart of the admin UI navigation model: the welcome page leads to a section list, which opens a create form or a detail page by clicking a name, and a breadcrumb on the detail page returns to the list.",
    "관리 UI 탐색 모델의 순서도. 환영 페이지에서 섹션 목록으로 이동하고, 목록에서 만들기 양식을 열거나 이름을 클릭해 상세 페이지를 열며, 상세 페이지의 이동 경로로 목록에 돌아갑니다.",
) + [
    mask(492, 84, 40, 60),
    label("NAME", "이름 클릭"),
    mask(382, 180, 32, 44),
    label("ADD", "만들기"),
    mask(476, 134, 72, 60),
    label("BREADCRUMB", "이동 경로"),
    label("Welcome page", "환영 페이지"),
    label("quick-action cards", "바로 가기 카드"),
    label("Section list", "섹션 목록"),
    label("e.g. Workflows", "예: 워크플로"),
    label("Create form", "만들기 양식"),
    label("Detail page", "상세 페이지"),
    label("titled by name", "레코드 이름이 제목"),
]

# ---------------------------------------------------------------- guides/agent-skills-lifecycle
SPECS["guides/agent-skills-lifecycle"] = head(
    "Agent Skill lifecycle", "에이전트 스킬 수명 주기",
    "State machine showing an Agent Skill registered, cloning in the background, becoming ready or failed, pulling to retry from either state, and a ready skill generating a new workflow.",
    "에이전트 스킬의 상태 머신. 등록된 스킬은 백그라운드에서 복제되어 준비됨 또는 실패 상태가 되고, 어느 상태에서든 풀로 다시 시도할 수 있으며, 준비됨 상태의 스킬에서 새 워크플로를 생성합니다.",
) + [
    mask(376, 176, 40, 24),
    mask(394, 18, 52, 24),
    (">PULL</text>", ">풀</text>", 2),
    mask(534, 176, 64, 32),
    label("GENERATE", "생성"),
    label("Cloning", "복제 중"),
    label("ready", "준비됨"),
    label("failed", "실패"),
    label("Register", "등록"),
    label("returns immediately", "양식은 바로 반환"),
    label("in the background", "백그라운드에서 처리"),
    label("revision published", "리비전 게시됨"),
    label("reason on record", "사유가 레코드에 남음"),
    label("New workflow", "새 워크플로"),
]

# ---------------------------------------------------------------- guides/approvals-sequence
SPECS["guides/approvals-sequence"] = head(
    "Requesting a human approval", "사람의 승인 요청",
    "Sequence diagram of an approval request: the execution agent asks for approval, A2Flow notifies the approver and the run pauses, the approver decides, and A2Flow grants a certificate to each covered step and resumes the run.",
    "승인 요청의 시퀀스 다이어그램. 실행 에이전트가 승인을 요청하면 A2Flow가 승인자에게 알리고 실행이 일시 중지됩니다. 승인자가 결정하면 A2Flow가 승인 범위의 각 단계에 인증서를 부여하고 실행을 재개합니다.",
) + [
    mask(221, 156, 118, 60),
    label("REQUEST APPROVAL", "승인 요청"),
    mask(539, 216, 52, 32),
    label("NOTIFY", "알림"),
    mask(539, 276, 52, 32),
    label("DECIDE", "결정"),
    mask(238, 336, 84, 60),
    label("RUN RESUMES", "실행 재개"),
    label("the whole run", "실행 전체가"),
    label("pauses to wait", "일시 중지되어 대기"),
    label("a certificate is", "단계마다"),
    label("granted per step", "인증서 부여"),
    label("Execution", "실행"),
    label("agent", "에이전트"),
    label("Approver", "승인자"),
    label("LEGEND", "범례"),
    label("Call", "호출"),
    label("Run resumes", "실행 재개"),
]

# ---------------------------------------------------------------- guides/notifications-routing
SPECS["guides/notifications-routing"] = head(
    "Where a notification goes", "알림이 전달되는 곳",
    "Flowchart showing a workflow event routing to the one concerned user, or every eligible approver-group member, and fanning out to the bell, the Notifications page, and email if it is enabled.",
    "워크플로 이벤트가 관련 사용자 한 명 또는 자격이 있는 승인자 그룹 구성원 전원에게 전달되고, 벨, 알림 페이지, 그리고 사용 설정된 경우 이메일로 퍼져 나가는 과정을 보여 주는 순서도.",
) + [
    label("Workflow event", "워크플로 이벤트"),
    label("Concerned user(s)", "관련 사용자"),
    label("or approver group", "또는 승인자 그룹"),
    label("Bell", "벨"),
    label("unread notifications", "읽지 않은 알림"),
    label("Notifications page", "알림 페이지"),
    label("full history", "전체 기록"),
    label("Email", "이메일"),
    label("if enabled", "사용 설정된 경우"),
]

# ---------------------------------------------------------------- guides/tags-vocabulary
SPECS["guides/tags-vocabulary"] = head(
    "One vocabulary, seven registries", "하나의 어휘, 7개 레지스트리",
    "Flowchart showing one shared tag vocabulary per tenant applied to seven taggable registries: Secrets, MCP Servers, Agent Skills, Knowledge Bases, Workflows, Tool Mocks, and User Groups.",
    "테넌트마다 하나인 공유 태그 어휘가 태그를 붙일 수 있는 7개 레지스트리(시크릿, MCP 서버, 에이전트 스킬, 지식 베이스, 워크플로, 도구 모의, 사용자 그룹)에 적용되는 것을 보여 주는 순서도.",
    page_title="Tag vocabulary", svg_title="Tag vocabulary",
) + [
    label("Tag vocabulary", "태그 어휘"),
    label("one per tenant", "테넌트마다 하나"),
    label("Secrets", "시크릿"),
    label("MCP Servers", "MCP 서버"),
    label("Agent Skills", "에이전트 스킬"),
    label("Knowledge Bases", "지식 베이스"),
    label("Workflows", "워크플로"),
    label("Tool Mocks", "도구 모의"),
    label("User Groups", "사용자 그룹"),
]

# ---------------------------------------------------------------- guides/tool-mocks-decision
SPECS["guides/tool-mocks-decision"] = head(
    "Where a tool mock intercepts", "도구 모의가 개입하는 위치",
    "Flowchart showing the agent calling a tool, checking whether it is mocked for this run, and either reaching the real MCP server or receiving the mock's next response with no server contacted.",
    "에이전트가 도구를 호출하면 이 실행에서 모의된 도구인지 확인한 뒤, 실제 MCP 서버에 연결하거나 서버에 연결하지 않고 모의의 다음 응답을 받는 과정을 보여 주는 순서도.",
) + [
    mask(468, 148, 28, 44),
    label("NO", "아니요"),
    mask(376, 236, 32, 24),
    label("YES", "예"),
    label("The agent", "에이전트"),
    label("calls a tool", "도구 호출"),
    label("Mocked for", "이 실행에서"),
    label("this run?", "모의된 도구인가?"),
    label("MCP server", "MCP 서버"),
    label("real side effect", "실제 부작용"),
    label("Mock's next response", "모의의 다음 응답"),
    label("no server contacted", "서버에 연결하지 않음"),
    label("LEGEND", "범례"),
    label("Start / end", "시작 / 종료"),
    label("Decision", "판단"),
]

# ---------------------------------------------------------------- guides/users-groups-relationship
SPECS["guides/users-groups-relationship"] = head(
    "Tenant, users, and groups", "테넌트, 사용자, 그룹",
    "Flowchart showing a tenant containing users and user groups, group membership granting a user its group, and both the user's own roles and its groups' roles feeding the user's effective roles.",
    "테넌트가 사용자와 사용자 그룹을 포함하고, 그룹 소속으로 사용자가 그룹에 속하며, 사용자 자신의 역할과 그룹의 역할이 함께 사용자의 유효 역할이 되는 것을 보여 주는 순서도.",
) + [
    mask(244, 166, 52, 32),
    label("MEMBER", "소속"),
    mask(420, 162, 44, 32),
    mask(244, 232, 44, 32),
    (">ROLES</text>", ">역할</text>", 2),
    label("Tenant", "테넌트"),
    label("org boundary", "조직 경계"),
    label("User Group", "사용자 그룹"),
    label("named bundle", "이름 있는 묶음"),
    label("User", "사용자"),
    label("one account", "계정 하나"),
    label("Effective roles", "유효 역할"),
]

# ---------------------------------------------------------------- guides/workflow-executions-status
SPECS["guides/workflow-executions-status"] = head(
    "Run status", "실행 상태",
    "State machine showing a run starting as running, moving to scheduled while it only waits on a time and back when it resumes, then settling completed once every task has ended with none failed, or failed once every task has ended with at least one failure.",
    "실행이 실행 중으로 시작하고, 시간만 기다리는 동안 예약됨으로 바뀌었다가 재개되면 돌아오며, 모든 작업이 끝났을 때 실패가 없으면 완료됨, 실패가 하나라도 있으면 실패로 확정되는 것을 보여 주는 상태 전이도.",
) + [
    mask(244, 130, 72, 60),
    label("NONE FAILED", "실패 없음"),
    mask(404, 130, 72, 84),
    label("1+ FAILED", "1개 이상 실패"),
    label("WAITS ON A TIME", "시간 대기"),
    label("RESUMES", "재개"),
    label("running", "실행 중"),
    label("scheduled", "예약됨"),
    label("completed", "완료됨"),
    label("failed", "실패"),
]

# ---------------------------------------------------------------- guides/workflow-executions-layout
SPECS["guides/workflow-executions-layout"] = head(
    "The workflow session screen", "워크플로 세션 화면",
    "Flowchart showing the workflow session screen layout: the task timeline and the messages grouped by task sit side by side, and messages lead into the chat input.",
    "워크플로 세션 화면 배치를 보여 주는 순서도. 작업 타임라인과 작업별로 묶인 메시지가 나란히 있고, 메시지 다음에 채팅 입력란이 이어진다.",
) + [
    label("Task timeline", "작업 타임라인"),
    label("collapsible, left edge", "왼쪽 가장자리, 접을 수 있음"),
    label("Messages", "메시지"),
    label("grouped by task", "작업별로 묶임"),
    label("Chat input", "채팅 입력란"),
]

# ---------------------------------------------------------------- guides/workflows-lifecycle
SPECS["guides/workflows-lifecycle"] = head(
    "From skill to running workflow", "스킬에서 실행 중인 워크플로까지",
    "Flowchart showing an Agent Skill generating a Workflow, refined into an adjusted draft, published, and run as a Workflow execution.",
    "에이전트 스킬에서 워크플로를 생성하고, 조정된 초안으로 다듬어 게시한 다음, 워크플로 실행으로 실행하는 과정을 보여 주는 순서도.",
) + [
    label("Agent Skill", "에이전트 스킬"),
    (">Workflow</text>", ">워크플로</text>", 2),
    label("AI-designed templates", "AI가 디자인한 템플릿"),
    label("Adjusted draft", "조정된 초안"),
    label("Published", "게시됨"),
    label("design is frozen", "디자인 고정됨"),
    label("execution", "실행"),
]

# ---------------------------------------------------------------- guides/workflows-status
SPECS["guides/workflows-status"] = head(
    "Detailed workflow status", "워크플로 상세 상태",
    "State machine of a workflow's detailed status: generating leads to draft or failed, failed can be rewritten back to draft, draft publishes to published, published and modified toggle on further edits and publishes, and either can be deactivated back to draft.",
    "워크플로의 상세 상태를 보여 주는 상태 전이도. 생성 중에서 초안 또는 실패로 넘어가고, 실패는 다시 작성하면 초안으로 돌아가며, 초안을 게시하면 게시됨이 된다. 게시됨과 수정됨은 추가 편집과 게시로 서로 오가고, 둘 다 비활성화하면 초안으로 돌아간다.",
) + [
    mask(168, 162, 54, 32),
    label("FAILED", "실패"),
    mask(294, 154, 62, 32),
    label("BY HAND", "직접"),
    mask(663, 54, 54, 32),
    label("EDITED", "편집"),
    mask(445, 70, 50, 32),
    mask(663, 116, 54, 32),
    (">PUBLISH</text>", ">게시</text>", 2),
    mask(445, 302, 70, 56),
    mask(579, 322, 70, 56),
    (">DEACTIVATE</text>", ">비활성화</text>", 2),
    label("generating", "생성 중"),
    label("draft", "초안"),
    label("published", "게시됨"),
    label("modified", "수정됨"),
    label("failed", "실패"),
]

# ---------------------------------------------------------------- guides/workflows-snapshot
SPECS["guides/workflows-snapshot"] = head(
    "Running a workflow makes a snapshot", "워크플로를 실행하면 스냅샷이 만들어집니다",
    "Flowchart showing the published Workflow and its chosen tool mocks copied by value onto a new Workflow execution snapshot, which opens a Workflow session.",
    "게시된 워크플로와 선택한 도구 모의가 새 워크플로 실행 스냅샷에 값으로 복사되고, 스냅샷이 워크플로 세션을 여는 것을 보여 주는 순서도.",
) + [
    mask(328, 126, 68, 72),
    label("COPIED", "값으로 복사"),
    mask(174, 126, 32, 32),
    label("RUN", "실행"),
    label("Workflow", "워크플로"),
    label("published version", "게시된 버전"),
    label("Chosen tool mocks", "선택한 도구 모의"),
    label("Workflow execution", "워크플로 실행"),
    label("the snapshot", "스냅샷"),
    label("Workflow session", "워크플로 세션"),
]

# ---------------------------------------------------------------- guides/workflows-tool-binding
SPECS["guides/workflows-tool-binding"] = head(
    "Tool binding: design time vs run time", "도구 연결: 디자인 시점과 실행 시점",
    "Flowchart showing a design-time tool binding copied at run onto the task, then checked at call time: if the tool is bound to an in-progress task the call goes through, otherwise it is refused with the tools that are allowed.",
    "디자인 시점의 도구 연결이 실행할 때 작업으로 복사되고 호출 시점에 검사되는 과정을 보여 주는 순서도. 도구가 진행 중인 작업에 연결되어 있으면 호출이 통과하고, 그렇지 않으면 허용된 도구 목록과 함께 거부된다.",
) + [
    mask(253, 70, 54, 32),
    label("COPIED", "복사"),
    mask(752, 70, 36, 24),
    label("YES", "예"),
    mask(670, 177, 32, 44),
    label("NO", "아니요"),
    label("Design time", "디자인 시점"),
    label("binds server + tool", "서버와 도구를 연결"),
    label("Run time", "실행 시점"),
    label("task carries binding", "작업이 연결을 보유"),
    label("Bound to a task", "진행 중인 작업에"),
    label("in progress?", "연결되어 있는가?"),
    label("Goes through", "호출 통과"),
    label("Refused", "거부됨"),
    label("lists what's allowed", "허용된 도구 목록 반환"),
]

# ---------------------------------------------------------------- concepts/authorization-effective-roles
SPECS["concepts/authorization-effective-roles"] = head(
    "Resolving effective roles", "유효 역할 결정",
    "Flowchart showing direct role grants on the user record and roles inherited from user groups both feeding a user's effective roles, the union used by every authorization check.",
    "사용자 레코드에 직접 부여된 역할과 사용자 그룹에서 상속된 역할이 모두 사용자의 유효 역할로 모이며, 이 합집합을 모든 권한 검사가 사용한다는 것을 보여 주는 순서도.",
) + [
    mask(254, 83, 52, 32, h=13),
    label("DIRECT", "직접"),
    mask(254, 178, 52, 32, h=13),
    label("GROUP", "그룹"),
    label("Direct grants", "직접 부여"),
    label("on the user record", "사용자 레코드에 부여"),
    label("Group grants", "그룹 부여"),
    label("inherited", "상속"),
    label("Effective roles", "유효 역할"),
    label("Every auth", "모든"),
    label("check", "권한 검사"),
]

# ---------------------------------------------------------------- concepts/authorization-session-matrix
SPECS["concepts/authorization-session-matrix"] = head(
    "Who can reach which session", "누가 어떤 세션에 액세스할 수 있는가",
    "Access matrix showing that Developers, the workflow's creator, and Super Admin reach a Design session, with Reviewers holding read-only access to it, while the run's initiator, its designated approvers, and Super Admin reach a Workflow session, with Admin holding read-only access to the Workflow session.",
    "개발자, 워크플로 작성자, 슈퍼 관리자가 디자인 세션에 액세스하고 검토자는 읽기 전용으로 액세스하며, 실행의 시작자, 지정된 승인자, 슈퍼 관리자가 워크플로 세션에 액세스하고 관리자는 읽기 전용으로 액세스한다는 것을 보여 주는 액세스 매트릭스.",
) + [
    label("Session", "세션"),
    label("vs. actor", "vs. 대상"),
    label("Developer", "개발자"),
    label("Reviewer", "검토자"),
    (">any in tenant</text>", ">테넌트의 모든 사용자</text>", 2),
    label("Creator", "작성자"),
    label("workflow's createdBy", "createdBy"),
    label("Initiator", "시작자"),
    label("started the run", "실행을 시작한 사람"),
    label("Approver", "승인자"),
    label("designated for it", "해당 실행에 지정됨"),
    label("Admin", "관리자"),
    label("tenant admin", "테넌트 관리자"),
    label("Super Admin", "슈퍼 관리자"),
    label("unrestricted", "제한 없음"),
    label("Design session", "디자인 세션"),
    label("Workflow session", "워크플로 세션"),
    (">Yes</text>", ">전체 액세스</text>", 6),
    (">No access</text>", ">액세스 불가</text>", 7),
    (">Read only</text>", ">읽기 전용</text>", 3),
    (">can't drive it</text>", ">구동 불가</text>", 2),
    label("LEGEND", "범례"),
    label("Full access", "전체 액세스"),
]

# ---------------------------------------------------------------- operations/deployment-topology
SPECS["operations/deployment-topology"] = head(
    "Deployment topology", "배포 토폴로지",
    "Architecture diagram showing the browser reaching a reverse proxy that routes API requests (/api/*) straight to the backend API and page requests to the frontend, and the backend API — which also runs the email worker — reaching durable state (database, skill store, secret key), external services (LLM provider, MCP servers), and an SMTP relay.",
    "브라우저가 리버스 프록시에 접속하고, 리버스 프록시가 API 요청(/api/*)은 백엔드 API로 바로, 페이지 요청은 프런트엔드로 라우팅하며, 이메일 워커도 함께 실행하는 백엔드 API가 지속 상태(데이터베이스, 스킬 스토어, 시크릿 키), 외부 서비스(LLM 제공자, MCP 서버), SMTP 릴레이에 접근하는 구조를 보여 주는 아키텍처 다이어그램.",
) + [
    ('<rect x="52" y="484" width="112" height="12"', '<rect x="52" y="483" width="64" height="14"'),
    ('<text x="108" y="493"', '<text x="84" y="493"'),
    label("DURABLE STATE", "지속 상태"),
    ('<rect x="452" y="484" width="128" height="12"', '<rect x="452" y="483" width="76" height="14"'),
    ('<text x="516" y="493"', '<text x="490" y="493"'),
    label("EXTERNAL SERVICES", "외부 서비스"),
    label("Browser", "브라우저"),
    label("Reverse proxy", "리버스 프록시"),
    label("load balancer", "로드 밸런서"),
    label("Frontend", "프런트엔드"),
    mask(690, 158, 52, 44, h=12),
    label("pages", "페이지"),
    label("Backend API", "백엔드 API"),
    label("uvicorn + email worker", "uvicorn + 이메일 워커"),
    label("Database", "데이터베이스"),
    label("records", "레코드"),
    label("Skill store", "스킬 스토어"),
    label("cloned repos", "복제된 저장소"),
    label("Secret key", "시크릿 키"),
    label("encrypts", "암호화"),
    label("LLM provider", "LLM 제공자"),
    label("MCP servers", "MCP 서버"),
    label("SMTP relay", "SMTP 릴레이"),
    label("LEGEND", "범례"),
    label("A2Flow component", "A2Flow 구성 요소"),
    label("External system", "외부 시스템"),
    label("Data store", "데이터 저장소"),
]

# ---------------------------------------------------------------- operations/scaling-lock-race
SPECS["operations/scaling-lock-race"] = head(
    "One driver per conversation", "대화 하나당 구동자는 하나",
    "Sequence diagram of two replicas racing to run the same session: Replica 1 takes a PostgreSQL advisory lock and opens the stream for Client A, while Replica 2's later request for the same session is refused with 409 while the lock is held, and the lock is released only when Replica 1's stream ends.",
    "두 레플리카가 같은 세션을 실행하려고 경합하는 시퀀스 다이어그램. 레플리카 1이 PostgreSQL 권고 잠금을 획득해 클라이언트 A를 위한 스트림을 열고, 잠금이 유지되는 동안 같은 세션에 대한 레플리카 2의 이후 요청은 409로 거부되며, 잠금은 레플리카 1의 스트림이 끝날 때에만 해제됩니다.",
) + [
    mask(401, 188, 78, 60, h=12),
    mask(621, 364, 78, 60, h=12),
    (">TAKE LOCK</text>", ">잠금 획득</text>", 2),
    mask(401, 232, 78, 48, h=12),
    label("ACQUIRED", "획득됨"),
    mask(147, 276, 146, 104, h=12),
    label("SSE STREAM OPENS", "SSE 스트림 열림"),
    mask(609, 408, 102, 100, h=12),
    label("HELD ELSEWHERE", "다른 곳에서 보유"),
    mask(833, 452, 94, 72, h=12),
    label("409 REFUSED", "409로 거부"),
    mask(161, 496, 118, 72, h=12),
    label("STREAM ENDS", "스트림 종료"),
    mask(401, 540, 78, 48, h=12),
    label("RELEASED", "해제됨"),
    label("Client A", "클라이언트 A"),
    label("Replica 1", "레플리카 1"),
    label("Replica 2", "레플리카 2"),
    label("Client B", "클라이언트 B"),
    label("LEGEND", "범례"),
    label("Call", "호출"),
    label("Return", "반환"),
    label("Refused", "거부됨"),
]

# ---------------------------------------------------------------- architecture/approvals-sequence
SPECS["architecture/approvals-sequence"] = head(
    "How an approval gate runs", "승인 게이트의 동작 방식",
    "Sequence diagram of an approval: the execution agent requests approval, A2Flow notifies the approver while the covered steps stay blocked, the approver decides, and A2Flow grants a certificate to each covered step as it starts and lets the run continue.",
    "승인의 시퀀스 다이어그램. 실행 에이전트가 승인을 요청하면, 대상 단계가 차단된 상태에서 A2Flow가 승인자에게 알립니다. 승인자가 결정하면 A2Flow는 대상 단계가 시작될 때마다 인증서를 부여하고 실행을 계속하게 합니다.",
) + [
    mask(222, 160, 116, 60, h=12),
    label("REQUEST APPROVAL", "승인 요청"),
    mask(536, 220, 58, 32, h=12),
    label("NOTIFY", "알림"),
    mask(536, 280, 58, 32, h=12),
    label("DECIDE", "결정"),
    mask(222, 340, 116, 60, h=12),
    label("RUN CONTINUES", "실행 계속"),
    label("the covered steps", "대상 단계는"),
    label("stay blocked", "차단된 상태 유지"),
    label("a certificate is", "단계마다"),
    label("granted per step", "인증서 부여"),
    label("Execution", "실행"),
    label("agent", "에이전트"),
    label("Approver", "승인자"),
    label("LEGEND", "범례"),
    label("Call", "호출"),
    label("Run continues", "실행 계속"),
]

# ---------------------------------------------------------------- architecture/approvals-step-coverage
SPECS["architecture/approvals-step-coverage"] = head(
    "What one approval covers", "승인 하나가 다루는 범위",
    "Flowchart of a five-step task chain where Approval A covers the first three steps and Approval B takes over from the fourth step onward, showing that an approval covers its named step and everything after it up to the next approval.",
    "승인 A가 처음 세 단계를 다루고 승인 B가 네 번째 단계부터 이어받는 5단계 작업 체인의 순서도. 승인은 자신이 지정한 단계와 다음 승인 전까지 그 뒤의 모든 단계를 다룹니다.",
) + [
    label("Approval A", "승인 A"),
    label("Approval B", "승인 B"),
    (">gate</text>", ">게이트</text>", 2),
    label("Ask for a go-ahead", "승인 요청"),
    label("Launch instance", "인스턴스 시작"),
    label("Tag instance", "인스턴스 태그 지정"),
    label("Ask again", "다시 요청"),
    label("Delete snapshot", "스냅샷 삭제"),
    label("APPROVAL A COVERS", "승인 A가 다루는 범위"),
    label("APPROVAL B COVERS", "승인 B가 다루는 범위"),
    label("LEGEND", "범례"),
    label("Approval gate", "승인 게이트"),
]

# ---------------------------------------------------------------- architecture/overview-lifecycle
SPECS["architecture/overview-lifecycle"] = head(
    "How a workflow moves", "워크플로의 흐름",
    "Flowchart showing an Agent Skill generated into a Workflow, run as a Workflow execution inside a Workflow session, whose Tasks request human approval or call an MCP tool through the MCP gateway to reach an MCP server.",
    "에이전트 스킬에서 워크플로가 생성되고, 워크플로 세션 안에서 워크플로 실행으로 수행되며, 그 작업이 사람의 승인을 요청하거나 MCP 게이트웨이를 통해 MCP 도구를 호출하여 MCP 서버에 도달하는 과정을 보여 주는 순서도.",
) + [
    ('<rect x="508" y="118" width="90" height="12"', '<rect x="508" y="117" width="90" height="14"'),
    label("GENERATE", "워크플로 생성"),
    ('<rect x="508" y="222" width="100" height="12"', '<rect x="508" y="221" width="92" height="14"'),
    label("PUBLISH/RUN", "게시 후 실행"),
    mask(315, 520, 120, 84, h=12),
    label("NEEDS A PERSON", "사람이 필요함"),
    mask(565, 520, 120, 84, h=12),
    label("NEEDS A TOOL", "도구가 필요함"),
    mask(460, 560, 80, 44, h=12),
    label("CERTIFICATE", "인증서"),
    label("Agent Skill", "에이전트 스킬"),
    label("a Git repository", "Git 저장소"),
    label("Workflow", "워크플로"),
    label("templates + tool bindings", "템플릿 + 도구 연결"),
    label("Workflow execution", "워크플로 실행"),
    label("a snapshot of the design", "디자인의 스냅샷"),
    label("Workflow session", "워크플로 세션"),
    label("the run's shared chat", "실행이 진행되는 공유 채팅"),
    label("Tasks", "작업"),
    label("one at a time", "한 번에 하나씩"),
    label("Approval gate", "승인 게이트"),
    label("MCP gateway", "MCP 게이트웨이"),
    label("MCP server", "MCP 서버"),
]

# ---------------------------------------------------------------- architecture/secrets-resolution
SPECS["architecture/secrets-resolution"] = head(
    "How a secret reference resolves", "시크릿 참조의 해석",
    "Flowchart showing a name/key secret reference branching by storage type: local secrets are decrypted from the stored value, Vault secrets are read live, and both feed an MCP server connection or a skill repository clone.",
    "시크릿 참조가 유형에 따라 갈라지는 것을 보여 주는 순서도. 로컬 유형은 저장된 값을 복호화하고, Vault 유형은 Vault에서 값을 실시간으로 읽으며, 둘 다 MCP 서버 연결이나 스킬 저장소 복제에 사용됩니다.",
    page_title="Secret reference resolution", svg_title="Secret reference resolution",
) + [
    mask(305, 160, 48, 32, h=12),
    label("LOCAL", "로컬"),
    label("A reference", "참조"),
    label("Which type?", "어떤 유형인가?"),
    label("Decrypt the", "저장된 값을"),
    label("stored value", "복호화"),
    label("Read it live", "Vault에서"),
    label("from Vault", "실시간으로 읽기"),
    label("MCP server connection", "MCP 서버 연결"),
    label("or a skill repository clone", "또는 스킬 저장소 복제"),
]

_POLICY_MASKS = [
    mask(612, 140, 56, 44, h=12),
    label("DENIED", "거부됨"),
    mask(508, 234, 64, 44, h=12),
    label("ALLOWED", "허용됨"),
    mask(698, 300, 32, 24, h=12),
    label("YES", "예"),
    mask(508, 390, 28, 44, h=12),
    label("NO", "아니요"),
    label("calls a tool", "도구 호출"),
    label("Policy chain", "정책 체인"),
    label("Refused", "거부됨"),
    label("Mocked for", "이 실행에서"),
    label("this run?", "모의된 도구인가?"),
    label("Mock's response", "모의의 응답"),
    label("no server contacted", "서버에 연결하지 않음"),
    label("MCP server", "MCP 서버"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-policy-chain
SPECS["architecture/mcp-gateway-and-proxy-policy-chain"] = head(
    "The policy chain", "정책 체인",
    "Flowchart showing how the MCP gateway decides a tool call: a policy chain either refuses it or allows it, an allowed call is either answered from a mock or goes through credential injection and the MCP proxy to the real MCP server, and both the refusal and the real call produce an audit record.",
    "도구 호출을 결정하는 정책 체인의 순서도. 거부된 호출은 허용된 내용을 알리며 거부되고, 허용된 호출은 모의로 응답하거나 자격 증명 주입과 MCP 프록시를 거쳐 MCP 서버로 전달되며, 거부와 실제 호출은 모두 감사 기록을 남깁니다.",
    page_title="Policy chain", svg_title="Policy chain",
) + _POLICY_MASKS + [
    label("Execution agent", "실행 에이전트"),
    label("lists what is allowed", "허용된 내용을 알림"),
    label("Credential injection", "자격 증명 주입"),
    label("MCP proxy", "MCP 프록시"),
    label("Audit record", "감사 기록"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-tool-mocks
SPECS["architecture/mcp-gateway-and-proxy-tool-mocks"] = head(
    "Where the mock sits", "모의의 위치",
    "Flowchart showing that a tool mock is consulted only after the same policy chain a production call faces: a denied call is refused exactly as in production, and an allowed call is answered from a mock's next response or the real MCP server.",
    "도구 모의는 프로덕션 호출과 동일한 정책 체인을 거친 후에만 참조된다는 것을 보여 주는 순서도. 거부된 호출은 프로덕션과 똑같이 거부되고, 허용된 호출은 모의의 다음 응답이나 실제 MCP 서버가 응답합니다.",
) + _POLICY_MASKS + [
    label("The agent", "에이전트"),
    label("exactly as production", "프로덕션과 똑같이"),
    label("the real side effect", "실제 부작용"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-trust-boundary
SPECS["architecture/mcp-gateway-and-proxy-trust-boundary"] = head(
    "Crossing the trust boundary", "신뢰 경계 넘기",
    "Architecture diagram showing the MCP gateway, which decides whether a call is allowed, mocked, and which credentials it needs, handing exactly one authorized call across a trust boundary into the MCP proxy, which starts or connects to the real MCP server.",
    "호출의 허용 여부, 모의 여부, 필요한 자격 증명을 결정하는 MCP 게이트웨이가 권한이 부여된 호출 정확히 하나를 신뢰 경계 너머의 MCP 프록시로 넘기고, MCP 프록시가 실제 MCP 서버를 시작하거나 연결하는 것을 보여 주는 아키텍처 다이어그램.",
) + [
    ('<rect x="52" y="64" width="112" height="12"', '<rect x="52" y="63" width="112" height="14"'),
    label("RUNS THE AGENT", "에이전트가 실행되는 쪽"),
    ('<rect x="412" y="64" width="64" height="12"', '<rect x="412" y="63" width="64" height="14"'),
    label("SANDBOX", "샌드박스"),
    mask(328, 104, 84, 60, h=12),
    label("AUTHORIZED", "권한 부여"),
    label("MCP gateway", "MCP 게이트웨이"),
    label("allowed, mocked, credentials", "허용, 모의, 자격 증명 결정"),
    label("MCP proxy", "MCP 프록시"),
    label("starts or connects", "시작 또는 연결"),
    label("MCP server", "MCP 서버"),
    label("outside our control", "관리 범위 밖"),
    label("LEGEND", "범례"),
    label("Trust boundary", "신뢰 경계"),
]

# ---------------------------------------------------------------- architecture/sessions-turn-flow
SPECS["architecture/sessions-turn-flow"] = head(
    "How a turn runs", "한 턴의 진행 방식",
    "Sequence diagram of one chat turn: the user's message travels from Frontend to Backend to the Model, the model's streamed reply and any render_a2ui surface flow back, and the user's filled-in surface makes the same round trip again.",
    "채팅 한 턴의 시퀀스 다이어그램. 사용자의 메시지가 프런트엔드에서 백엔드를 거쳐 모델로 전달되고, 모델의 스트리밍 응답과 render_a2ui 화면 요소가 돌아오며, 사용자가 채운 화면 요소가 같은 경로를 다시 왕복합니다.",
) + [
    mask(190, 160, 100, 72, h=12),
    label("WRITES MESSAGE", "메시지 작성"),
    mask(396, 200, 144, 124, h=12),
    label("MESSAGE + TOOL SCHEMA", "메시지 + 도구 스키마"),
    mask(640, 240, 104, 96, h=12),
    label("BRIDGE TO AGENT", "에이전트로 연결"),
    mask(632, 280, 120, 110, h=12),
    label("TEXT + TOOL CALLS", "텍스트 + 도구 호출"),
    mask(414, 320, 108, 96, h=12),
    label("STREAMED ONWARD", "그대로 스트리밍"),
    mask(192, 360, 96, 88, h=12),
    label("DRAWS SURFACE", "화면 요소 표시"),
    mask(186, 400, 108, 76, h=12),
    label("FILLS + SUBMITS", "입력 후 제출"),
    mask(414, 440, 108, 100, h=12),
    label("FULL DATA MODEL", "전체 데이터 모델"),
    mask(638, 480, 108, 76, h=12),
    label("MATCHED TO CALL", "호출과 대조"),
    mask(412, 520, 112, 96, h=12),
    label("RESPONDS TO USER", "사용자에게 응답"),
    label("a render_a2ui call is", "render_a2ui 호출은"),
    label("forwarded, never executed", "실행되지 않고 전달됨"),
    label("User", "사용자"),
    label("Browser", "브라우저"),
    label("Frontend", "프런트엔드"),
    label("Backend", "백엔드"),
    label("Model", "모델"),
    label("LEGEND", "범례"),
    label("Call", "호출"),
    label("Streamed return", "스트리밍 반환"),
    label("Response to user", "사용자 응답"),
]

# ---------------------------------------------------------------- architecture/workflow-design-status
SPECS["architecture/workflow-design-status"] = head(
    "Workflow status lifecycle", "워크플로 상태 수명 주기",
    "State machine showing a workflow moving from a published Agent Skill through generating to draft or failed, then from draft through published and modified, with publish looping back from modified.",
    "게시된 에이전트 스킬에서 생성 중을 거쳐 초안 또는 실패로 이동하고, 초안에서 게시됨과 수정됨으로 진행하며, 수정됨에서 게시를 통해 다시 돌아오는 워크플로의 상태 다이어그램.",
) + [
    mask(196, 96, 48, 32, h=12),
    label("GENERATE", "생성"),
    mask(366, 180, 56, 60, h=12),
    label("NO STEPS", "단계 없음"),
    mask(568, 180, 48, 44, h=12),
    label("REVISED", "재작성"),
    mask(596, 96, 48, 32, h=12),
    mask(676, 180, 48, 32, h=12),
    label("EDITED", "편집"),
    mask(736, 180, 48, 32, h=12),
    (">PUBLISH</text>", ">게시</text>", 2),
    label("generating", "생성 중"),
    label("draft", "초안"),
    label("published", "게시됨"),
    label("failed", "실패"),
    label("modified", "수정됨"),
    label("Agent Skill", "에이전트 스킬"),
    label("published revision", "게시된 리비전"),
    label("design run in progress", "디자인 실행 진행 중"),
    label("templates + bindings", "템플릿 + 연결"),
    label("design is frozen", "디자인 고정됨"),
    label("reason on record", "사유가 레코드에 남음"),
    label("runs use published", "실행은 게시본 사용"),
    label("LEGEND", "범례"),
    label("Precondition", "사전 조건"),
    label("Status", "상태"),
    label("Live version", "실행에 쓰이는 버전"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-snapshot
SPECS["architecture/workflow-execution-snapshot"] = head(
    "Running a workflow copies its design", "워크플로를 실행하면 디자인이 복사됩니다",
    "Flowchart showing a published workflow and its chosen tool mocks copied by value onto a new workflow execution snapshot, which opens a workflow session containing tasks that all start pending.",
    "게시된 워크플로와 선택한 도구 모의가 새 워크플로 실행 스냅샷으로 복사되고, 이 스냅샷이 시작 시점에 모든 작업이 대기 중인 워크플로 세션을 여는 과정을 보여 주는 순서도.",
    page_title="Running a workflow", svg_title="Running a workflow copies its design",
) + [
    mask(404, 136, 32, 32, h=12),
    label("RUN", "실행"),
    mask(556, 136, 96, 72, h=12),
    label("COPIED BY VALUE", "값으로 복사"),
    label("Workflow", "워크플로"),
    label("published version", "게시된 버전"),
    label("Chosen tool mocks", "선택한 도구 모의"),
    label("test runs only", "테스트 실행 전용"),
    label("Workflow execution", "워크플로 실행"),
    label("the snapshot", "스냅샷"),
    label("Workflow session", "워크플로 세션"),
    label("the run's chat", "실행의 채팅"),
    label("Tasks", "작업"),
    label("all pending at the start", "시작 시 모두 대기 중"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-run-loop
SPECS["architecture/workflow-execution-run-loop"] = head(
    "How the run advances", "실행이 진행되는 방식",
    "Flowchart showing the task-advancement loop: list tasks, pick one whose dependencies have completed, mark it in progress, do the work, mark it ended, and repeat until every task has ended and the run settles.",
    "실행 진행 루프의 순서도. 실행의 작업을 나열하고, 종속 대상이 완료된 작업을 골라 진행 중으로 표시하고, 작업을 수행한 뒤 완료됨, 실패 또는 건너뜀으로 표시하고, 이를 반복하다가 모든 작업이 끝나면 확정합니다.",
) + [
    mask(484, 222, 32, 32, h=12),
    label("YES", "있음"),
    mask(644, 154, 24, 32, h=12),
    label("NO", "없음"),
    label("List the run's tasks", "실행의 작업 나열"),
    label("A pending task whose", "종속 대상이 완료된"),
    label("deps have completed?", "대기 중 작업이 있는가?"),
    label("Mark it in_progress", "진행 중으로 표시"),
    label("Do the work", "작업 수행"),
    label("tools, approvals, conversation", "도구, 승인, 대화"),
    label("Mark it completed,", "완료됨, 실패 또는"),
    label("failed, or skipped", "건너뜀으로 표시"),
    label("Run settles", "실행 확정"),
    label("every task has ended", "모든 작업 종료됨"),
    label("LEGEND", "범례"),
    label("Step (rectangle)", "단계(직사각형)"),
    label("Decision (diamond)", "판단(마름모)"),
    label("Loop exit (oval)", "루프 종료(타원)"),
    label("Continues the loop", "루프 계속"),
]
