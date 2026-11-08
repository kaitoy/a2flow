"""Per-diagram replacement specs: English light HTML -> Spanish light HTML.

See :mod:`specs.common` for the entry format. Conventions the translations follow,
mirroring the Spanish prose of the manual:

* node names, edge labels, notes and legends are Spanish, in infinitives or third person,
  so no ``tú`` form appears on a diagram even though the GUI catalog addresses the reader
  that way;
* status values and UI button names use the exact wording of the Spanish GUI catalog
  (``frontend/src/i18n/messages/es.ts``), e.g. ``borrador``, ``en ejecución``, ``Publicar``,
  ``Desactivar``, and core terms follow the glossary in ``frontend/README.md``;
* technical strings (``name/key``, ``POST /AGENT``, ``HTTPS``) stay English;
* labels keep the English styling, so an edge label stays uppercase 9px mono and its mask is
  widened with :func:`specs.common.mask` - budget 0.6em plus letter-spacing per glyph and
  8px of padding;
* a node name too long for its box either wraps with :func:`_node` or widens the box around
  the same centre, so the arrows still meet its edges.
"""

from specs.common import head, label, mask

SPECS: dict[str, list[tuple]] = {}


def _node(x: int, y: int, text: str, size: int = 14) -> str:
    """Render a semibold, centred node-name ``<text>`` exactly as the English sources write it.

    Args:
        x: The anchor's ``x``.
        y: The baseline's ``y``.
        text: The label.
        size: The font size.

    Returns:
        The element's markup, for matching an English label or inserting a wrapped line.
    """
    return (
        f'<text x="{x}" y="{y}" fill="#1c1e21" font-size="{size}" font-weight="600" '
        f"font-family=\"'Inter', sans-serif\" text-anchor=\"middle\">{text}</text>"
    )


# ---------------------------------------------------------------- guides/secrets-usage
SPECS["guides/secrets-usage"] = head(
    "Where a secret entry is used", "Dónde se usa una entrada de un secreto",
    "Flowchart showing a secret's entry referenced either in an MCP server's headers and environment variables, or as an Agent Skill repository's auth password.",
    "Diagrama de flujo que muestra cómo se hace referencia a una entrada de un secreto, ya sea en los encabezados y las variables de entorno de un servidor MCP, o como contraseña de autenticación del repositorio de una skill de agente.",
) + [
    # Both edge labels slide left of the elbow, so they clear the boxes they point at.
    ('<rect x="423" y="56" width="54" height="14"', '<rect x="410" y="58" width="68" height="12"'),
    ('<text x="450" y="67"', '<text x="444" y="67"'),
    label("HEADERS", "ENCABEZADOS"),
    ('<rect x="430" y="164" width="40" height="14"', '<rect x="397" y="164" width="84" height="14"'),
    ('<text x="450" y="175"', '<text x="439" y="175"'),
    ('letter-spacing="0.10em">AUTH</text>', 'letter-spacing="0.02em">AUTENTICACIÓN</text>'),
    label("Secret", "Secreto"),
    label("Entry", "Entrada"),
    # The two right-hand boxes grow to the right; their arrows still meet the left edge.
    ('<rect x="480" y="20" width="220"', '<rect x="480" y="20" width="236"'),
    ('<text x="590" y="50"', '<text x="598" y="50"'),
    ('<text x="590" y="70"', '<text x="598" y="70"'),
    label("MCP server", "Servidor MCP"),
    label("headers + env vars", "encabezados + variables de entorno"),
    ('<rect x="480" y="160" width="220"', '<rect x="480" y="160" width="236"'),
    ('<text x="590" y="190"', '<text x="598" y="190"'),
    ('<text x="590" y="210"', '<text x="598" y="210"'),
    label("Agent Skill", "Skill de agente"),
    label("repo auth password", "contraseña de autenticación del repo"),
]

# ---------------------------------------------------------------- guides/admin-ui-navigation
SPECS["guides/admin-ui-navigation"] = head(
    "Admin UI navigation", "Navegación de la interfaz de administración",
    "Flowchart of the admin UI navigation model: the welcome page leads to a section list, which opens a create form or a detail page by clicking a name, and a breadcrumb on the detail page returns to the list.",
    "Diagrama de flujo del modelo de navegación de la interfaz de administración: la página de bienvenida lleva a la lista de una sección, desde la que se abre un formulario de creación o, al hacer clic en un nombre, una página de detalle; la ruta de navegación de la página de detalle devuelve a la lista.",
) + [
    mask(382, 180, 32, 46),
    label("ADD", "AÑADIR"),
    # The detail box moves right and narrows, opening a 130px gap for RUTA DE NAVEGACIÓN.
    ('<line x1="460" y1="104" x2="560" y2="104"', '<line x1="460" y1="104" x2="590" y2="104"'),
    ('<line x1="560" y1="128" x2="460" y2="128"', '<line x1="590" y1="128" x2="460" y2="128"'),
    ("L652,196 Q660,196 660,188 L660,152", "L672,196 Q680,196 680,188 L680,152"),
    ('<rect x="492" y="84" width="40" height="14"', '<rect x="502" y="84" width="46" height="14"'),
    ('<text x="512" y="95"', '<text x="525" y="95"'),
    label("NAME", "NOMBRE"),
    ('<rect x="476" y="134" width="72" height="14"', '<rect x="471" y="134" width="108" height="14"'),
    ('<text x="512" y="145"', '<text x="525" y="145"'),
    label("BREADCRUMB", "RUTA DE NAVEGACIÓN"),
    label("Welcome page", "Página de bienvenida"),
    label("quick-action cards", "tarjetas de acción rápida"),
    label("Section list", "Lista de la sección"),
    label("e.g. Workflows", "p. ej., Flujos de trabajo"),
    label("Create form", "Formulario de creación"),
    ('<rect x="560" y="80" width="200"', '<rect x="590" y="80" width="180"'),
    ('<text x="660" y="110"', '<text x="680" y="110"'),
    ('<text x="660" y="130"', '<text x="680" y="130"'),
    label("Detail page", "Página de detalle"),
    label("titled by name", "con el nombre como título"),
]

# ---------------------------------------------------------------- guides/agent-skills-lifecycle
SPECS["guides/agent-skills-lifecycle"] = head(
    "Agent Skill lifecycle", "Ciclo de vida de una skill de agente",
    "State machine showing an Agent Skill registered, cloning in the background, becoming ready or failed, pulling to retry from either state, and a ready skill generating a new workflow.",
    "Diagrama de estados que muestra cómo una skill de agente se registra, se clona en segundo plano, pasa a estar lista o fallida, se actualiza para reintentarlo desde cualquiera de los dos estados y, una vez lista, genera un nuevo flujo de trabajo.",
) + [
    ('<rect x="376" y="176" width="40" height="14"', '<rect x="366" y="175" width="68" height="16"'),
    ('<text x="396" y="187"', '<text x="400" y="187"'),
    mask(394, 18, 52, 70),
    (">PULL</text>", ">ACTUALIZAR</text>", 2),
    label("GENERATE", "GENERAR"),
    label("Register", "Registrar"),
    label("returns immediately", "responde de inmediato"),
    label("Cloning", "Clonando"),
    label("in the background", "en segundo plano"),
    label("ready", "listo"),
    label("revision published", "revisión publicada"),
    label("failed", "fallido"),
    label("reason on record", "motivo registrado"),
    ('<rect x="440" y="220" width="160" height="56"', '<rect x="430" y="220" width="180" height="56"'),
    label("New workflow", "Nuevo flujo de trabajo"),
]

# ---------------------------------------------------------------- guides/approvals-sequence
SPECS["guides/approvals-sequence"] = head(
    "Requesting a human approval", "Solicitar una aprobación humana",
    "Sequence diagram of an approval request: the execution agent asks for approval, A2Flow notifies the approver and the run pauses, the approver decides, and A2Flow grants a certificate to each covered step and resumes the run.",
    "Diagrama de secuencia de una solicitud de aprobación: el agente de ejecución solicita la aprobación, A2Flow notifica al aprobador y la ejecución se detiene, el aprobador decide, y A2Flow concede un certificado a cada paso cubierto y reanuda la ejecución.",
) + [
    mask(221, 156, 118, 130),
    label("REQUEST APPROVAL", "SOLICITAR APROBACIÓN"),
    mask(539, 216, 52, 66),
    label("NOTIFY", "NOTIFICAR"),
    mask(238, 336, 84, 142),
    label("RUN RESUMES", "LA EJECUCIÓN SE REANUDA"),
    label("the whole run", "toda la ejecución"),
    label("pauses to wait", "se detiene a esperar"),
    label("a certificate is", "se concede un certificado"),
    label("granted per step", "a cada paso"),
    label("Execution", "Agente de"),
    label("agent", "ejecución"),
    label("Approver", "Aprobador"),
    label("LEGEND", "LEYENDA"),
    label("Call", "Llamada"),
    label("Run resumes", "La ejecución se reanuda"),
]

# ---------------------------------------------------------------- guides/notifications-routing
SPECS["guides/notifications-routing"] = head(
    "Where a notification goes", "Adónde va una notificación",
    "Flowchart showing a workflow event routing to the one concerned user, or every eligible approver-group member, and fanning out to the bell, the Notifications page, and email if it is enabled.",
    "Diagrama de flujo que muestra cómo un evento de flujo de trabajo se dirige al único usuario afectado, o a todos los miembros aptos del grupo de aprobadores, y se reparte entre la campana, la página de notificaciones y, si está habilitado, el correo electrónico.",
) + [
    ('<rect x="260" y="40" width="180" height="56"', '<rect x="235" y="40" width="230" height="56"'),
    label("Workflow event", "Evento del flujo de trabajo"),
    label("Concerned user(s)", "Usuarios afectados"),
    label("or approver group", "o grupo de aprobadores"),
    label("Bell", "Campana"),
    label("unread notifications", "notificaciones sin leer"),
    ('<rect x="270" y="300" width="160" height="72"', '<rect x="256" y="300" width="188" height="72"'),
    label("Notifications page", "Página de notificaciones"),
    label("full history", "historial completo"),
    label("Email", "Correo electrónico"),
    label("if enabled", "si está habilitado"),
]

# ---------------------------------------------------------------- guides/tags-vocabulary
SPECS["guides/tags-vocabulary"] = head(
    "One vocabulary, seven registries", "Un vocabulario, siete catálogos",
    "Flowchart showing one shared tag vocabulary per tenant applied to seven taggable registries: Secrets, MCP Servers, Agent Skills, Knowledge Bases, Workflows, Tool Mocks, and User Groups.",
    "Diagrama de flujo que muestra un único vocabulario de etiquetas compartido por tenant, aplicado a siete catálogos etiquetables: Secretos, Servidores MCP, Skills de agente, Bases de conocimiento, Flujos de trabajo, Mocks de herramientas y Grupos de usuarios.",
    page_title="Tag vocabulary", svg_title="Tag vocabulary",
) + [
    label("Tag vocabulary", "Vocabulario de etiquetas"),
    label("one per tenant", "uno por tenant"),
    label("Secrets", "Secretos"),
    (_node(216, 272, "MCP Servers"), _node(216, 263, "Servidores") + _node(216, 280, "MCP")),
    (_node(358, 272, "Agent Skills"), _node(358, 263, "Skills de") + _node(358, 280, "agente")),
    (_node(500, 272, "Knowledge Bases"), _node(500, 263, "Bases de") + _node(500, 280, "conocimiento")),
    (_node(642, 272, "Workflows"), _node(642, 263, "Flujos de") + _node(642, 280, "trabajo")),
    (_node(784, 272, "Tool Mocks"), _node(784, 263, "Mocks de") + _node(784, 280, "herramientas")),
    (_node(926, 272, "User Groups"), _node(926, 263, "Grupos de") + _node(926, 280, "usuarios")),
]

# ---------------------------------------------------------------- guides/tool-mocks-decision
SPECS["guides/tool-mocks-decision"] = head(
    "Where a tool mock intercepts", "Dónde intercepta un mock de herramienta",
    "Flowchart showing the agent calling a tool, checking whether it is mocked for this run, and either reaching the real MCP server or receiving the mock's next response with no server contacted.",
    "Diagrama de flujo que muestra cómo el agente llama a una herramienta, comprueba si está simulada en esta ejecución y, o bien llega al servidor MCP real, o bien recibe la siguiente respuesta del mock sin contactar con ningún servidor.",
) + [
    label("YES", "SÍ"),
    label("The agent", "El agente"),
    label("calls a tool", "llama a una herramienta"),
    label("Mocked for", "¿Simulada en"),
    label("this run?", "esta ejecución?"),
    label("MCP server", "Servidor MCP"),
    label("real side effect", "efecto secundario real"),
    ('<rect x="260" y="268" width="200" height="72"', '<rect x="235" y="268" width="250" height="72"'),
    label("Mock's next response", "Siguiente respuesta del mock"),
    label("no server contacted", "sin contactar con ningún servidor"),
    label("LEGEND", "LEYENDA"),
    label("Start / end", "Inicio / fin"),
    label("Decision", "Decisión"),
]

# ---------------------------------------------------------------- guides/users-groups-relationship
SPECS["guides/users-groups-relationship"] = head(
    "Tenant, users, and groups", "Tenant, usuarios y grupos",
    "Flowchart showing a tenant containing users and user groups, group membership granting a user its group, and both the user's own roles and its groups' roles feeding the user's effective roles.",
    "Diagrama de flujo que muestra un tenant que contiene usuarios y grupos de usuarios, la pertenencia que vincula a un usuario con su grupo, y cómo tanto los roles propios del usuario como los de sus grupos conforman sus roles efectivos.",
) + [
    label("MEMBER", "MIEMBRO"),
    label("org boundary", "límite de la organización"),
    label("User Group", "Grupo de usuarios"),
    label("named bundle", "conjunto con nombre"),
    label("User", "Usuario"),
    label("one account", "una cuenta"),
    label("Effective roles", "Roles efectivos"),
]

# ---------------------------------------------------------------- guides/workflow-executions-status
SPECS["guides/workflow-executions-status"] = head(
    "Run status", "Estado de la ejecución",
    "State machine showing a run starting as running, moving to scheduled while it only waits on a time and back when it resumes, then settling completed once every task has ended with none failed, or failed once every task has ended with at least one failure.",
    "Máquina de estados que muestra una ejecución que empieza en ejecución, pasa a programado mientras solo espera a que llegue una hora concreta y vuelve al reanudarse, y termina en completado cuando todas las tareas han finalizado sin fallos, o en fallido cuando todas han finalizado con al menos un fallo.",
) + [
    label("WAITS ON A TIME", "ESPERA UNA HORA"),
    mask(475, 89, 60, 66),
    label("RESUMES", "SE REANUDA"),
    label("NONE FAILED", "SIN FALLOS"),
    label("1+ FAILED", "1+ FALLOS"),
    label("running", "en ejecución"),
    label("scheduled", "programado"),
    label("completed", "completado"),
    label("failed", "fallido"),
]

# ---------------------------------------------------------------- guides/workflow-executions-layout
SPECS["guides/workflow-executions-layout"] = head(
    "The workflow session screen", "La pantalla de la sesión del flujo de trabajo",
    "Flowchart showing the workflow session screen layout: the task timeline and the messages grouped by task sit side by side, and messages lead into the chat input.",
    "Diagrama de flujo que muestra la disposición de la pantalla de la sesión del flujo de trabajo: la cronología de tareas y los mensajes agrupados por tarea están uno junto al otro, y los mensajes conducen a la entrada del chat.",
) + [
    label("Task timeline", "Cronología de tareas"),
    label("collapsible, left edge", "contraíble, borde izquierdo"),
    label("Messages", "Mensajes"),
    label("grouped by task", "agrupados por tarea"),
    label("Chat input", "Entrada del chat"),
]

# ---------------------------------------------------------------- guides/workflows-lifecycle
SPECS["guides/workflows-lifecycle"] = head(
    "From skill to running workflow", "De la skill al flujo de trabajo en ejecución",
    "Flowchart showing an Agent Skill generating a Workflow, refined into an adjusted draft, published, and run as a Workflow execution.",
    "Diagrama de flujo que muestra una skill de agente que genera un flujo de trabajo, que se refina en un borrador ajustado, se publica y se ejecuta como una ejecución del flujo de trabajo.",
) + [
    label("Agent Skill", "Skill de agente"),
    # The workflow box grows around its centre, shortening its two arrows.
    ('<line x1="200" y1="94" x2="232" y2="94"', '<line x1="200" y1="94" x2="226" y2="94"'),
    ('<line x1="402" y1="94" x2="434" y2="94"', '<line x1="408" y1="94" x2="434" y2="94"'),
    ('<rect x="232" y="60" width="170" height="68"', '<rect x="226" y="60" width="182" height="68"'),
    (_node(317, 87, "Workflow"), _node(317, 87, "Flujo de trabajo")),
    label("AI-designed templates", "plantillas diseñadas por IA"),
    label("Adjusted draft", "Borrador ajustado"),
    label("Published", "Publicado"),
    label("design is frozen", "diseño congelado"),
    (_node(910, 87, "Workflow"), _node(910, 87, "Ejecución del")),
    label("execution", "flujo de trabajo"),
]

# ---------------------------------------------------------------- guides/workflows-status
SPECS["guides/workflows-status"] = head(
    "Detailed workflow status", "Estado detallado del flujo de trabajo",
    "State machine of a workflow's detailed status: generating leads to draft or failed, failed can be rewritten back to draft, draft publishes to published, published and modified toggle on further edits and publishes, and either can be deactivated back to draft.",
    "Máquina de estados del estado detallado de un flujo de trabajo: generando lleva a borrador o a fallido, fallido se puede reescribir para volver a borrador, borrador se publica y pasa a publicado, publicado y modificado se alternan con nuevas ediciones y publicaciones, y cualquiera de los dos se puede desactivar para volver a borrador.",
) + [
    label("FAILED", "FALLIDO"),
    label("BY HAND", "A MANO"),
    label("EDITED", "EDITADO"),
    mask(445, 70, 50, 56),
    (">PUBLISH</text>", ">PUBLICAR</text>", 2),
    (">DEACTIVATE</text>", ">DESACTIVAR</text>", 2),
    label("generating", "generando"),
    label("draft", "borrador"),
    label("published", "publicado"),
    label("modified", "modificado"),
    label("failed", "fallido"),
]

# ---------------------------------------------------------------- guides/workflows-snapshot
SPECS["guides/workflows-snapshot"] = head(
    "Running a workflow makes a snapshot", "Ejecutar un flujo de trabajo crea una instantánea",
    "Flowchart showing the published Workflow and its chosen tool mocks copied by value onto a new Workflow execution snapshot, which opens a Workflow session.",
    "Diagrama de flujo que muestra el flujo de trabajo publicado y los mocks de herramientas elegidos copiados por valor en la instantánea de una nueva ejecución, que abre una sesión del flujo de trabajo.",
) + [
    ('<rect x="174" y="126" width="32" height="14"', '<rect x="168" y="126" width="58" height="14"'),
    ('<text x="190" y="137"', '<text x="197" y="137"'),
    label("RUN", "EJECUTAR"),
    label("COPIED", "COPIADO"),
    label("Workflow", "Flujo de trabajo"),
    label("published version", "versión publicada"),
    (_node(400, 82, "Chosen tool mocks"), _node(400, 68, "Mocks de herramienta") + _node(400, 86, "elegidos")),
    ('<rect x="180" y="160" width="200" height="68"', '<rect x="155" y="160" width="250" height="68"'),
    label("Workflow execution", "Ejecución del flujo de trabajo"),
    label("the snapshot", "la instantánea"),
    ('<rect x="180" y="280" width="200" height="56"', '<rect x="155" y="280" width="250" height="56"'),
    label("Workflow session", "Sesión del flujo de trabajo"),
]

# ---------------------------------------------------------------- guides/workflows-tool-binding
SPECS["guides/workflows-tool-binding"] = head(
    "Tool binding: design time vs run time", "Vinculación de herramientas: diseño frente a ejecución",
    "Flowchart showing a design-time tool binding copied at run onto the task, then checked at call time: if the tool is bound to an in-progress task the call goes through, otherwise it is refused with the tools that are allowed.",
    "Diagrama de flujo que muestra una vinculación de herramienta en tiempo de diseño copiada a la tarea al ejecutar y comprobada al llamar: si la herramienta está vinculada a una tarea en curso, la llamada pasa; de lo contrario, se rechaza indicando las herramientas permitidas.",
) + [
    label("COPIED", "COPIADA"),
    label("YES", "SÍ"),
    label("Design time", "Tiempo de diseño"),
    label("binds server + tool", "vincula servidor + herramienta"),
    label("Run time", "Tiempo de ejecución"),
    label("task carries binding", "la tarea lleva la vinculación"),
    label("Bound to a task", "¿Vinculada a una"),
    label("in progress?", "tarea en curso?"),
    label("Goes through", "La llamada pasa"),
    label("Refused", "Rechazado"),
    label("lists what's allowed", "indica lo permitido"),
]

# ---------------------------------------------------------------- concepts/authorization-effective-roles
SPECS["concepts/authorization-effective-roles"] = head(
    "Resolving effective roles", "Resolución de los roles efectivos",
    "Flowchart showing direct role grants on the user record and roles inherited from user groups both feeding a user's effective roles, the union used by every authorization check.",
    "Diagrama de flujo que muestra cómo los roles concedidos directamente en el registro del usuario y los heredados de grupos de usuarios alimentan los roles efectivos del usuario, la unión que usa toda comprobación de autorización.",
) + [
    label("DIRECT", "DIRECTO"),
    label("GROUP", "GRUPO"),
    label("Direct grants", "Concesiones directas"),
    label("on the user record", "en el registro del usuario"),
    label("Group grants", "Concesiones de grupo"),
    label("inherited", "heredadas"),
    label("Effective roles", "Roles efectivos"),
    label("Every auth", "Toda comprobación"),
    label("check", "de autorización"),
]

# ---------------------------------------------------------------- concepts/authorization-session-matrix
SPECS["concepts/authorization-session-matrix"] = head(
    "Who can reach which session", "Quién puede acceder a cada sesión",
    "Access matrix showing that Developers, the workflow's creator, and Super Admin reach a Design session, with Reviewers holding read-only access to it, while the run's initiator, its designated approvers, and Super Admin reach a Workflow session, with Admin holding read-only access to the Workflow session.",
    "Matriz de acceso que muestra que los Desarrolladores, el creador del flujo de trabajo y el Superadministrador acceden a una sesión de diseño, con acceso de solo lectura para los Revisores, mientras que el iniciador de la ejecución, sus aprobadores designados y el Superadministrador acceden a una sesión del flujo de trabajo, con acceso de solo lectura para el Administrador.",
) + [
    label("Session", "Sesión"),
    label("vs. actor", "frente a actor"),
    label("Developer", "Desarrollador"),
    label("Reviewer", "Revisor"),
    (">any in tenant</text>", ">cualquiera del tenant</text>", 2),
    label("Creator", "Creador"),
    label("workflow's createdBy", "creó el flujo de trabajo"),
    label("Initiator", "Iniciador"),
    label("started the run", "inició la ejecución"),
    label("Approver", "Aprobador"),
    label("designated for it", "designado para ella"),
    label("Admin", "Administrador"),
    label("tenant admin", "administrador del tenant"),
    label("Super Admin", "Superadministrador"),
    label("unrestricted", "sin restricciones"),
    label("Design session", "Sesión de diseño"),
    label("Workflow session", "Sesión del flujo de trabajo"),
    (">Yes</text>", ">Sí</text>", 6),
    (">No access</text>", ">Sin acceso</text>", 7),
    (">Read only</text>", ">Solo lectura</text>", 3),
    (">can't drive it</text>", ">no puede dirigirla</text>", 2),
    label("LEGEND", "LEYENDA"),
    label("Full access", "Acceso completo"),
]

# ---------------------------------------------------------------- operations/deployment-topology
SPECS["operations/deployment-topology"] = head(
    "Deployment topology", "Topología de despliegue",
    "Architecture diagram showing the browser reaching a reverse proxy that routes API requests (/api/*) straight to the backend API and page requests to the frontend, and the backend API — which also runs the email worker — reaching durable state (database, skill store, secret key), external services (LLM provider, MCP servers), and an SMTP relay.",
    "Diagrama de arquitectura que muestra el navegador llegando a un proxy inverso que dirige las solicitudes de API (/api/*) directamente a la API del backend y las solicitudes de páginas al frontend, y a la API del backend, que también ejecuta el worker de correo, accediendo al estado duradero (base de datos, almacén de skills, clave secreta), a los servicios externos (proveedor de LLM, servidores MCP) y a un relé SMTP.",
) + [
    label("DURABLE STATE", "ESTADO DURADERO"),
    label("EXTERNAL SERVICES", "SERVICIOS EXTERNOS"),
    label("pages", "páginas"),
    label("Browser", "Navegador"),
    label("Reverse proxy", "Proxy inverso"),
    label("load balancer", "balanceador de carga"),
    label("chat UI", "interfaz de chat"),
    label("Backend API", "API del backend"),
    label("uvicorn + email worker", "uvicorn + worker de correo"),
    label("Database", "Base de datos"),
    label("records", "registros"),
    (_node(220, 542, "Skill store", 13), _node(220, 531, "Almacén", 13) + _node(220, 546, "de skills", 13)),
    label("cloned repos", "repos clonados"),
    label("Secret key", "Clave secreta"),
    label("encrypts", "cifra"),
    (_node(515, 552, "LLM provider", 13), _node(515, 545, "Proveedor", 13) + _node(515, 561, "de LLM", 13)),
    (_node(645, 552, "MCP servers", 13), _node(645, 545, "Servidores", 13) + _node(645, 561, "MCP", 13)),
    label("SMTP relay", "Relé SMTP"),
    label("LEGEND", "LEYENDA"),
    label("A2Flow component", "Componente de A2Flow"),
    label("External system", "Sistema externo"),
    label("Data store", "Almacén de datos"),
]

# ---------------------------------------------------------------- operations/scaling-lock-race
SPECS["operations/scaling-lock-race"] = head(
    "One driver per conversation", "Un solo conductor por conversación",
    "Sequence diagram of two replicas racing to run the same session: Replica 1 takes a PostgreSQL advisory lock and opens the stream for Client A, while Replica 2's later request for the same session is refused with 409 while the lock is held, and the lock is released only when Replica 1's stream ends.",
    "Diagrama de secuencia de dos réplicas que compiten por ejecutar la misma sesión: la réplica 1 toma un bloqueo consultivo de PostgreSQL y abre el stream para el cliente A, mientras que la solicitud posterior a la réplica 2 para la misma sesión se rechaza con 409 mientras se mantiene el bloqueo, y este solo se libera cuando termina el stream de la réplica 1.",
) + [
    mask(401, 188, 78, 82, h=12),
    mask(621, 364, 78, 82, h=12),
    (">TAKE LOCK</text>", ">TOMAR BLOQUEO</text>", 2),
    label("ACQUIRED", "OBTENIDO"),
    label("SSE STREAM OPENS", "SE ABRE EL STREAM SSE"),
    mask(609, 408, 102, 146, h=12),
    label("HELD ELSEWHERE", "MANTENIDO EN OTRA RÉPLICA"),
    label("409 REFUSED", "409 RECHAZADO"),
    label("STREAM ENDS", "TERMINA EL STREAM"),
    label("RELEASED", "LIBERADO"),
    label("Client A", "Cliente A"),
    label("Replica 1", "Réplica 1"),
    label("Replica 2", "Réplica 2"),
    label("Client B", "Cliente B"),
    label("LEGEND", "LEYENDA"),
    label("Call", "Llamada"),
    label("Return", "Respuesta"),
    label("Refused", "Rechazado"),
]

# ---------------------------------------------------------------- architecture/approvals-sequence
SPECS["architecture/approvals-sequence"] = head(
    "How an approval gate runs", "Cómo funciona una barrera de aprobación",
    "Sequence diagram of an approval: the execution agent requests approval, A2Flow notifies the approver while the covered steps stay blocked, the approver decides, and A2Flow grants a certificate to each covered step as it starts and lets the run continue.",
    "Diagrama de secuencia de una aprobación: el agente de ejecución solicita la aprobación, A2Flow notifica al aprobador mientras los pasos cubiertos siguen bloqueados, el aprobador decide y A2Flow concede un certificado a cada paso cubierto cuando se inicia y deja que la ejecución continúe.",
) + [
    mask(222, 160, 116, 130, h=12),
    label("REQUEST APPROVAL", "SOLICITAR APROBACIÓN"),
    mask(536, 220, 58, 66, h=12),
    label("NOTIFY", "NOTIFICAR"),
    mask(222, 340, 116, 134, h=12),
    label("RUN CONTINUES", "LA EJECUCIÓN CONTINÚA"),
    label("the covered steps", "los pasos cubiertos"),
    label("stay blocked", "siguen bloqueados"),
    label("a certificate is", "se concede un certificado"),
    label("granted per step", "a cada paso"),
    label("Execution", "Agente de"),
    label("agent", "ejecución"),
    label("Approver", "Aprobador"),
    label("LEGEND", "LEYENDA"),
    label("Call", "Llamada"),
    label("Run continues", "La ejecución continúa"),
]

# ---------------------------------------------------------------- architecture/approvals-step-coverage
SPECS["architecture/approvals-step-coverage"] = head(
    "What one approval covers", "Qué cubre una aprobación",
    "Flowchart of a five-step task chain where Approval A covers the first three steps and Approval B takes over from the fourth step onward, showing that an approval covers its named step and everything after it up to the next approval.",
    "Diagrama de flujo de una cadena de cinco pasos en la que la aprobación A cubre los tres primeros pasos y la aprobación B toma el relevo a partir del cuarto, lo que muestra que una aprobación cubre el paso que nombra y todo lo que sigue hasta la próxima aprobación.",
) + [
    label("Approval A", "Aprobación A"),
    label("Approval B", "Aprobación B"),
    (">gate</text>", ">barrera</text>", 2),
    label("Ask for a go-ahead", "Pedir el visto bueno"),
    label("Launch instance", "Lanzar la instancia"),
    label("Tag instance", "Etiquetar la instancia"),
    label("Ask again", "Volver a preguntar"),
    label("Delete snapshot", "Eliminar la instantánea"),
    label("APPROVAL A COVERS", "CUBRE LA APROBACIÓN A"),
    label("APPROVAL B COVERS", "CUBRE LA APROBACIÓN B"),
    label("LEGEND", "LEYENDA"),
    label("Approval gate", "Barrera de aprobación"),
]

# ---------------------------------------------------------------- architecture/overview-lifecycle
SPECS["architecture/overview-lifecycle"] = head(
    "How a workflow moves", "Cómo avanza un flujo de trabajo",
    "Flowchart showing an Agent Skill generated into a Workflow, run as a Workflow execution inside a Workflow session, whose Tasks request human approval or call an MCP tool through the MCP gateway to reach an MCP server.",
    "Diagrama de flujo que muestra una skill de agente a partir de la cual se genera un flujo de trabajo, que se lanza como una ejecución dentro de una sesión del flujo de trabajo, cuyas tareas solicitan aprobación humana o llaman a una herramienta MCP a través del gateway MCP para llegar a un servidor MCP.",
) + [
    label("GENERATE", "GENERAR"),
    ('<rect x="508" y="222" width="100" height="12"', '<rect x="508" y="222" width="118" height="12"'),
    label("PUBLISH/RUN", "PUBLICAR/EJECUTAR"),
    mask(315, 520, 120, 128, h=12),
    label("NEEDS A PERSON", "REQUIERE UNA PERSONA"),
    mask(565, 520, 120, 152, h=12),
    label("NEEDS A TOOL", "REQUIERE UNA HERRAMIENTA"),
    label("CERTIFICATE", "CERTIFICADO"),
    label("Agent Skill", "Skill de agente"),
    label("a Git repository", "un repositorio Git"),
    ('<rect x="390" y="144" width="220"', '<rect x="370" y="144" width="260"'),
    label("Workflow", "Flujo de trabajo"),
    label("templates + tool bindings", "plantillas + herramientas vinculadas"),
    ('<rect x="380" y="248" width="240"', '<rect x="370" y="248" width="260"'),
    label("Workflow execution", "Ejecución del flujo de trabajo"),
    label("a snapshot of the design", "una instantánea del diseño"),
    ('<rect x="390" y="352" width="220"', '<rect x="370" y="352" width="260"'),
    label("Workflow session", "Sesión del flujo de trabajo"),
    label("the run's shared chat", "el chat compartido de la ejecución"),
    label("Tasks", "Tareas"),
    label("one at a time", "una a la vez"),
    label("Approval gate", "Barrera de aprobación"),
    label("MCP gateway", "Gateway MCP"),
    label("MCP server", "Servidor MCP"),
]

# ---------------------------------------------------------------- architecture/secrets-resolution
SPECS["architecture/secrets-resolution"] = head(
    "How a secret reference resolves", "Cómo se resuelve una referencia a un secreto",
    "Flowchart showing a name/key secret reference branching by storage type: local secrets are decrypted from the stored value, Vault secrets are read live, and both feed an MCP server connection or a skill repository clone.",
    "Diagrama de flujo que muestra una referencia a un secreto que se bifurca según el tipo: local descifra el valor guardado, vault lo lee en vivo desde Vault, y ambos alimentan una conexión a un servidor MCP o la clonación de un repositorio de skill.",
    page_title="Secret reference resolution", svg_title="Secret reference resolution",
) + [
    label("A reference", "Una referencia"),
    label("Which type?", "¿Qué tipo?"),
    label("Decrypt the", "Descifrar el"),
    label("stored value", "valor guardado"),
    label("Read it live", "Leerlo en vivo"),
    label("from Vault", "desde Vault"),
    label("MCP server connection", "Conexión a un servidor MCP"),
    label("or a skill repository clone", "o clonación de un repositorio de skill"),
]

_POLICY_MASKS = [
    mask(612, 140, 56, 58, h=12),
    label("DENIED", "DENEGADO"),
    label("ALLOWED", "PERMITIDO"),
    label("YES", "SÍ"),
    label("calls a tool", "llama a una herramienta"),
    label("Policy chain", "Cadena de políticas"),
    label("Refused", "Rechazado"),
    label("Mocked for", "¿Simulada en"),
    label("this run?", "esta ejecución?"),
    # The mock's pill grows to the right; the arrow still meets its left edge.
    ('<rect x="820" y="292" width="160"', '<rect x="820" y="292" width="172"'),
    ('<text x="900" y="316"', '<text x="906" y="316"'),
    ('<text x="900" y="330"', '<text x="906" y="330"'),
    label("Mock's response", "Respuesta del mock"),
    label("no server contacted", "no contacta con servidores"),
    label("MCP server", "Servidor MCP"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-policy-chain
SPECS["architecture/mcp-gateway-and-proxy-policy-chain"] = head(
    "The policy chain", "La cadena de políticas",
    "Flowchart showing how the MCP gateway decides a tool call: a policy chain either refuses it or allows it, an allowed call is either answered from a mock or goes through credential injection and the MCP proxy to the real MCP server, and both the refusal and the real call produce an audit record.",
    "Diagrama de flujo de la cadena de políticas que decide una llamada a una herramienta: las llamadas denegadas se rechazan indicando lo que está permitido, las permitidas se responden desde un mock o pasan por la inyección de credenciales y el proxy MCP hasta el servidor MCP, y tanto un rechazo como una llamada real generan un registro de auditoría.",
    page_title="Policy chain", svg_title="Policy chain",
) + _POLICY_MASKS + [
    label("Execution agent", "Agente de ejecución"),
    label("lists what is allowed", "indica lo permitido"),
    ('<rect x="400" y="416" width="200" height="48"', '<rect x="390" y="416" width="220" height="48"'),
    label("Credential injection", "Inyección de credenciales"),
    label("MCP proxy", "Proxy MCP"),
    label("Audit record", "Registro de auditoría"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-tool-mocks
SPECS["architecture/mcp-gateway-and-proxy-tool-mocks"] = head(
    "Where the mock sits", "Dónde se sitúa el mock",
    "Flowchart showing that a tool mock is consulted only after the same policy chain a production call faces: a denied call is refused exactly as in production, and an allowed call is answered from a mock's next response or the real MCP server.",
    "Diagrama de flujo que muestra que un mock de herramienta solo se consulta después de la misma cadena de políticas que afronta una llamada de producción: una llamada denegada se rechaza exactamente igual que en producción, y una permitida se responde con la siguiente respuesta de un mock o desde el servidor MCP real.",
) + _POLICY_MASKS + [
    label("The agent", "El agente"),
    label("exactly as production", "igual que en producción"),
    ('<rect x="420" y="416" width="160" height="48"', '<rect x="410" y="416" width="180" height="48"'),
    label("the real side effect", "el efecto secundario real"),
]

# ---------------------------------------------------------------- architecture/mcp-gateway-and-proxy-trust-boundary
SPECS["architecture/mcp-gateway-and-proxy-trust-boundary"] = head(
    "Crossing the trust boundary", "Cruzar el límite de confianza",
    "Architecture diagram showing the MCP gateway, which decides whether a call is allowed, mocked, and which credentials it needs, handing exactly one authorized call across a trust boundary into the MCP proxy, which starts or connects to the real MCP server.",
    "Diagrama de arquitectura que muestra el gateway MCP, que decide si una llamada se permite, si se simula y qué credenciales necesita, entregando exactamente una llamada autorizada a través de un límite de confianza al proxy MCP, que inicia el servidor MCP real o se conecta a él.",
) + [
    label("RUNS THE AGENT", "EJECUTA EL AGENTE"),
    label("AUTHORIZED", "AUTORIZADA"),
    label("MCP gateway", "Gateway MCP"),
    label("allowed, mocked, credentials", "permitida, simulada, credenciales"),
    label("MCP proxy", "Proxy MCP"),
    label("starts or connects", "inicia o se conecta"),
    label("MCP server", "Servidor MCP"),
    label("outside our control", "fuera de nuestro control"),
    label("LEGEND", "LEYENDA"),
    label("Trust boundary", "Límite de confianza"),
]

# ---------------------------------------------------------------- architecture/sessions-turn-flow
SPECS["architecture/sessions-turn-flow"] = head(
    "How a turn runs", "Cómo transcurre un turno",
    "Sequence diagram of one chat turn: the user's message travels from Frontend to Backend to the Model, the model's streamed reply and any render_a2ui surface flow back, and the user's filled-in surface makes the same round trip again.",
    "Diagrama de secuencia de un turno de chat: el mensaje del usuario viaja del frontend al backend y al modelo, la respuesta transmitida del modelo y cualquier superficie render_a2ui regresan, y la superficie rellenada por el usuario hace de nuevo el mismo recorrido de ida y vuelta.",
) + [
    mask(190, 160, 100, 118, h=12),
    label("WRITES MESSAGE", "ESCRIBE EL MENSAJE"),
    mask(396, 200, 144, 210, h=12),
    label("MESSAGE + TOOL SCHEMA", "MENSAJE + ESQUEMA DE HERRAMIENTAS"),
    mask(640, 240, 104, 106, h=12),
    label("BRIDGE TO AGENT", "PUENTE AL AGENTE"),
    mask(632, 280, 120, 198, h=12),
    label("TEXT + TOOL CALLS", "TEXTO + LLAMADAS A HERRAMIENTAS"),
    label("STREAMED ONWARD", "SE RETRANSMITE"),
    mask(192, 360, 96, 130, h=12),
    label("DRAWS SURFACE", "DIBUJA LA SUPERFICIE"),
    label("FILLS + SUBMITS", "RELLENA + ENVÍA"),
    mask(414, 440, 108, 155, h=12),
    label("FULL DATA MODEL", "MODELO DE DATOS COMPLETO"),
    mask(638, 480, 108, 137, h=12),
    label("MATCHED TO CALL", "ASOCIADO A LA LLAMADA"),
    mask(412, 520, 112, 124, h=12),
    label("RESPONDS TO USER", "RESPONDE AL USUARIO"),
    label("a render_a2ui call is", "una llamada a render_a2ui"),
    label("forwarded, never executed", "se reenvía sin ejecutarse"),
    label("User", "Usuario"),
    label("Browser", "Navegador"),
    label("chat UI", "interfaz de chat"),
    label("Model", "Modelo"),
    label("LLM provider", "proveedor de LLM"),
    label("LEGEND", "LEYENDA"),
    label("Call", "Llamada"),
    label("Streamed return", "Respuesta transmitida"),
    label("Response to user", "Respuesta al usuario"),
]

# ---------------------------------------------------------------- architecture/workflow-design-status
SPECS["architecture/workflow-design-status"] = head(
    "Workflow status lifecycle", "Ciclo de vida del estado del flujo de trabajo",
    "State machine showing a workflow moving from a published Agent Skill through generating to draft or failed, then from draft through published and modified, with publish looping back from modified.",
    "Máquina de estados que muestra un flujo de trabajo que pasa de una skill de agente publicada, a través de la generación, a borrador o fallido, y luego de borrador a publicado y modificado, con la publicación volviendo desde modificado.",
) + [
    ('<rect x="196" y="96" width="48" height="12"', '<rect x="201" y="96" width="38" height="12"'),
    label("GENERATE", "GENERAR"),
    mask(366, 180, 56, 62, h=12),
    label("NO STEPS", "SIN PASOS"),
    mask(568, 180, 48, 56, h=12),
    label("REVISED", "REVISADO"),
    # The right-hand column moves 16px right, so PUBLICAR gets a gap wider than its mask.
    ('<line x1="600" y1="112" x2="640" y2="112"', '<line x1="600" y1="112" x2="656" y2="112"'),
    ('<rect x="596" y="96" width="48" height="12"', '<rect x="602" y="96" width="52" height="12"'),
    ('<text x="620" y="105"', '<text x="628" y="105"'),
    ('<line x1="700" y1="152" x2="700" y2="220"', '<line x1="716" y1="152" x2="716" y2="220"'),
    ('<line x1="760" y1="220" x2="760" y2="152"', '<line x1="776" y1="220" x2="776" y2="152"'),
    ('<rect x="676" y="180" width="48" height="12"', '<rect x="692" y="180" width="48" height="12"'),
    ('<text x="700" y="190"', '<text x="716" y="190"'),
    ('<rect x="736" y="180" width="48" height="12"', '<rect x="748" y="179" width="56" height="14"'),
    ('<text x="760" y="190"', '<text x="776" y="190"'),
    ('<rect x="640" y="72" width="160"', '<rect x="656" y="72" width="160"'),
    ('<text x="720" y="108"', '<text x="736" y="108"'),
    ('<text x="720" y="124"', '<text x="736" y="124"'),
    ('<rect x="640" y="220" width="160"', '<rect x="656" y="220" width="160"'),
    ('<text x="720" y="256"', '<text x="736" y="256"'),
    ('<text x="720" y="272"', '<text x="736" y="272"'),
    label("EDITED", "EDITADO"),
    (">PUBLISH</text>", ">PUBLICAR</text>", 2),
    label("generating", "generando"),
    label("draft", "borrador"),
    label("published", "publicado"),
    label("failed", "fallido"),
    label("modified", "modificado"),
    label("Agent Skill", "Skill de agente"),
    label("published revision", "revisión publicada"),
    label("design run in progress", "diseño en ejecución"),
    label("templates + bindings", "plantillas + vinculación"),
    label("design is frozen", "diseño congelado"),
    label("reason on record", "motivo registrado"),
    label("runs use published", "se ejecuta lo publicado"),
    label("LEGEND", "LEYENDA"),
    label("Precondition", "Condición previa"),
    label("Status", "Estado"),
    label("Live version", "Versión activa"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-snapshot
SPECS["architecture/workflow-execution-snapshot"] = head(
    "Running a workflow copies its design", "Ejecutar un flujo de trabajo copia su diseño",
    "Flowchart showing a published workflow and its chosen tool mocks copied by value onto a new workflow execution snapshot, which opens a workflow session containing tasks that all start pending.",
    "Diagrama de flujo que muestra un flujo de trabajo publicado y los mocks de herramientas elegidos, copiados en una nueva instantánea de ejecución, que abre una sesión del flujo de trabajo con todas las tareas pendientes al principio.",
    page_title="Running a workflow", svg_title="Running a workflow copies its design",
) + [
    mask(404, 136, 32, 58, h=12),
    label("RUN", "EJECUTAR"),
    # Pulled left so the mask stops short of the elbow at x=660.
    ('<rect x="556" y="136" width="96" height="12"', '<rect x="545" y="135" width="110" height="14"'),
    ('<text x="604" y="145"', '<text x="600" y="145"'),
    label("COPIED BY VALUE", "COPIADO POR VALOR"),
    label("Workflow", "Flujo de trabajo"),
    label("published version", "versión publicada"),
    ('<rect x="560" y="60" width="200"', '<rect x="530" y="60" width="260"'),
    label("Chosen tool mocks", "Mocks de herramientas elegidos"),
    label("test runs only", "solo ejecuciones de prueba"),
    ('<rect x="380" y="180" width="240"', '<rect x="370" y="180" width="260"'),
    label("Workflow execution", "Ejecución del flujo de trabajo"),
    label("the snapshot", "la instantánea"),
    ('<rect x="380" y="300" width="240"', '<rect x="370" y="300" width="260"'),
    label("Workflow session", "Sesión del flujo de trabajo"),
    label("the run's chat", "el chat de la ejecución"),
    ('<rect x="380" y="420" width="240"', '<rect x="370" y="420" width="260"'),
    label("Tasks", "Tareas"),
    label("all pending at the start", "todas pendientes al principio"),
]

# ---------------------------------------------------------------- architecture/workflow-execution-run-loop
SPECS["architecture/workflow-execution-run-loop"] = head(
    "How the run advances", "Cómo avanza la ejecución",
    "Flowchart showing the task-advancement loop: list tasks, pick one whose dependencies have completed, mark it in progress, do the work, mark it ended, and repeat until every task has ended and the run settles.",
    "Diagrama de flujo del bucle de avance de la ejecución: listar las tareas de la ejecución, elegir una cuyas dependencias hayan terminado, marcarla en curso, hacer el trabajo, marcarla completada, fallida u omitida, y repetir, o cerrar cuando todas las tareas hayan terminado.",
) + [
    label("YES", "SÍ"),
    (_node(500, 68, "List the run's tasks"), _node(500, 60, "Listar las tareas") + _node(500, 76, "de la ejecución")),
    # The diamond grows by 20px a side so its second line clears the slope.
    ('points="500,112 600,160 500,208 400,160"', 'points="500,112 620,160 500,208 380,160"'),
    ('<line x1="600" y1="160" x2="720" y2="160"', '<line x1="620" y1="160" x2="720" y2="160"'),
    ('<rect x="644" y="154" width="24" height="12"', '<rect x="658" y="154" width="24" height="12"'),
    ('<text x="656" y="163"', '<text x="670" y="163"'),
    label("A pending task whose", "¿Tarea pendiente con"),
    label("deps have completed?", "dependencias terminadas?"),
    label("Mark it in_progress", "Marcarla en curso"),
    ('<rect x="400" y="344" width="200" height="48"', '<rect x="368" y="344" width="264" height="48"'),
    label("Do the work", "Hacer el trabajo"),
    label("tools, approvals, conversation", "herramientas, aprobaciones, conversación"),
    label("Mark it completed,", "Marcarla completada,"),
    label("failed, or skipped", "fallida u omitida"),
    label("Run settles", "La ejecución se cierra"),
    label("every task has ended", "todas las tareas han terminado"),
    label("LEGEND", "LEYENDA"),
    label("Step (rectangle)", "Paso (rectángulo)"),
    label("Decision (diamond)", "Decisión (rombo)"),
    label("Loop exit (oval)", "Salida del bucle (óvalo)"),
    label("Continues the loop", "Continúa el bucle"),
]
