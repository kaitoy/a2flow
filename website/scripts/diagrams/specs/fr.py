"""Per-diagram replacement specs: English light HTML -> French light HTML.

See :mod:`specs.common` for the entry format. Conventions the translations follow,
mirroring the French prose:

* node names, edge labels, notes and legends are French, addressed to the reader as *vous*
  where a sentence needs a person, with a non-breaking space before ``:``, ``;``, ``?``
  and ``!`` and straight apostrophes, as the GUI catalog writes them;
* status values and UI button names use the exact wording of the French GUI catalog
  (``frontend/src/i18n/messages/fr.ts``), e.g. ``brouillon``, ``en cours d'exécution``,
  ``Publier``, ``Désactiver``; a mono edge label keeps the English uppercase styling;
* technical strings (``name/key``, ``POST /AGENT``, ``HTTPS``) stay English;
* Latin labels keep the English font, so budget about 0.55em per Inter glyph and 0.6em per
  mono glyph plus letter-spacing, and 8px for a mask;
* a label too long for its box is first widened through replacements, moving the anchors so
  it stays centred and arrows still meet box edges; where the layout cannot give the width,
  it wraps on two lines with :func:`_two`;
* each ``<desc>`` equals the image's alt text on the French page.
"""

from specs.common import head, label, mask

SPECS: dict[str, list[tuple]] = {}


def _two(x: int, first: str, second: str, up: int = 9, gap: int = 17) -> str:
    """Build the content of a label that wraps on two lines.

    Args:
        x: The ``<text>`` element's ``x``, which both lines are anchored on.
        first: The first line.
        second: The second line.
        up: How far above the element's ``y`` the first baseline sits.
        gap: The distance between the two baselines.

    Returns:
        The two ``<tspan>`` elements, to pass as the ``new`` of :func:`specs.common.label`.
    """
    return f'<tspan x="{x}" dy="-{up}">{first}</tspan><tspan x="{x}" dy="{gap}">{second}</tspan>'


# ---------------------------------------------------------------- guides/secrets-usage
SPECS["guides/secrets-usage"] = head(
    "Where a secret entry is used", "Où une entrée de secret est utilisée",
    "Flowchart showing a secret's entry referenced either in an MCP server's headers and environment variables, or as an Agent Skill repository's auth password.",
    "Organigramme montrant l'entrée d'un secret référencée soit dans les en-têtes et variables d'environnement d'un serveur MCP, soit comme mot de passe d'authentification du dépôt d'une compétence d'agent.",
) + [
    ('viewBox="0 0 740 250"', 'viewBox="0 0 780 250"'),
    ('<rect x="480" y="20" width="220"', '<rect x="480" y="20" width="260"'),
    ('<rect x="480" y="160" width="220"', '<rect x="480" y="160" width="260"'),
    ('<text x="590" y="50"', '<text x="610" y="50"'),
    ('<text x="590" y="70"', '<text x="610" y="70"'),
    ('<text x="590" y="190"', '<text x="610" y="190"'),
    ('<text x="590" y="210"', '<text x="610" y="210"'),
    label("HEADERS", "EN-TÊTES"),
    ('<rect x="430" y="164" width="40"', '<rect x="368" y="164" width="108"'),
    ('<text x="450" y="175"', '<text x="422" y="175"'),
    label("AUTH", "AUTHENTIFICATION"),
    label("Entry", "Entrée"),
    label("MCP server", "Serveur MCP"),
    label("headers + env vars", "en-têtes + variables d'environnement"),
    label("Agent Skill", "Compétence d'agent"),
    label("repo auth password", "mot de passe d'authentification du dépôt"),
]

# ---------------------------------------------------------------- guides/admin-ui-navigation
SPECS["guides/admin-ui-navigation"] = head(
    "Admin UI navigation", "Navigation dans l'interface d'administration",
    "Flowchart of the admin UI navigation model: the welcome page leads to a section list, which opens a create form or a detail page by clicking a name, and a breadcrumb on the detail page returns to the list.",
    "Organigramme de la navigation dans l'interface d'administration : la page de bienvenue mène à la liste d'une section, d'où l'on ouvre un formulaire de création ou, en cliquant sur un nom, une page de détail ; le fil d'Ariane de la page de détail ramène à la liste.",
) + [
    label("NAME", "NOM"),
    ('<rect x="382" y="180" width="32"', '<rect x="376" y="180" width="54"'),
    ('<text x="398" y="191"', '<text x="403" y="191"'),
    label("ADD", "AJOUTER"),
    mask(476, 134, 72, 76),
    label("BREADCRUMB", "FIL D'ARIANE"),
    label("Welcome page", "Page de bienvenue"),
    label("quick-action cards", "cartes d'action rapide"),
    label("Section list", "Liste d'une section"),
    label("e.g. Workflows", "p. ex. Workflows"),
    label("Create form", "Formulaire de création"),
    label("Detail page", "Page de détail"),
    label("titled by name", "titrée d'après le nom"),
]

# ---------------------------------------------------------------- guides/agent-skills-lifecycle
SPECS["guides/agent-skills-lifecycle"] = head(
    "Agent Skill lifecycle", "Cycle de vie d'une compétence d'agent",
    "State machine showing an Agent Skill registered, cloning in the background, becoming ready or failed, pulling to retry from either state, and a ready skill generating a new workflow.",
    "Machine à états d'une compétence d'agent : une fois enregistrée, elle est clonée en arrière-plan, puis devient prête ou en échec ; une récupération permet de réessayer depuis l'un ou l'autre état, et une compétence prête permet de générer un nouveau workflow.",
) + [
    ('<rect x="376" y="176" width="40"', '<rect x="366" y="176" width="66"'),
    ('<text x="396" y="187"', '<text x="399" y="187"'),
    mask(394, 18, 52, 66),
    (">PULL</text>", ">RÉCUPÉRER</text>", 2),
    label("GENERATE", "GÉNÉRER"),
    label("Register", "Enregistrement"),
    label("returns immediately", "retour immédiat"),
    label("Cloning", "Clonage"),
    label("in the background", "en arrière-plan"),
    label("ready", "prêt"),
    label("revision published", "révision publiée"),
    label("failed", "échec"),
    label("reason on record", "motif consigné"),
    label("New workflow", "Nouveau workflow"),
]

# ---------------------------------------------------------------- guides/approvals-sequence
SPECS["guides/approvals-sequence"] = head(
    "Requesting a human approval", "Demander une approbation humaine",
    "Sequence diagram of an approval request: the execution agent asks for approval, A2Flow notifies the approver and the run pauses, the approver decides, and A2Flow grants a certificate to each covered step and resumes the run.",
    "Diagramme de séquence d'une demande d'approbation : l'agent d'exécution demande une approbation, A2Flow notifie l'approbateur et l'exécution se met en pause, l'approbateur décide, puis A2Flow accorde un certificat à chaque étape couverte et reprend l'exécution.",
) + [
    mask(221, 156, 118, 138),
    label("REQUEST APPROVAL", "DEMANDE D'APPROBATION"),
    label("NOTIFY", "NOTIFIE"),
    label("DECIDE", "DÉCIDE"),
    mask(238, 336, 84, 118),
    label("RUN RESUMES", "L'EXÉCUTION REPREND"),
    label("the whole run", "toute l'exécution"),
    label("pauses to wait", "se met en pause"),
    label("a certificate is", "un certificat est"),
    label("granted per step", "accordé par étape"),
    label("Execution", "Agent"),
    label("agent", "d'exécution"),
    label("Approver", "Approbateur"),
    label("LEGEND", "LÉGENDE"),
    label("Call", "Appel"),
    label("Run resumes", "Reprise de l'exécution"),
]

# ---------------------------------------------------------------- guides/notifications-routing
SPECS["guides/notifications-routing"] = head(
    "Where a notification goes", "Où va une notification",
    "Flowchart showing a workflow event routing to the one concerned user, or every eligible approver-group member, and fanning out to the bell, the Notifications page, and email if it is enabled.",
    "Organigramme montrant un événement de workflow acheminé vers l'utilisateur concerné, ou vers chaque membre éligible du groupe d'approbateurs, puis diffusé vers la cloche, la page Notifications et l'e-mail s'il est activé.",
) + [
    ('<rect x="260" y="40" width="180"', '<rect x="250" y="40" width="200"'),
    label("Workflow event", "Événement de workflow"),
    ('<rect x="250" y="160" width="200"', '<rect x="230" y="160" width="240"'),
    label("Concerned user(s)", "Utilisateur(s) concerné(s)"),
    label("or approver group", "ou groupe d'approbateurs"),
    label("Bell", "Cloche"),
    label("unread notifications", "notifications non lues"),
    label("Notifications page", "Page Notifications"),
    label("full history", "historique complet"),
    label("Email", "E-mail"),
    label("if enabled", "si activé"),
]

# ---------------------------------------------------------------- guides/tags-vocabulary
SPECS["guides/tags-vocabulary"] = head(
    "One vocabulary, seven registries", "Un vocabulaire, sept registres",
    "Flowchart showing one shared tag vocabulary per tenant applied to seven taggable registries: Secrets, MCP Servers, Agent Skills, Knowledge Bases, Workflows, Tool Mocks, and User Groups.",
    "Organigramme montrant un vocabulaire d'étiquettes commun par tenant, appliqué à sept registres étiquetables : Secrets, Serveurs MCP, Compétences d'agent, Bases de connaissances, Workflows, Simulacres d'outils et Groupes d'utilisateurs.",
    page_title="Tag vocabulary", svg_title="Tag vocabulary",
) + [
    label("Tag vocabulary", "Vocabulaire d'étiquettes"),
    label("one per tenant", "un par tenant"),
    label("MCP Servers", "Serveurs MCP"),
    label("Agent Skills", _two(358, "Compétences", "d'agent")),
    label("Knowledge Bases", _two(500, "Bases de", "connaissances")),
    label("Tool Mocks", _two(784, "Simulacres", "d'outils")),
    label("User Groups", _two(926, "Groupes", "d'utilisateurs")),
]

# ---------------------------------------------------------------- guides/tool-mocks-decision
SPECS["guides/tool-mocks-decision"] = head(
    "Where a tool mock intercepts", "Où un simulacre d'outil intervient",
    "Flowchart showing the agent calling a tool, checking whether it is mocked for this run, and either reaching the real MCP server or receiving the mock's next response with no server contacted.",
    "Organigramme montrant l'agent qui appelle un outil, vérifie si celui-ci est simulé pour cette exécution, puis atteint le véritable serveur MCP ou reçoit la réponse suivante du simulacre sans contacter aucun serveur.",
) + [
    mask(468, 148, 28, 32),
    label("NO", "NON"),
    label("YES", "OUI"),
    label("The agent", "L'agent"),
    label("calls a tool", "appelle un outil"),
    label("Mocked for", "Simulé pour"),
    label("this run?", "cette exécution ?"),
    label("MCP server", "Serveur MCP"),
    label("real side effect", "effet de bord réel"),
    ('<rect x="260" y="268" width="200"', '<rect x="230" y="268" width="260"'),
    label("Mock's next response", "Réponse suivante du simulacre"),
    label("no server contacted", "aucun serveur contacté"),
    label("LEGEND", "LÉGENDE"),
    label("Start / end", "Début / fin"),
    label("Decision", "Décision"),
]

# ---------------------------------------------------------------- guides/users-groups-relationship
SPECS["guides/users-groups-relationship"] = head(
    "Tenant, users, and groups", "Tenant, utilisateurs et groupes",
    "Flowchart showing a tenant containing users and user groups, group membership granting a user its group, and both the user's own roles and its groups' roles feeding the user's effective roles.",
    "Diagramme de flux montrant un tenant contenant des utilisateurs et des groupes d'utilisateurs, l'appartenance à un groupe rattachant l'utilisateur à ce groupe, et les rôles propres de l'utilisateur comme ceux de ses groupes alimentant ses rôles effectifs.",
) + [
    label("MEMBER", "MEMBRE"),
    (">ROLES</text>", ">RÔLES</text>", 2),
    label("org boundary", "limite de l'organisation"),
    label("User Group", "Groupe d'utilisateurs"),
    label("named bundle", "ensemble nommé"),
    label("User", "Utilisateur"),
    label("one account", "un compte"),
    label("Effective roles", "Rôles effectifs"),
]

# ---------------------------------------------------------------- guides/workflow-executions-status
SPECS["guides/workflow-executions-status"] = head(
    "Run status", "État de l'exécution",
    "State machine showing a run starting as running, moving to scheduled while it only waits on a time and back when it resumes, then settling completed once every task has ended with none failed, or failed once every task has ended with at least one failure.",
    "Diagramme d'états montrant une exécution qui démarre à l'état en cours d'exécution, passe à planifié tant qu'elle ne fait qu'attendre l'heure prévue, revient à en cours d'exécution à la reprise, puis se termine à l'état terminé une fois toutes les tâches achevées sans échec, ou à l'état échec une fois toutes les tâches achevées avec au moins un échec.",
) + [
    label("NONE FAILED", "AUCUN ÉCHEC"),
    label("1+ FAILED", "1+ ÉCHECS"),
    label("WAITS ON A TIME", "ATTEND L'HEURE"),
    label("RESUMES", "REPREND"),
    label("running", "en cours d'exécution"),
    label("scheduled", "planifié"),
    label("completed", "terminé"),
    label("failed", "échec"),
]

# ---------------------------------------------------------------- guides/workflow-executions-layout
SPECS["guides/workflow-executions-layout"] = head(
    "The workflow session screen", "L'écran de session du workflow",
    "Flowchart showing the workflow session screen layout: the task timeline and the messages grouped by task sit side by side, and messages lead into the chat input.",
    "Diagramme de flux montrant la disposition de l'écran de session du workflow : la chronologie des tâches et les messages regroupés par tâche sont côte à côte, et les messages mènent à la zone de saisie de la discussion.",
) + [
    label("Task timeline", "Chronologie des tâches"),
    label("collapsible, left edge", "repliable, bord gauche"),
    label("grouped by task", "regroupés par tâche"),
    label("Chat input", _two(640, "Zone de saisie", "de la discussion")),
]

# ---------------------------------------------------------------- guides/workflows-lifecycle
SPECS["guides/workflows-lifecycle"] = head(
    "From skill to running workflow", "De la compétence au workflow en cours d'exécution",
    "Flowchart showing an Agent Skill generating a Workflow, refined into an adjusted draft, published, and run as a Workflow execution.",
    "Diagramme de flux montrant une compétence d'agent qui génère un workflow, affiné en brouillon ajusté, publié, puis lancé sous forme d'exécution.",
) + [
    label("Agent Skill", _two(130, "Compétence", "d'agent")),
    label("AI-designed templates", "modèles conçus par l'IA"),
    label("Adjusted draft", "Brouillon ajusté"),
    label("Published", "Publié"),
    label("design is frozen", "conception figée"),
    # The English writes "Workflow / execution"; the word order flips, and the first
    # "Workflow" (the box at x=317) already reads the same in French.
    (
        """<text x="910" y="87" fill="#1c1e21" font-size="14" font-weight="600" font-family="'Inter', sans-serif" text-anchor="middle">Workflow</text>""",
        """<text x="910" y="87" fill="#1c1e21" font-size="14" font-weight="600" font-family="'Inter', sans-serif" text-anchor="middle">Exécution</text>""",
    ),
    label("execution", "du workflow"),
]

# ---------------------------------------------------------------- guides/workflows-status
SPECS["guides/workflows-status"] = head(
    "Detailed workflow status", "État détaillé d'un workflow",
    "State machine of a workflow's detailed status: generating leads to draft or failed, failed can be rewritten back to draft, draft publishes to published, published and modified toggle on further edits and publishes, and either can be deactivated back to draft.",
    "Diagramme d'états de l'état détaillé d'un workflow : génération en cours mène à brouillon ou échec, échec peut être réécrit pour revenir à brouillon, brouillon se publie en publié, publié et modifié alternent au gré des modifications et des publications, et l'un comme l'autre peuvent être désactivés pour revenir à brouillon.",
) + [
    label("FAILED", "ÉCHEC"),
    label("BY HAND", "À LA MAIN"),
    label("EDITED", "MODIFIÉ"),
    (">PUBLISH</text>", ">PUBLIER</text>", 2),
    (">DEACTIVATE</text>", ">DÉSACTIVER</text>", 2),
    label("generating", "génération en cours"),
    label("draft", "brouillon"),
    label("published", "publié"),
    label("modified", "modifié"),
    label("failed", "échec"),
]

# ---------------------------------------------------------------- guides/workflows-snapshot
SPECS["guides/workflows-snapshot"] = head(
    "Running a workflow makes a snapshot", "Exécuter un workflow crée un instantané",
    "Flowchart showing the published Workflow and its chosen tool mocks copied by value onto a new Workflow execution snapshot, which opens a Workflow session.",
    "Diagramme de flux montrant le workflow publié et les simulacres d'outils choisis, copiés par valeur dans un nouvel instantané d'exécution, qui ouvre une session du workflow.",
) + [
    ('<rect x="174" y="126" width="32"', '<rect x="166" y="126" width="60"'),
    ('<text x="190" y="137"', '<text x="196" y="137"'),
    label("RUN", "EXÉCUTER"),
    label("COPIED", "COPIÉS"),
    label("published version", "version publiée"),
    label("Chosen tool mocks", _two(400, "Simulacres", "d'outils choisis")),
    label("Workflow execution", "Exécution du workflow"),
    label("the snapshot", "l'instantané"),
    label("Workflow session", "Session du workflow"),
]

# ---------------------------------------------------------------- guides/workflows-tool-binding
SPECS["guides/workflows-tool-binding"] = head(
    "Tool binding: design time vs run time", "Liaison d'outil : à la conception et à l'exécution",
    "Flowchart showing a design-time tool binding copied at run onto the task, then checked at call time: if the tool is bound to an in-progress task the call goes through, otherwise it is refused with the tools that are allowed.",
    "Diagramme de flux montrant une liaison d'outil établie à la conception, copiée sur la tâche au lancement, puis vérifiée au moment de l'appel : si l'outil est lié à une tâche en cours, l'appel passe ; sinon, il est refusé avec la liste des outils autorisés.",
) + [
    label("COPIED", "COPIÉE"),
    label("YES", "OUI"),
    label("NO", "NON"),
    label("Design time", "À la conception"),
    label("binds server + tool", "lie serveur + outil"),
    label("Run time", "À l'exécution"),
    label("task carries binding", "la tâche porte la liaison"),
    label("Bound to a task", "Lié à une tâche"),
    label("in progress?", "en cours ?"),
    label("Goes through", "L'appel passe"),
    label("Refused", "Refusé"),
    label("lists what's allowed", "liste ce qui est autorisé"),
]

# ---------------------------------------------------------------- concepts/authorization-effective-roles
SPECS["concepts/authorization-effective-roles"] = head(
    "Resolving effective roles", "Résolution des rôles effectifs",
    "Flowchart showing direct role grants on the user record and roles inherited from user groups both feeding a user's effective roles, the union used by every authorization check.",
    "Organigramme montrant que les rôles accordés directement sur l'enregistrement de l'utilisateur et les rôles hérités des groupes d'utilisateurs alimentent ensemble les rôles effectifs de l'utilisateur, l'union utilisée par chaque contrôle d'autorisation.",
) + [
    label("GROUP", "GROUPE"),
    ('<rect x="40" y="40" width="200"', '<rect x="28" y="40" width="212"'),
    ('<rect x="40" y="160" width="200"', '<rect x="28" y="160" width="212"'),
    ('<text x="140" y="69"', '<text x="134" y="69"'),
    ('<text x="140" y="88"', '<text x="134" y="88"'),
    ('<text x="140" y="189"', '<text x="134" y="189"'),
    ('<text x="140" y="208"', '<text x="134" y="208"'),
    label("Direct grants", "Attributions directes"),
    label("on the user record", "sur l'enregistrement utilisateur"),
    label("Group grants", "Attributions de groupe"),
    label("inherited", "héritées"),
    label("Effective roles", "Rôles effectifs"),
    label("Every auth", "Chaque contrôle"),
    label("check", "d'autorisation"),
]

# ---------------------------------------------------------------- concepts/authorization-session-matrix
SPECS["concepts/authorization-session-matrix"] = head(
    "Who can reach which session", "Qui accède à quelle session",
    "Access matrix showing that Developers, the workflow's creator, and Super Admin reach a Design session, with Reviewers holding read-only access to it, while the run's initiator, its designated approvers, and Super Admin reach a Workflow session, with Admin holding read-only access to the Workflow session.",
    "Matrice d'accès montrant que les Développeurs, le créateur du workflow et le Super administrateur accèdent à une session de conception, les Relecteurs y ayant un accès en lecture seule, tandis que l'initiateur de l'exécution, ses approbateurs désignés et le Super administrateur accèdent à une session du workflow, l'Administrateur y ayant un accès en lecture seule.",
) + [
    # The Super Admin column widens to hold "Super administrateur".
    ('<rect x="1216" y="72" width="148"', '<rect x="1216" y="72" width="172"'),
    ('<rect x="1216" y="144" width="148"', '<rect x="1216" y="144" width="172"'),
    ('<rect x="1216" y="188" width="148"', '<rect x="1216" y="188" width="172"'),
    ('<text x="1290" y="94"', '<text x="1302" y="94"'),
    ('<text x="1290" y="112"', '<text x="1302" y="112"'),
    ('<text x="1290" y="168"', '<text x="1302" y="168"'),
    ('<text x="1290" y="212"', '<text x="1302" y="212"'),
    ('<line x1="12" y1="248" x2="1364"', '<line x1="12" y1="248" x2="1388"'),
    label("vs. actor", "selon l'acteur"),
    label("Developer", "Développeur"),
    label("Reviewer", "Relecteur"),
    (">any in tenant</text>", ">tous dans le tenant</text>", 2),
    label("Creator", "Créateur"),
    label("workflow's createdBy", "« Créé par » du workflow"),
    label("Initiator", "Initiateur"),
    label("started the run", "a lancé l'exécution"),
    label("Approver", "Approbateur"),
    label("designated for it", "désigné pour celle-ci"),
    label("Admin", "Administrateur"),
    label("tenant admin", "administrateur du tenant"),
    label("Super Admin", "Super administrateur"),
    label("unrestricted", "sans restriction"),
    label("Design session", "Session de conception"),
    label("Workflow session", "Session du workflow"),
    (">Yes</text>", ">Oui</text>", 6),
    (">No access</text>", ">Aucun accès</text>", 7),
    (">Read only</text>", ">Lecture seule</text>", 3),
    (">can't drive it</text>", ">ne peut pas la piloter</text>", 2),
    label("LEGEND", "LÉGENDE"),
    label("Full access", "Accès complet"),
]

# ---------------------------------------------------------------- operations/deployment-topology
SPECS["operations/deployment-topology"] = head(
    "Deployment topology", "Topologie de déploiement",
    "Architecture diagram showing the browser reaching a reverse proxy that routes API requests (/api/*) straight to the backend API and page requests to the frontend, and the backend API — which also runs the email worker — reaching durable state (database, skill store, secret key), external services (LLM provider, MCP servers), and an SMTP relay.",
    "Schéma d'architecture montrant le navigateur qui atteint un proxy inverse, lequel achemine les requêtes d'API (/api/*) directement vers l'API du backend et les requêtes de pages vers le frontend, et l'API du backend, qui exécute aussi le worker d'e-mails, qui atteint l'état durable (base de données, magasin de compétences, clé secrète), les services externes (fournisseur de LLM, serveurs MCP) et un relais SMTP.",
) + [
    label("DURABLE STATE", "ÉTAT DURABLE"),
    label("EXTERNAL SERVICES", "SERVICES EXTERNES"),
    label("Browser", "Navigateur"),
    label("Reverse proxy", "Proxy inverse"),
    label("load balancer", "répartiteur de charge"),
    label("chat UI", "interface de discussion"),
    label("Backend API", "API du backend"),
    label("uvicorn + email worker", "uvicorn + worker d'e-mails"),
    # The three durable-state boxes are 100px wide, so their names wrap and the sublabels drop.
    label("Database", _two(110, "Base de", "données", 11, 16)),
    ('<text x="110" y="558"', '<text x="110" y="566"'),
    label("records", "enregistrements"),
    label("Skill store", _two(220, "Magasin de", "compétences", 11, 16)),
    ('<text x="220" y="558"', '<text x="220" y="566"'),
    label("cloned repos", "dépôts clonés"),
    label("Secret key", _two(330, "Clé", "secrète", 11, 16)),
    ('<text x="330" y="558"', '<text x="330" y="566"'),
    label("encrypts", "chiffre"),
    label("LLM provider", _two(515, "Fournisseur", "de LLM", 8, 16)),
    label("MCP servers", "Serveurs MCP"),
    label("SMTP relay", "Relais SMTP"),
    label("LEGEND", "LÉGENDE"),
    label("A2Flow component", "Composant A2Flow"),
    label("External system", "Système externe"),
    label("Data store", "Magasin de données"),
]

# ---------------------------------------------------------------- operations/scaling-lock-race
SPECS["operations/scaling-lock-race"] = head(
    "One driver per conversation", "Un seul pilote par conversation",
    "Sequence diagram of two replicas racing to run the same session: Replica 1 takes a PostgreSQL advisory lock and opens the stream for Client A, while Replica 2's later request for the same session is refused with 409 while the lock is held, and the lock is released only when Replica 1's stream ends.",
    "Diagramme de séquence de deux réplicas en concurrence pour exécuter la même session : le réplica 1 prend un verrou consultatif PostgreSQL et ouvre le flux pour le client A, tandis que la requête ultérieure du réplica 2 pour la même session est refusée avec une erreur 409 tant que le verrou est détenu, et le verrou n'est libéré que lorsque le flux du réplica 1 se termine.",
) + [
    mask(401, 188, 78, 92, h=12),
    mask(621, 364, 78, 92, h=12),
    (">TAKE LOCK</text>", ">PREND LE VERROU</text>", 2),
    label("ACQUIRED", "ACQUIS"),
    label("SSE STREAM OPENS", "OUVERTURE DU FLUX SSE"),
    label("HELD ELSEWHERE", "DÉTENU AILLEURS"),
    label("409 REFUSED", "409 REFUSÉ"),
    label("STREAM ENDS", "FIN DU FLUX"),
    label("RELEASED", "LIBÉRÉ"),
    label("Replica 1", "Réplica 1"),
    label("Replica 2", "Réplica 2"),
    label("LEGEND", "LÉGENDE"),
    label("Call", "Appel"),
    label("Return", "Retour"),
    label("Refused", "Refusé"),
]

# ---------------------------------------------------------------- architecture/approvals-sequence
SPECS["architecture/approvals-sequence"] = head(
    "How an approval gate runs", "Déroulement d'une barrière d'approbation",
    "Sequence diagram of an approval: the execution agent requests approval, A2Flow notifies the approver while the covered steps stay blocked, the approver decides, and A2Flow grants a certificate to each covered step as it starts and lets the run continue.",
    "Diagramme de séquence d'une approbation : l'agent d'exécution demande une approbation, A2Flow notifie l'approbateur tandis que les étapes couvertes restent bloquées, l'approbateur statue, puis A2Flow accorde un certificat à chaque étape couverte à son démarrage et laisse l'exécution se poursuivre.",
) + [
    mask(222, 160, 116, 138, h=12),
    label("REQUEST APPROVAL", "DEMANDE D'APPROBATION"),
    label("NOTIFY", "NOTIFIE"),
    label("DECIDE", "STATUE"),
    mask(222, 340, 116, 128, h=12),
    label("RUN CONTINUES", "L'EXÉCUTION CONTINUE"),
    label("the covered steps", "les étapes couvertes"),
    label("stay blocked", "restent bloquées"),
    label("a certificate is", "un certificat est"),
    label("granted per step", "accordé par étape"),
    label("Execution", "Agent"),
    label("agent", "d'exécution"),
    label("Approver", "Approbateur"),
    label("LEGEND", "LÉGENDE"),
    label("Call", "Appel"),
    label("Run continues", "Poursuite de l'exécution"),
]

# ---------------------------------------------------------------- architecture/approvals-step-coverage
SPECS["architecture/approvals-step-coverage"] = head(
    "What one approval covers", "Ce que couvre une approbation",
    "Flowchart of a five-step task chain where Approval A covers the first three steps and Approval B takes over from the fourth step onward, showing that an approval covers its named step and everything after it up to the next approval.",
    "Organigramme d'une chaîne de cinq étapes où l'approbation A couvre les trois premières étapes et l'approbation B prend le relais à partir de la quatrième, montrant qu'une approbation couvre l'étape qu'elle nomme et tout ce qui suit jusqu'à la prochaine approbation.",
) + [
    label("Approval A", "Approbation A"),
    label("Approval B", "Approbation B"),
    (">gate</text>", ">barrière</text>", 2),
    label("Ask for a go-ahead", "Demander le feu vert"),
    label("Launch instance", "Lancer l'instance"),
    label("Tag instance", "Étiqueter l'instance"),
    label("Ask again", "Redemander"),
    label("Delete snapshot", _two(840, "Supprimer", "l'instantané", 9, 16)),
    label("APPROVAL A COVERS", "L'APPROBATION A COUVRE"),
    label("APPROVAL B COVERS", "L'APPROBATION B COUVRE"),
    label("LEGEND", "LÉGENDE"),
    label("Approval gate", "Barrière d'approbation"),
]

# ---------------------------------------------------------------- architecture/overview-lifecycle
SPECS["architecture/overview-lifecycle"] = head(
    "How a workflow moves", "Le parcours d'un workflow",
    "Flowchart showing an Agent Skill generated into a Workflow, run as a Workflow execution inside a Workflow session, whose Tasks request human approval or call an MCP tool through the MCP gateway to reach an MCP server.",
    "Organigramme montrant une compétence d'agent dont est généré un workflow, lancé sous forme d'exécution dans une session du workflow, dont les tâches demandent une approbation humaine ou appellent un outil MCP via la passerelle MCP pour atteindre un serveur MCP.",
) + [
    label("GENERATE", "GÉNÉRER"),
    ('<rect x="508" y="222" width="100"', '<rect x="508" y="222" width="112"'),
    label("PUBLISH/RUN", "PUBLIER/EXÉCUTER"),
    mask(315, 520, 120, 134, h=12),
    label("NEEDS A PERSON", "BESOIN D'UNE PERSONNE"),
    label("NEEDS A TOOL", "BESOIN D'UN OUTIL"),
    label("CERTIFICATE", "CERTIFICAT"),
    label("Agent Skill", "Compétence d'agent"),
    label("a Git repository", "un dépôt Git"),
    label("templates + tool bindings", "modèles + liaisons d'outils"),
    label("Workflow execution", "Exécution du workflow"),
    label("a snapshot of the design", "un instantané de la conception"),
    label("Workflow session", "Session du workflow"),
    label("the run's shared chat", "discussion partagée de l'exécution"),
    label("Tasks", "Tâches"),
    label("one at a time", "une à la fois"),
    # Keeps the right edge, where the certificate arrow starts.
    ('<rect x="200" y="552" width="180"', '<rect x="184" y="552" width="196"'),
    ('<text x="290" y="585"', '<text x="282" y="585"'),
    label("Approval gate", "Barrière d'approbation"),
    label("MCP gateway", "Passerelle MCP"),
    label("MCP server", "Serveur MCP"),
]

# ---------------------------------------------------------------- architecture/secrets-resolution
SPECS["architecture/secrets-resolution"] = head(
    "How a secret reference resolves", "Comment une référence de secret est résolue",
    "Flowchart showing a name/key secret reference branching by storage type: local secrets are decrypted from the stored value, Vault secrets are read live, and both feed an MCP server connection or a skill repository clone.",
    "Organigramme montrant une référence de secret qui se divise selon le type : local déchiffre la valeur stockée, vault la lit en direct depuis Vault, et les deux alimentent une connexion à un serveur MCP ou le clonage d'un dépôt de compétence.",
    page_title="Secret reference resolution", svg_title="Secret reference resolution",
) + [
    label("A reference", "Une référence"),
    label("Which type?", "Quel type ?"),
    label("Decrypt the", "Déchiffrer la"),
    label("stored value", "valeur stockée"),
    label("Read it live", "La lire en direct"),
    label("from Vault", "depuis Vault"),
    label("MCP server connection", "Connexion au serveur MCP"),
    label("or a skill repository clone", "ou clonage d'un dépôt de compétence"),
]

_POLICY_COMMON = [
    label("DENIED", "REFUSÉ"),
    label("ALLOWED", "AUTORISÉ"),
    label("YES", "OUI"),
    mask(508, 390, 28, 32, h=12),
    label("NO", "NON"),
    label("calls a tool", "appelle un outil"),
    label("Policy chain", "Chaîne de stratégies"),
    label("Refused", "Refusé"),
    label("Mocked for", "Simulé pour"),
    label("this run?", "cette exécution ?"),
    # The mock's box widens leftwards, so its arrow ends earlier.
    ('<line x1="608" y1="320" x2="820"', '<line x1="608" y1="320" x2="796"'),
    ('<rect x="820" y="292" width="160"', '<rect x="796" y="292" width="184"'),
    ('<text x="900" y="316"', '<text x="888" y="316"'),
    ('<text x="900" y="330"', '<text x="888" y="330"'),
    label("Mock's response", "Réponse du simulacre"),
    label("no server contacted", "aucun serveur contacté"),
    label("MCP server", "Serveur MCP"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-policy-chain
SPECS["architecture/mcp-gateway-and-proxy-policy-chain"] = head(
    "The policy chain", "La chaîne de stratégies",
    "Flowchart showing how the MCP gateway decides a tool call: a policy chain either refuses it or allows it, an allowed call is either answered from a mock or goes through credential injection and the MCP proxy to the real MCP server, and both the refusal and the real call produce an audit record.",
    "Organigramme de la chaîne de stratégies qui tranche un appel d'outil : les appels refusés sont rejetés avec l'indication de ce qui est autorisé, les appels autorisés reçoivent la réponse d'un simulacre ou passent par l'injection des identifiants et le proxy MCP pour atteindre le serveur MCP, et un refus comme un appel réel produisent un enregistrement d'audit.",
    page_title="Policy chain", svg_title="Policy chain",
) + _POLICY_COMMON + [
    label("Execution agent", "Agent d'exécution"),
    ('<rect x="680" y="132" width="160"', '<rect x="680" y="132" width="176"'),
    ('<text x="760" y="156"', '<text x="768" y="156"'),
    ('<text x="760" y="170"', '<text x="768" y="170"'),
    ('d="M760,188 L760,672 Q760,680 752,680', 'd="M768,188 L768,672 Q768,680 760,680'),
    label("lists what is allowed", "liste ce qui est autorisé"),
    ('<rect x="400" y="416" width="200"', '<rect x="382" y="416" width="236"'),
    label("Credential injection", "Injection des identifiants"),
    label("MCP proxy", "Proxy MCP"),
    ('<rect x="410" y="704" width="180"', '<rect x="400" y="704" width="200"'),
    label("Audit record", "Enregistrement d'audit"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-tool-mocks
SPECS["architecture/mcp-gateway-and-proxy-tool-mocks"] = head(
    "Where the mock sits", "Où se situe le simulacre",
    "Flowchart showing that a tool mock is consulted only after the same policy chain a production call faces: a denied call is refused exactly as in production, and an allowed call is answered from a mock's next response or the real MCP server.",
    "Organigramme montrant qu'un simulacre d'outil n'est consulté qu'après la même chaîne de stratégies qu'un appel en production : un appel refusé est rejeté exactement comme en production, et un appel autorisé reçoit la réponse suivante d'un simulacre ou celle du vrai serveur MCP.",
) + _POLICY_COMMON + [
    label("The agent", "L'agent"),
    ('<rect x="680" y="132" width="160"', '<rect x="680" y="132" width="192"'),
    ('<text x="760" y="156"', '<text x="776" y="156"'),
    ('<text x="760" y="170"', '<text x="776" y="170"'),
    label("exactly as production", "exactement comme en production"),
    label("the real side effect", "l'effet de bord réel"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-trust-boundary
SPECS["architecture/mcp-gateway-and-proxy-trust-boundary"] = head(
    "Crossing the trust boundary", "Franchir la frontière de confiance",
    "Architecture diagram showing the MCP gateway, which decides whether a call is allowed, mocked, and which credentials it needs, handing exactly one authorized call across a trust boundary into the MCP proxy, which starts or connects to the real MCP server.",
    "Schéma d'architecture montrant la passerelle MCP, qui décide si un appel est autorisé, simulé et de quels identifiants il a besoin, et qui remet exactement un appel autorisé à travers une frontière de confiance au proxy MCP, lequel démarre le vrai serveur MCP ou s'y connecte.",
) + [
    label("RUNS THE AGENT", "EXÉCUTE L'AGENT"),
    ('<rect x="412" y="64" width="64"', '<rect x="412" y="64" width="76"'),
    ('<text x="444" y="73"', '<text x="450" y="73"'),
    label("SANDBOX", "BAC À SABLE"),
    label("AUTHORIZED", "AUTORISÉ"),
    label("MCP gateway", "Passerelle MCP"),
    label("allowed, mocked, credentials", "autorisé, simulé, identifiants"),
    label("MCP proxy", "Proxy MCP"),
    label("starts or connects", "démarre ou se connecte"),
    label("MCP server", "Serveur MCP"),
    label("outside our control", "hors de notre contrôle"),
    label("LEGEND", "LÉGENDE"),
    label("Trust boundary", "Frontière de confiance"),
]

# ---------------------------------------------------------------- architecture/sessions-turn-flow
SPECS["architecture/sessions-turn-flow"] = head(
    "How a turn runs", "Déroulement d'un tour",
    "Sequence diagram of one chat turn: the user's message travels from Frontend to Backend to the Model, the model's streamed reply and any render_a2ui surface flow back, and the user's filled-in surface makes the same round trip again.",
    "Diagramme de séquence d'un tour de discussion : le message de l'utilisateur va de l'interface au backend puis au modèle, la réponse diffusée du modèle et toute surface render_a2ui reviennent, et la surface remplie par l'utilisateur refait le même aller-retour.",
) + [
    mask(190, 160, 100, 106, h=12),
    label("WRITES MESSAGE", "ÉCRIT UN MESSAGE"),
    mask(396, 200, 144, 162, h=12),
    label("MESSAGE + TOOL SCHEMA", "MESSAGE + SCHÉMA D'OUTILS"),
    mask(640, 240, 104, 150, h=12),
    label("BRIDGE TO AGENT", "PASSERELLE VERS L'AGENT"),
    mask(632, 280, 120, 150, h=12),
    label("TEXT + TOOL CALLS", "TEXTE + APPELS D'OUTILS"),
    label("STREAMED ONWARD", "TRANSMIS EN FLUX"),
    mask(192, 360, 96, 120, h=12),
    label("DRAWS SURFACE", "AFFICHE LA SURFACE"),
    label("FILLS + SUBMITS", "REMPLIT + ENVOIE"),
    mask(414, 440, 108, 162, h=12),
    label("FULL DATA MODEL", "MODÈLE DE DONNÉES COMPLET"),
    mask(638, 480, 108, 114, h=12),
    label("MATCHED TO CALL", "ASSOCIÉ À L'APPEL"),
    mask(412, 520, 112, 144, h=12),
    label("RESPONDS TO USER", "RÉPOND À L'UTILISATEUR"),
    label("a render_a2ui call is", "un appel render_a2ui est"),
    label("forwarded, never executed", "transmis, jamais exécuté"),
    label("User", "Utilisateur"),
    label("Browser", "Navigateur"),
    label("Frontend", "Interface"),
    label("chat UI", "de discussion"),
    label("Model", "Modèle"),
    label("LLM provider", "fournisseur de LLM"),
    label("LEGEND", "LÉGENDE"),
    label("Call", "Appel"),
    label("Streamed return", "Retour en flux"),
    label("Response to user", "Réponse à l'utilisateur"),
]

# ---------------------------------------------------------------- architecture/workflow-design-status
SPECS["architecture/workflow-design-status"] = head(
    "Workflow status lifecycle", "Cycle de vie de l'état d'un workflow",
    "State machine showing a workflow moving from a published Agent Skill through generating to draft or failed, then from draft through published and modified, with publish looping back from modified.",
    "Automate à états montrant un workflow qui part d'une compétence d'agent publiée, passe par génération en cours pour aboutir à brouillon ou échec, puis va de brouillon à publié et modifié, la publication ramenant de modifié à publié.",
) + [
    # These two arrows are 40px long; a wider mask would slip under the nodes painted later.
    ('<rect x="196" y="96" width="48"', '<rect x="202" y="96" width="36"'),
    ('<rect x="596" y="96" width="48"', '<rect x="602" y="96" width="36"'),
    label("GENERATE", "GÉNÉRER"),
    mask(366, 180, 56, 80, h=12),
    label("NO STEPS", "AUCUNE ÉTAPE"),
    label("REVISED", "RÉVISÉ"),
    label("EDITED", "MODIFIÉ"),
    (">PUBLISH</text>", ">PUBLIER</text>", 2),
    label("generating", "génération en cours"),
    label("draft", "brouillon"),
    label("published", "publié"),
    label("failed", "échec"),
    label("modified", "modifié"),
    label("Agent Skill", "Compétence d'agent"),
    label("published revision", "révision publiée"),
    label("design run in progress", "conception en cours"),
    label("templates + bindings", "modèles + liaisons"),
    label("design is frozen", "conception figée"),
    label("reason on record", "motif consigné"),
    label("runs use published", "version publiée exécutée"),
    label("LEGEND", "LÉGENDE"),
    label("Precondition", "Prérequis"),
    label("Status", "État"),
    label("Live version", "Version active"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-snapshot
SPECS["architecture/workflow-execution-snapshot"] = head(
    "Running a workflow copies its design", "Exécuter un workflow copie sa conception",
    "Flowchart showing a published workflow and its chosen tool mocks copied by value onto a new workflow execution snapshot, which opens a workflow session containing tasks that all start pending.",
    "Organigramme montrant un workflow publié et les simulacres d'outils choisis copiés dans un nouvel instantané d'exécution, qui ouvre une session du workflow avec toutes les tâches en attente au départ.",
    page_title="Running a workflow",
) + [
    ('<rect x="404" y="136" width="32"', '<rect x="388" y="136" width="60"'),
    ('<text x="420" y="145"', '<text x="418" y="145"'),
    label("RUN", "EXÉCUTER"),
    ('<rect x="556" y="136" width="96"', '<rect x="542" y="136" width="110"'),
    ('<text x="604" y="145"', '<text x="597" y="145"'),
    label("COPIED BY VALUE", "COPIÉS PAR VALEUR"),
    label("published version", "version publiée"),
    ('<rect x="560" y="60" width="200"', '<rect x="540" y="60" width="240"'),
    label("Chosen tool mocks", "Simulacres d'outils choisis"),
    label("test runs only", "exécutions de test uniquement"),
    label("Workflow execution", "Exécution du workflow"),
    label("the snapshot", "l'instantané"),
    label("Workflow session", "Session du workflow"),
    label("the run's chat", "la discussion de l'exécution"),
    label("Tasks", "Tâches"),
    label("all pending at the start", "toutes en attente au départ"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-run-loop
SPECS["architecture/workflow-execution-run-loop"] = head(
    "How the run advances", "Comment l'exécution progresse",
    "Flowchart showing the task-advancement loop: list tasks, pick one whose dependencies have completed, mark it in progress, do the work, mark it ended, and repeat until every task has ended and the run settles.",
    "Organigramme de la boucle de progression de l'exécution : lister les tâches de l'exécution, en choisir une dont les dépendances sont terminées, la marquer en cours, effectuer le travail, la marquer terminée, en échec ou ignorée, puis recommencer ou conclure une fois toutes les tâches achevées.",
) + [
    # The whole column widens, and the loop arrow follows its left edge.
    ('<rect x="400" y="40" width="200"', '<rect x="370" y="40" width="260"'),
    ('<rect x="400" y="256" width="200"', '<rect x="370" y="256" width="260"'),
    ('<rect x="400" y="344" width="200"', '<rect x="370" y="344" width="260"'),
    ('<rect x="400" y="432" width="200"', '<rect x="370" y="432" width="260"'),
    ('d="M400,464 L168,464 Q160,464 160,456 L160,72 Q160,64 168,64 L400,64"', 'd="M370,464 L168,464 Q160,464 160,456 L160,72 Q160,64 168,64 L370,64"'),
    # So does the diamond, and the NO label stays centred on its now shorter arrow.
    ('points="500,112 600,160 500,208 400,160"', 'points="500,112 640,160 500,208 360,160"'),
    ('<line x1="600" y1="160" x2="720"', '<line x1="640" y1="160" x2="720"'),
    ('<rect x="644" y="154" width="24"', '<rect x="664" y="154" width="32"'),
    ('<text x="656" y="163"', '<text x="680" y="163"'),
    label("YES", "OUI"),
    label("NO", "NON"),
    label("List the run's tasks", "Lister les tâches de l'exécution"),
    label("A pending task whose", "Une tâche en attente"),
    label("deps have completed?", "aux dépendances terminées ?"),
    label("Mark it in_progress", "La marquer en cours"),
    label("Do the work", "Effectuer le travail"),
    label("tools, approvals, conversation", "outils, approbations, conversation"),
    label("Mark it completed,", "La marquer terminée,"),
    label("failed, or skipped", "en échec ou ignorée"),
    label("Run settles", "L'exécution se conclut"),
    label("every task has ended", "toutes les tâches achevées"),
    label("LEGEND", "LÉGENDE"),
    label("Step (rectangle)", "Étape (rectangle)"),
    label("Decision (diamond)", "Décision (losange)"),
    label("Loop exit (oval)", "Sortie de boucle (ovale)"),
    label("Continues the loop", "Poursuit la boucle"),
]
