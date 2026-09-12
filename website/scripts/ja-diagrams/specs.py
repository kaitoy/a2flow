"""Per-diagram replacement specs: English light HTML -> Japanese light HTML.

``SPECS`` maps a diagram id (``<section>/<basename>``) to the exact-substring replacements
``render.py`` applies to the English light HTML. Each entry is ``(old, new)`` or
``(old, new, count)``; ``old`` must occur exactly ``count`` times (default once), so a
change to the English source that invalidates a translation fails loudly instead of
silently shipping a half-translated diagram.

Conventions the translations follow, mirroring the Japanese prose:

* node names, edge labels, notes and legends are Japanese;
* status values (``draft``, ``running``), UI button names (``Run``, ``Publish``,
  ``Deactivate``) and technical strings (``name/key``, ``POST /AGENT``, ``HTTPS``) stay
  English, so their 9px mono labels are left untouched;
* a translated edge label goes from 9px mono to 12px sans, so its background mask is
  widened with :func:`mask` — budget 1em per full-width glyph plus 8px;
* zone-title chips stay anchored to the zone's top-left corner rather than re-centred.
"""

SPECS: dict[str, list[tuple]] = {}


def mask(x: int, y: int, w: int, new_w: int, fill: str = "#f2f8fc", h: int = 14) -> tuple[str, str]:
    """Resize an edge-label mask rect for a 12px CJK label, keeping its centre.

    Args:
        x: The English rect's ``x``.
        y: The English rect's ``y``.
        w: The English rect's ``width``.
        new_w: Width needed by the Japanese label.
        fill: The rect's fill (light paper by default).
        h: The English rect's ``height`` (12, 13 or 14 in the sources).

    Returns:
        The ``(old, new)`` replacement pair.
    """
    old = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}"/>'
    nx = x + (w - new_w) // 2
    new = f'<rect x="{nx}" y="{y - 1}" width="{new_w}" height="{h + 2}" rx="2" fill="{fill}"/>'
    return old, new


def label(old: str, new: str) -> tuple[str, str]:
    """Replace the content of a ``<text>`` element, matched on ``>old</text>``."""
    return f">{old}</text>", f">{new}</text>"


def head(en_title: str, ja_title: str, en_desc: str, ja_desc: str, page_title: str | None = None, svg_title: str | None = None) -> list[tuple[str, str]]:
    """Translate the page ``<title>``, the ``<h1>``, and the SVG ``<title>``/``<desc>``.

    The page and SVG titles default to the ``<h1>`` text; pass ``page_title`` /
    ``svg_title`` for the few diagrams where they differ.
    """
    return [
        (f"<title>{page_title or en_title}</title>", f"<title>{ja_title}</title>"),
        (f"<h1>{en_title}</h1>", f"<h1>{ja_title}</h1>"),
        (f'-title">{svg_title or en_title}</title>', f'-title">{ja_title}</title>'),
        (f">{en_desc}</desc>", f">{ja_desc}</desc>"),
    ]


# ---------------------------------------------------------------- guides/secrets-usage
SPECS["guides/secrets-usage"] = [
    ("<title>Where a secret entry is used</title>", "<title>シークレットのエントリが使われる場所</title>"),
    ("<h1>Where a secret entry is used</h1>", "<h1>シークレットのエントリが使われる場所</h1>"),
    ('<title id="secrets-usage-title">Where a secret entry is used</title>', '<title id="secrets-usage-title">シークレットのエントリが使われる場所</title>'),
    (
        "Flowchart showing a secret's entry referenced either in an MCP server's headers and environment variables, or as an Agent Skill repository's auth password.",
        "シークレットのエントリが、MCP サーバーのヘッダーと環境変数から参照されるか、エージェントスキルのリポジトリの Auth Password として参照されるかを示すフローチャート。",
    ),
    # edge label HEADERS -> ヘッダー (12px needs a 56px mask)
    ('<rect x="423" y="56" width="54" height="14" rx="2" fill="#f2f8fc"/>', '<rect x="422" y="56" width="56" height="16" rx="2" fill="#f2f8fc"/>'),
    ('>HEADERS</text>', '>ヘッダー</text>'),
    (">Secret</text>", ">シークレット</text>"),
    (">Entry</text>", ">エントリ</text>"),
    (">MCP server</text>", ">MCP サーバー</text>"),
    (">headers + env vars</text>", ">ヘッダー + 環境変数</text>"),
    (">Agent Skill</text>", ">エージェントスキル</text>"),
    (">repo auth password</text>", ">リポジトリの Auth Password</text>"),
]

# ---------------------------------------------------------------- guides/admin-ui-navigation
SPECS["guides/admin-ui-navigation"] = head(
    "Admin UI navigation", "管理 UI のナビゲーション",
    "Flowchart of the admin UI navigation model: the welcome page leads to a section list, which opens a create form or a detail page by clicking a name, and a breadcrumb on the detail page returns to the list.",
    "管理 UI のナビゲーションモデルのフローチャート。ようこそページからセクションの一覧へ進み、一覧からは新規作成フォームか、名前をクリックして詳細ページを開く。詳細ページのパンくずで一覧に戻る。",
) + [
    mask(492, 84, 40, 92),
    label("NAME", "名前をクリック"),
    mask(476, 134, 72, 56),
    label("BREADCRUMB", "パンくず"),
    label("Welcome page", "ようこそページ"),
    label("quick-action cards", "クイックアクションカード"),
    label("Section list", "セクションの一覧"),
    label("e.g. Workflows", "例: Workflows"),
    label("Create form", "新規作成フォーム"),
    label("Detail page", "詳細ページ"),
    label("titled by name", "レコード名がタイトル"),
]

# ---------------------------------------------------------------- guides/agent-skills-lifecycle
SPECS["guides/agent-skills-lifecycle"] = head(
    "Agent Skill lifecycle", "エージェントスキルのライフサイクル",
    "State machine showing an Agent Skill registered, cloning in the background, becoming ready or failed, pulling to retry from either state, and a ready skill generating a new workflow.",
    "エージェントスキルの状態遷移図。登録するとバックグラウンドでクローンされ、ready か failed になる。どちらの状態からも Pull でやり直せ、ready のスキルから新しいワークフローを生成できる。",
) + [
    label("Register", "登録"),
    label("returns immediately", "フォームはすぐ返る"),
    label("in the background", "バックグラウンドで処理"),
    label("revision published", "リビジョンが公開された"),
    label("reason on record", "理由がレコードに出る"),
    label("New workflow", "新しいワークフロー"),
]

# ---------------------------------------------------------------- guides/approvals-sequence
SPECS["guides/approvals-sequence"] = head(
    "Requesting a human approval", "人の承認を依頼する",
    "Sequence diagram of an approval request: the execution agent asks for approval, A2Flow notifies the approver and the run pauses, the approver decides, and A2Flow grants a certificate to each covered step and resumes the run.",
    "承認依頼のシーケンス図。実行エージェントが承認を依頼し、A2Flow が承認者に通知して実行が止まる。承認者が判断すると、A2Flow は対象の各ステップに証明書を渡して実行を再開する。",
) + [
    mask(221, 156, 118, 68),
    label("REQUEST APPROVAL", "承認を依頼"),
    mask(539, 216, 52, 32),
    label("NOTIFY", "通知"),
    mask(539, 276, 52, 32),
    label("DECIDE", "判断"),
    mask(238, 336, 84, 68),
    label("RUN RESUMES", "実行が再開"),
    label("the whole run", "実行全体が"),
    label("pauses to wait", "止まって待つ"),
    label("a certificate is", "ステップごとに"),
    label("granted per step", "証明書が渡される"),
    label("Execution", "実行"),
    label("agent", "エージェント"),
    label("Approver", "承認者"),
    label("LEGEND", "凡例"),
    label("Call", "呼び出し"),
    label("Run resumes", "実行の再開"),
]

# ---------------------------------------------------------------- guides/notifications-routing
SPECS["guides/notifications-routing"] = head(
    "Where a notification goes", "通知の行き先",
    "Flowchart showing a workflow event routing to the one concerned user, or every eligible approver-group member, and fanning out to the bell, the Notifications page, and email if it is enabled.",
    "ワークフローの出来事が、関係する 1 人(承認者グループなら資格のある全員)に届き、ベル、通知ページ、そして有効ならメールへ広がることを示すフローチャート。",
) + [
    label("Workflow event", "ワークフローの出来事"),
    label("Concerned user(s)", "関係するユーザー"),
    label("or approver group", "または承認者グループの全員"),
    label("Bell", "ベル"),
    label("unread notifications", "未読の通知"),
    label("Notifications page", "通知ページ"),
    label("full history", "履歴の全体"),
    label("Email", "メール"),
    label("if enabled", "有効にしていれば"),
]

# ---------------------------------------------------------------- guides/tags-vocabulary
SPECS["guides/tags-vocabulary"] = head(
    "One vocabulary, six registries", "1 つの語彙、6 つのレジストリ",
    "Flowchart showing one shared tag vocabulary per tenant applied to six taggable registries: Secrets, MCP Servers, Agent Skills, Workflows, Tool Mocks, and User Groups.",
    "テナントごとに 1 つのタグ語彙が、タグを付けられる 6 つのレジストリ(Secrets、MCP Servers、Agent Skills、Workflows、Tool Mocks、User Groups)に共有されることを示すフローチャート。",
    page_title="Tag vocabulary", svg_title="Tag vocabulary",
) + [
    label("Tag vocabulary", "タグ語彙"),
    label("one per tenant", "テナントごとに 1 つ"),
]

# ---------------------------------------------------------------- guides/tool-mocks-decision
SPECS["guides/tool-mocks-decision"] = head(
    "Where a tool mock intercepts", "ツールモックが割り込む場所",
    "Flowchart showing the agent calling a tool, checking whether it is mocked for this run, and either reaching the real MCP server or receiving the mock's next response with no server contacted.",
    "エージェントがツールを呼ぶと、この実行でモックされているかを確認し、本物の MCP サーバーに届くか、どのサーバーにも接続せずモックの次のレスポンスを受け取るかを示すフローチャート。",
) + [
    mask(468, 148, 28, 44),
    label("NO", "いいえ"),
    mask(376, 236, 32, 32),
    label("YES", "はい"),
    label("The agent", "エージェント"),
    label("calls a tool", "ツールを呼ぶ"),
    label("Mocked for", "この実行で"),
    label("this run?", "モックされている?"),
    label("MCP server", "MCP サーバー"),
    label("real side effect", "本物の副作用"),
    label("Mock's next response", "モックの次のレスポンス"),
    label("no server contacted", "サーバーには接続しない"),
    label("LEGEND", "凡例"),
    label("Start / end", "開始 / 終了"),
    label("Decision", "判断"),
]

# ---------------------------------------------------------------- guides/users-groups-relationship
SPECS["guides/users-groups-relationship"] = head(
    "Tenant, users, and groups", "テナント、ユーザー、グループ",
    "Flowchart showing a tenant containing users and user groups, group membership granting a user its group, and both the user's own roles and its groups' roles feeding the user's effective roles.",
    "テナントがユーザーとユーザーグループを含み、メンバーシップでユーザーがグループに属し、ユーザー自身のロールとグループのロールの両方が実効ロールになることを示すフローチャート。",
) + [
    mask(244, 166, 52, 92),
    label("MEMBER", "メンバーシップ"),
    mask(420, 162, 44, 44),
    mask(244, 232, 44, 44),
    (">ROLES</text>", ">ロール</text>", 2),
    label("Tenant", "テナント"),
    label("org boundary", "組織の境界"),
    label("User Group", "ユーザーグループ"),
    label("named bundle", "名前つきの束"),
    label("User", "ユーザー"),
    label("one account", "1 つのアカウント"),
    label("Effective roles", "実効ロール"),
]

# ---------------------------------------------------------------- guides/workflow-executions-status
SPECS["guides/workflow-executions-status"] = head(
    "Run status", "実行のステータス",
    "State machine showing a run starting as running, then settling completed once every task has ended with none failed, or failed once every task has ended with at least one failure.",
    "実行が running で始まり、全タスクが終わって失敗がなければ completed、1 つ以上が失敗していれば failed に落ち着くことを示す状態遷移図。",
) + [
    mask(244, 130, 72, 56),
    label("NONE FAILED", "失敗なし"),
    mask(404, 130, 72, 80),
    label("1+ FAILED", "1 つ以上失敗"),
]

# ---------------------------------------------------------------- guides/workflow-executions-layout
SPECS["guides/workflow-executions-layout"] = head(
    "The workflow session screen", "ワークフローセッションの画面",
    "Flowchart showing the workflow session screen layout: the task timeline and the messages grouped by task sit side by side, and messages lead into the chat input.",
    "ワークフローセッションの画面レイアウトを示すフローチャート。タスクタイムラインと、タスクごとにまとまったメッセージが横に並び、メッセージの先にチャット入力がある。",
) + [
    label("Task timeline", "タスクタイムライン"),
    label("collapsible, left edge", "左端。折りたためる"),
    label("Messages", "メッセージ"),
    label("grouped by task", "タスクごとにまとまる"),
    label("Chat input", "チャット入力"),
]

# ---------------------------------------------------------------- guides/workflows-lifecycle
SPECS["guides/workflows-lifecycle"] = head(
    "From skill to running workflow", "スキルから実行中のワークフローまで",
    "Flowchart showing an Agent Skill generating a Workflow, refined into an adjusted draft, published, and run as a Workflow execution.",
    "エージェントスキルからワークフローを生成し、下書きを調整して公開し、ワークフロー実行として動かすまでを示すフローチャート。",
) + [
    ('<rect x="60" y="60" width="140" height="68"', '<rect x="44" y="60" width="156" height="68"'),
    ('<text x="130" y="100" fill="#1c1e21" font-size="14" font-weight="600" ',
     '<text x="122" y="100" fill="#1c1e21" font-size="14" font-weight="600" '),
    label("Agent Skill", "エージェントスキル"),
    (">Workflow</text>", ">ワークフロー</text>", 2),
    label("AI-designed templates", "AI が設計したテンプレート"),
    label("Adjusted draft", "調整した下書き"),
    label("Published", "公開済み"),
    label("design is frozen", "設計が凍結される"),
    label("execution", "実行"),
]

# ---------------------------------------------------------------- guides/workflows-status
SPECS["guides/workflows-status"] = head(
    "Detailed workflow status", "ワークフローの詳細ステータス",
    "State machine of a workflow's detailed status: generating leads to draft or failed, failed can be rewritten back to draft, draft publishes to published, published and modified toggle on further edits and publishes, and either can be deactivated back to draft.",
    "ワークフローの詳細ステータスの状態遷移図。generating から draft か failed になり、failed は書き直して draft に戻せる。draft は公開すると published になり、published と modified は編集と公開で行き来し、どちらも Deactivate で draft に戻る。",
) + [
    mask(168, 162, 54, 40),
    label("FAILED", "失敗"),
    mask(294, 154, 62, 44),
    label("BY HAND", "手動で"),
    mask(663, 54, 54, 40),
    label("EDITED", "編集"),
]

# ---------------------------------------------------------------- guides/workflows-snapshot
SPECS["guides/workflows-snapshot"] = head(
    "Running a workflow makes a snapshot", "ワークフローを実行するとスナップショットができる",
    "Flowchart showing the published Workflow and its chosen tool mocks copied by value onto a new Workflow execution snapshot, which opens a Workflow session.",
    "公開済みのワークフローと選んだツールモックが、新しいワークフロー実行のスナップショットに値としてコピーされ、ワークフローセッションが開くことを示すフローチャート。",
) + [
    mask(328, 126, 68, 92),
    label("COPIED", "値としてコピー"),
    label("Workflow", "ワークフロー"),
    label("published version", "公開済みの版"),
    label("Chosen tool mocks", "選んだツールモック"),
    label("Workflow execution", "ワークフロー実行"),
    label("the snapshot", "スナップショット"),
    label("Workflow session", "ワークフローセッション"),
]

# ---------------------------------------------------------------- guides/workflows-tool-binding
SPECS["guides/workflows-tool-binding"] = head(
    "Tool binding: design time vs run time", "ツールの割り当て: 設計時と実行時",
    "Flowchart showing a design-time tool binding copied at run onto the task, then checked at call time: if the tool is bound to an in-progress task the call goes through, otherwise it is refused with the tools that are allowed.",
    "設計時のツールの割り当てが Run 時にタスクへコピーされ、呼び出し時に確認されることを示すフローチャート。進行中のタスクに割り当てられたツールなら呼び出しは届き、そうでなければ使えるツールの一覧とともに拒否される。",
) + [
    mask(253, 70, 54, 44),
    label("COPIED", "コピー"),
    mask(752, 70, 36, 32),
    label("YES", "はい"),
    mask(670, 177, 32, 44),
    label("NO", "いいえ"),
    label("Design time", "設計時"),
    label("binds server + tool", "サーバーとツールを割り当て"),
    label("Run time", "実行時"),
    label("task carries binding", "タスクが割り当てを持つ"),
    label("Bound to a task", "進行中のタスクに"),
    label("in progress?", "割り当てられている?"),
    label("Goes through", "呼び出しが届く"),
    label("Refused", "拒否"),
    label("lists what's allowed", "使えるツールの一覧が返る"),
]

# ---------------------------------------------------------------- concepts/authorization-effective-roles
SPECS["concepts/authorization-effective-roles"] = head(
    "Resolving effective roles", "実効ロールの解決",
    "Flowchart showing direct role grants on the user record and roles inherited from user groups both feeding a user's effective roles, the union used by every authorization check.",
    "ユーザーレコードに直接付与されたロールと、ユーザーグループから継承したロールの両方が実効ロールになり、その和集合をすべての認可チェックが使うことを示すフローチャート。",
) + [
    mask(254, 83, 52, 32, h=13),
    label("DIRECT", "直接"),
    mask(254, 178, 52, 56, h=13),
    label("GROUP", "グループ"),
    label("Direct grants", "直接付与"),
    label("on the user record", "ユーザーレコード上"),
    label("Group grants", "グループ付与"),
    label("inherited", "継承"),
    label("Effective roles", "実効ロール"),
    label("Every auth", "すべての"),
    label("check", "認可チェック"),
]

# ---------------------------------------------------------------- concepts/authorization-session-matrix
SPECS["concepts/authorization-session-matrix"] = head(
    "Who can reach which session", "誰がどのセッションに入れるか",
    "Access matrix showing that Developers, the workflow's creator, and Super Admin reach a Design session, while the run's initiator, its designated approvers, and Super Admin reach a Workflow session, with Admin holding read-only access to the Workflow session.",
    "開発者、ワークフローの作成者、スーパー管理者が設計セッションに入れ、実行の開始者、指名された承認者、スーパー管理者がワークフローセッションに入れること、そして管理者はワークフローセッションを読み取りのみできることを示すアクセスマトリクス。",
) + [
    label("Session", "セッション"),
    label("vs. actor", "vs. アクター"),
    label("Developer", "開発者"),
    label("any in tenant", "テナントの全員"),
    label("Creator", "作成者"),
    label("workflow's createdBy", "createdBy"),
    label("Initiator", "開始者"),
    label("started the run", "実行を始めた人"),
    label("Approver", "承認者"),
    label("designated for it", "その実行で指名"),
    label("Admin", "管理者"),
    label("tenant admin", "テナントの管理者"),
    label("Super Admin", "スーパー管理者"),
    label("unrestricted", "制限なし"),
    label("Design session", "設計セッション"),
    label("Workflow session", "ワークフローセッション"),
    (">Yes</text>", ">フルアクセス</text>", 6),
    (">No access</text>", ">アクセス不可</text>", 6),
    (">Read only</text>", ">読み取りのみ</text>", 2),
    label("the one asymmetry", "唯一の例外"),
    label("LEGEND", "凡例"),
    label("Full access", "フルアクセス"),
]

# ---------------------------------------------------------------- operations/deployment-topology
SPECS["operations/deployment-topology"] = head(
    "Deployment topology", "デプロイのトポロジー",
    "Architecture diagram showing the browser reaching the frontend through a reverse proxy, the frontend calling the backend API, and the backend API — which also runs the email worker — reaching durable state (database, skill store, secret key), external services (LLM provider, MCP servers), and an SMTP relay.",
    "ブラウザがリバースプロキシ経由でフロントエンドに届き、フロントエンドがバックエンド API を呼び、メールワーカーも動かすバックエンド API が、永続化が必要な状態(データベース、スキルストア、暗号化キー)、外部サービス(LLM プロバイダー、MCP サーバー)、SMTP リレーに届くことを示すアーキテクチャ図。",
) + [
    ('<rect x="52" y="484" width="112" height="12"', '<rect x="52" y="483" width="116" height="14"'),
    ('<text x="108" y="493"', '<text x="110" y="493"'),
    label("DURABLE STATE", "永続化が必要な状態"),
    ('<rect x="452" y="484" width="128" height="12"', '<rect x="452" y="483" width="68" height="14"'),
    ('<text x="516" y="493"', '<text x="486" y="493"'),
    label("EXTERNAL SERVICES", "外部サービス"),
    label("Browser", "ブラウザ"),
    label("Reverse proxy", "リバースプロキシ"),
    label("load balancer", "ロードバランサー"),
    label("Frontend", "フロントエンド"),
    label("Backend API", "バックエンド API"),
    label("uvicorn + email worker", "uvicorn + メールワーカー"),
    label("Database", "データベース"),
    label("records", "レコード"),
    label("Skill store", "スキルストア"),
    label("cloned repos", "クローン"),
    label("Secret key", "暗号化キー"),
    label("encrypts", "暗号化に使う"),
    ('<rect x="460" y="512" width="110" height="72"', '<rect x="448" y="512" width="130" height="72"'),
    ('<text x="515" y="552"', '<text x="513" y="552"'),
    label("LLM provider", "LLM プロバイダー"),
    label("MCP servers", "MCP サーバー"),
    label("SMTP relay", "SMTP リレー"),
    label("LEGEND", "凡例"),
    label("A2Flow component", "A2Flow の構成要素"),
    label("External system", "外部システム"),
    label("Data store", "データストア"),
]

# ---------------------------------------------------------------- operations/scaling-lock-race
SPECS["operations/scaling-lock-race"] = head(
    "One driver per conversation", "1 つの会話を動かすのは 1 つだけ",
    "Sequence diagram of two replicas racing to run the same session: Replica 1 takes a PostgreSQL advisory lock and opens the stream for Client A, while Replica 2's later request for the same session is refused with 409 while the lock is held, and the lock is released only when Replica 1's stream ends.",
    "2 つのレプリカが同じセッションを動かそうと競合するシーケンス図。レプリカ 1 が PostgreSQL のアドバイザリロックを取得してクライアント A にストリームを開き、ロックが保持されている間はレプリカ 2 への同じセッションのリクエストが 409 で拒否され、レプリカ 1 のストリームが終わったときにだけロックが解放される。",
) + [
    mask(401, 188, 78, 68, h=12),
    mask(621, 364, 78, 68, h=12),
    (">TAKE LOCK</text>", ">ロック取得</text>", 2),
    mask(401, 232, 78, 68, h=12),
    label("ACQUIRED", "取得できた"),
    mask(147, 276, 146, 124, h=12),
    label("SSE STREAM OPENS", "SSE ストリーム開始"),
    mask(609, 408, 102, 68, h=12),
    label("HELD ELSEWHERE", "他が保持中"),
    mask(833, 452, 94, 68, h=12),
    label("409 REFUSED", "409 で拒否"),
    mask(161, 496, 118, 92, h=12),
    label("STREAM ENDS", "ストリーム終了"),
    mask(401, 540, 78, 68, h=12),
    label("RELEASED", "ロック解放"),
    label("Client A", "クライアント A"),
    label("Replica 1", "レプリカ 1"),
    label("Replica 2", "レプリカ 2"),
    label("Client B", "クライアント B"),
    label("LEGEND", "凡例"),
    label("Call", "呼び出し"),
    label("Return", "返答"),
    label("Refused", "拒否"),
]

# ---------------------------------------------------------------- architecture/approvals-sequence
SPECS["architecture/approvals-sequence"] = head(
    "How an approval gate runs", "承認ゲートの動き",
    "Sequence diagram of an approval: the execution agent requests approval, A2Flow notifies the approver while the covered steps stay blocked, the approver decides, and A2Flow grants a certificate to each covered step as it starts and lets the run continue.",
    "承認のシーケンス図。実行エージェントが承認を依頼し、対象のステップが止まったまま A2Flow が承認者に通知する。承認者が決定すると、A2Flow は対象の各ステップに開始時に証明書を渡し、実行を続けさせる。",
) + [
    mask(222, 160, 116, 68, h=12),
    label("REQUEST APPROVAL", "承認を依頼"),
    mask(536, 220, 58, 32, h=12),
    label("NOTIFY", "通知"),
    mask(536, 280, 58, 32, h=12),
    label("DECIDE", "決定"),
    mask(222, 340, 116, 68, h=12),
    label("RUN CONTINUES", "実行が続く"),
    label("the covered steps", "対象のステップは"),
    label("stay blocked", "止まったまま"),
    label("a certificate is", "ステップごとに"),
    label("granted per step", "証明書が渡される"),
    label("Execution", "実行"),
    label("agent", "エージェント"),
    label("Approver", "承認者"),
    label("LEGEND", "凡例"),
    label("Call", "呼び出し"),
    label("Run continues", "実行の続行"),
]

# ---------------------------------------------------------------- architecture/approvals-step-coverage
SPECS["architecture/approvals-step-coverage"] = head(
    "What one approval covers", "1 つの承認が対象にする範囲",
    "Flowchart of a five-step task chain where Approval A covers the first three steps and Approval B takes over from the fourth step onward, showing that an approval covers its named step and everything after it up to the next approval.",
    "5 ステップのタスク連鎖のフローチャート。承認 A が最初の 3 ステップを対象にし、4 番目からは承認 B が引き継ぐ。承認は名指ししたステップと、次の承認までのそれ以降すべてを対象にする。",
) + [
    label("Approval A", "承認 A"),
    label("Approval B", "承認 B"),
    (">gate</text>", ">ゲート</text>", 2),
    label("Ask for a go-ahead", "承認を依頼する"),
    label("Launch instance", "インスタンス起動"),
    label("Tag instance", "インスタンスにタグ付け"),
    label("Ask again", "もう一度依頼する"),
    label("Delete snapshot", "スナップショット削除"),
    label("APPROVAL A COVERS", "承認 A の対象"),
    label("APPROVAL B COVERS", "承認 B の対象"),
    label("LEGEND", "凡例"),
    label("Approval gate", "承認ゲート"),
]

# ---------------------------------------------------------------- architecture/overview-lifecycle
SPECS["architecture/overview-lifecycle"] = head(
    "How a workflow moves", "ワークフローの流れ",
    "Flowchart showing an Agent Skill generated into a Workflow, run as a Workflow execution inside a Workflow session, whose Tasks request human approval or call an MCP tool through the MCP gateway to reach an MCP server.",
    "エージェントスキルからワークフローを生成し、ワークフローセッションの中でワークフロー実行として動かし、そのタスクが人の承認を求めるか、MCP ゲートウェイを通して MCP サーバーのツールを呼ぶことを示すフローチャート。",
) + [
    ('<rect x="508" y="118" width="90" height="12"', '<rect x="508" y="117" width="124" height="14"'),
    label("GENERATE", "ワークフローを生成"),
    ('<rect x="508" y="222" width="100" height="12"', '<rect x="508" y="221" width="88" height="14"'),
    label("PUBLISH/RUN", "公開して実行"),
    mask(315, 520, 120, 92, h=12),
    label("NEEDS A PERSON", "人の判断が要る"),
    mask(565, 520, 120, 80, h=12),
    label("NEEDS A TOOL", "ツールが要る"),
    mask(460, 560, 80, 44, h=12),
    label("CERTIFICATE", "証明書"),
    label("Agent Skill", "エージェントスキル"),
    label("a Git repository", "Git リポジトリ"),
    label("Workflow", "ワークフロー"),
    label("templates + tool bindings", "テンプレートとツールバインディング"),
    label("Workflow execution", "ワークフロー実行"),
    label("a snapshot of the design", "設計のスナップショット"),
    label("Workflow session", "ワークフローセッション"),
    label("the run's shared chat", "実行が進むチャット"),
    label("Tasks", "タスク"),
    label("one at a time", "1 つずつ"),
    label("Approval gate", "承認ゲート"),
    label("MCP gateway", "MCP ゲートウェイ"),
    label("MCP server", "MCP サーバー"),
]

# ---------------------------------------------------------------- architecture/secrets-resolution
SPECS["architecture/secrets-resolution"] = head(
    "How a secret reference resolves", "シークレット参照の解決",
    "Flowchart showing a name/key secret reference branching by storage type: local secrets are decrypted from the stored value, Vault secrets are read live, and both feed an MCP server connection or a skill repository clone.",
    "name/key のシークレット参照が保管の型で分岐することを示すフローチャート。local のシークレットは保管された値を復号し、Vault のシークレットはその場で読み、どちらも MCP サーバーへの接続かスキルのリポジトリのクローンに使われる。",
    page_title="Secret reference resolution", svg_title="Secret reference resolution",
) + [
    label("A reference", "参照"),
    label("Which type?", "どちらの型か"),
    label("Decrypt the", "保管された値を"),
    label("stored value", "復号する"),
    label("Read it live", "Vault から"),
    label("from Vault", "その場で読む"),
    label("MCP server connection", "MCP サーバーへの接続"),
    label("or a skill repository clone", "またはスキルのリポジトリのクローン"),
]

_POLICY_MASKS = [
    mask(612, 140, 56, 32, h=12),
    label("DENIED", "拒否"),
    mask(508, 234, 64, 32, h=12),
    label("ALLOWED", "許可"),
    mask(698, 300, 32, 32, h=12),
    label("YES", "はい"),
    mask(508, 390, 28, 44, h=12),
    label("NO", "いいえ"),
    label("calls a tool", "ツールを呼ぶ"),
    label("Policy chain", "ポリシーチェーン"),
    label("Refused", "拒否"),
    label("Mocked for", "この実行で"),
    label("this run?", "モックされている?"),
    label("Mock's response", "モックの次の応答"),
    label("no server contacted", "サーバーには届かない"),
    label("MCP server", "MCP サーバー"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-policy-chain
SPECS["architecture/mcp-gateway-and-proxy-policy-chain"] = head(
    "The policy chain", "ポリシーチェーン",
    "Flowchart showing how the MCP gateway decides a tool call: a policy chain either refuses it or allows it, an allowed call is either answered from a mock or goes through credential injection and the MCP proxy to the real MCP server, and both the refusal and the real call produce an audit record.",
    "MCP ゲートウェイがツール呼び出しをどう裁くかを示すフローチャート。ポリシーチェーンが拒否するか許可し、許可された呼び出しはモックが応答するか、資格情報の展開と MCP プロキシを経て本物の MCP サーバーに届く。拒否も本物の呼び出しも監査の記録を残す。",
    page_title="Policy chain", svg_title="Policy chain",
) + _POLICY_MASKS + [
    label("Execution agent", "実行エージェント"),
    label("lists what is allowed", "使えるツールの一覧が返る"),
    label("Credential injection", "資格情報の展開"),
    label("MCP proxy", "MCP プロキシ"),
    label("Audit record", "監査の記録"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-tool-mocks
SPECS["architecture/mcp-gateway-and-proxy-tool-mocks"] = head(
    "Where the mock sits", "モックの位置",
    "Flowchart showing that a tool mock is consulted only after the same policy chain a production call faces: a denied call is refused exactly as in production, and an allowed call is answered from a mock's next response or the real MCP server.",
    "ツールモックが参照されるのは、本番の呼び出しと同じポリシーチェーンを通ったあとだけだと示すフローチャート。拒否された呼び出しは本番とまったく同じように拒否され、許可された呼び出しはモックの次の応答か本物の MCP サーバーが応える。",
) + _POLICY_MASKS + [
    label("The agent", "エージェント"),
    label("exactly as production", "本番とまったく同じ"),
    label("the real side effect", "本物の副作用"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-trust-boundary
SPECS["architecture/mcp-gateway-and-proxy-trust-boundary"] = head(
    "Crossing the trust boundary", "信頼境界を越える",
    "Architecture diagram showing the MCP gateway, which decides whether a call is allowed, mocked, and which credentials it needs, handing exactly one authorized call across a trust boundary into the MCP proxy, which starts or connects to the real MCP server.",
    "呼び出しを許可するか、モックするか、どの資格情報が要るかを決める MCP ゲートウェイが、認可済みの呼び出しをちょうど 1 件だけ信頼境界を越えて MCP プロキシに渡し、MCP プロキシが本物の MCP サーバーを起動または接続することを示すアーキテクチャ図。",
) + [
    ('<rect x="52" y="64" width="112" height="12"', '<rect x="52" y="63" width="128" height="14"'),
    ('<text x="108" y="73"', '<text x="116" y="73"'),
    label("RUNS THE AGENT", "エージェントが動く側"),
    ('<rect x="412" y="64" width="64" height="12"', '<rect x="412" y="63" width="92" height="14"'),
    ('<text x="444" y="73"', '<text x="458" y="73"'),
    label("SANDBOX", "サンドボックス"),
    mask(328, 104, 84, 56, h=12),
    label("AUTHORIZED", "認可済み"),
    label("MCP gateway", "MCP ゲートウェイ"),
    label("allowed, mocked, credentials", "許可・モック・資格情報を決める"),
    label("MCP proxy", "MCP プロキシ"),
    label("starts or connects", "起動または接続"),
    label("MCP server", "MCP サーバー"),
    label("outside our control", "管理の外にある"),
    label("LEGEND", "凡例"),
    label("Trust boundary", "信頼境界"),
]

# ---------------------------------------------------------------- architecture/sessions-turn-flow
SPECS["architecture/sessions-turn-flow"] = head(
    "How a turn runs", "1 ターンの流れ",
    "Sequence diagram of one chat turn: the user's message travels from Frontend to Backend to the Model, the model's streamed reply and any render_a2ui surface flow back, and the user's filled-in surface makes the same round trip again.",
    "チャット 1 ターンのシーケンス図。ユーザーのメッセージがフロントエンド、バックエンド、モデルへ渡り、モデルのストリーム応答と render_a2ui のサーフェスが戻ってきて、ユーザーが埋めたサーフェスが同じ往復をもう一度する。",
) + [
    mask(190, 160, 100, 104, h=12),
    label("WRITES MESSAGE", "メッセージを書く"),
    mask(396, 200, 144, 168, h=12),
    label("MESSAGE + TOOL SCHEMA", "メッセージ + ツールスキーマ"),
    mask(626, 240, 132, 160, h=12),
    label("BRIDGE TO ADK AGENT", "ADK エージェントへ橋渡し"),
    mask(632, 280, 120, 156, h=12),
    label("TEXT + TOOL CALLS", "テキスト + ツール呼び出し"),
    mask(414, 320, 108, 80, h=12),
    label("STREAMED ONWARD", "そのまま流す"),
    mask(192, 360, 96, 104, h=12),
    label("DRAWS SURFACE", "サーフェスを描く"),
    mask(186, 400, 108, 68, h=12),
    label("FILLS + SUBMITS", "埋めて送信"),
    mask(414, 440, 108, 104, h=12),
    label("FULL DATA MODEL", "データモデル全体"),
    mask(638, 480, 108, 128, h=12),
    label("MATCHED TO CALL", "呼び出しと突き合わせ"),
    mask(412, 520, 112, 92, h=12),
    label("RESPONDS TO USER", "ユーザーに応答"),
    label("a render_a2ui call is", "render_a2ui の呼び出しは"),
    label("forwarded, never executed", "実行されず転送される"),
    label("User", "ユーザー"),
    label("Browser", "ブラウザ"),
    label("Frontend", "フロントエンド"),
    label("Backend", "バックエンド"),
    label("Model", "モデル"),
    label("LEGEND", "凡例"),
    label("Call", "呼び出し"),
    label("Streamed return", "ストリーム返答"),
    label("Response to user", "ユーザーへの応答"),
]

# ---------------------------------------------------------------- architecture/workflow-design-status
SPECS["architecture/workflow-design-status"] = head(
    "Workflow status lifecycle", "ワークフローのステータス遷移",
    "State machine showing a workflow moving from a published Agent Skill through generating to draft or failed, then from draft through published and modified, with publish looping back from modified.",
    "公開済みのエージェントスキルから generating を経て draft か failed になり、draft から published、modified へ進み、modified から公開で戻る、ワークフローの状態遷移図。",
) + [
    mask(196, 96, 48, 32, h=12),
    label("GENERATE", "生成"),
    mask(366, 180, 56, 80, h=12),
    label("NO STEPS", "ステップなし"),
    mask(568, 180, 48, 56, h=12),
    label("REVISED", "書き直し"),
    mask(596, 96, 48, 32, h=12),
    mask(676, 180, 48, 32, h=12),
    label("EDITED", "編集"),
    mask(736, 180, 48, 32, h=12),
    (">PUBLISH</text>", ">公開</text>", 2),
    label("Agent Skill", "エージェントスキル"),
    label("published revision", "公開済みのリビジョン"),
    label("design run in progress", "設計実行が進行中"),
    label("templates + bindings", "テンプレートと割り当て"),
    label("design is frozen", "設計が凍結される"),
    label("reason on record", "理由がレコードに残る"),
    label("runs use published", "実行は公開版を使う"),
    label("LEGEND", "凡例"),
    label("Precondition", "前提条件"),
    label("Status", "ステータス"),
    label("Live version", "実行に使われる版"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-snapshot
SPECS["architecture/workflow-execution-snapshot"] = head(
    "Running a workflow copies its design", "ワークフローの実行は設計を写す",
    "Flowchart showing a published workflow and its chosen tool mocks copied by value onto a new workflow execution snapshot, which opens a workflow session containing tasks that all start pending.",
    "公開版のワークフローと選ばれたツールモックが、新しいワークフロー実行のスナップショットに値のまま写され、開始時はすべて pending のタスクを持つワークフローセッションが開くことを示すフローチャート。",
    page_title="Running a workflow", svg_title="Running a workflow copies its design",
) + [
    mask(404, 136, 32, 32, h=12),
    label("RUN", "実行"),
    mask(556, 136, 96, 104, h=12),
    label("COPIED BY VALUE", "値のまま写される"),
    label("Workflow", "ワークフロー"),
    label("published version", "公開版"),
    label("Chosen tool mocks", "選ばれたツールモック"),
    label("test runs only", "テスト実行だけ"),
    label("Workflow execution", "ワークフロー実行"),
    label("the snapshot", "スナップショット"),
    label("Workflow session", "ワークフローセッション"),
    label("the run's chat", "実行が進むチャット"),
    label("Tasks", "タスク"),
    label("all pending at the start", "開始時はすべて pending"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-run-loop
SPECS["architecture/workflow-execution-run-loop"] = head(
    "How the run advances", "実行の進み方",
    "Flowchart showing the task-advancement loop: list tasks, pick one whose dependencies have completed, mark it in progress, do the work, mark it ended, and repeat until every task has ended and the run settles.",
    "タスクを進めるループのフローチャート。タスクを一覧し、依存が完了したものを選んで in_progress にし、作業して終了状態にする。全タスクが終わって実行が確定するまでこれを繰り返す。",
) + [
    mask(484, 222, 32, 32, h=12),
    label("YES", "ある"),
    mask(644, 154, 24, 32, h=12),
    label("NO", "ない"),
    label("List the run's tasks", "実行のタスクを一覧する"),
    label("A pending task whose", "依存が完了した"),
    label("deps have completed?", "pending タスクは?"),
    label("Mark it in_progress", "in_progress にする"),
    label("Do the work", "作業する"),
    label("tools, approvals, conversation", "ツール、承認、会話"),
    label("Mark it completed,", "completed、failed、"),
    label("failed, or skipped", "skipped のいずれかにする"),
    label("Run settles", "実行が確定する"),
    label("every task has ended", "全タスクが終わった"),
    label("LEGEND", "凡例"),
    label("Step (rectangle)", "ステップ(長方形)"),
    label("Decision (diamond)", "判断(ひし形)"),
    label("Loop exit (oval)", "ループの出口(楕円)"),
    label("Continues the loop", "ループを続ける"),
]
