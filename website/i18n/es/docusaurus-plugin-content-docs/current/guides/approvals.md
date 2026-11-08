---
title: Aprobaciones
sidebar_position: 5
---

# Aprobaciones

Una aprobación es la forma en que una ejecución se detiene y espera a una persona. El agente la solicita a mitad de la ejecución, el aprobador designado decide en el chat, y esa decisión es lo que desbloquea las herramientas de los pasos que cubre.

## Aprobación humana {#human-approval}

Cuando una tarea necesita un visto bueno explícito antes de que el agente actúe, por ejemplo en una operación destructiva o irreversible, el agente solicita una aprobación y se detiene.

![Diagrama de secuencia de una solicitud de aprobación: el agente de ejecución solicita la aprobación, A2Flow notifica al aprobador y la ejecución se detiene, el aprobador decide, y A2Flow concede un certificado a cada paso cubierto y reanuda la ejecución.](./img/approvals-sequence.svg#gh-light-mode-only)
![Diagrama de secuencia de una solicitud de aprobación: el agente de ejecución solicita la aprobación, A2Flow notifica al aprobador y la ejecución se detiene, el aprobador decide, y A2Flow concede un certificado a cada paso cubierto y reanuda la ejecución.](./img/approvals-sequence-dark.svg#gh-dark-mode-only)

### A quién se solicita {#who-is-asked}

Una solicitud se dirige a **exactamente un destino**: nunca a los dos y nunca a ninguno.

| Destino | A quién se notifica | Quién puede decidir |
|---|---|---|
| **Un usuario** | Solo a esa persona | Solo esa persona |
| **Un [grupo de usuarios](./users-and-groups.md#user-groups)** | A todos los miembros con el rol `Aprobador`, cada uno con su propia notificación | Cualquiera de ellos: la **primera** decisión resuelve la solicitud |

Dirigirla a un grupo significa que la aprobación no queda bloqueada por la disponibilidad de una sola persona. Un grupo sin ningún miembro que pueda aprobar se rechaza de entrada, ya que esa solicitud nunca podría resolverse, y lo mismo ocurre con un destino que no tenga todas las [etiquetas de control de acceso](./tags.md#execution-and-approval-tags) que tiene la propia ejecución, ya que nunca podría ver la solicitud para decidir sobre ella. Cuando alguien decide, nada descarta las notificaciones de los demás miembros; simplemente dejan de permitir ninguna acción. Queda registrado quién decidió realmente, porque el nombre del grupo por sí solo no responde a «¿quién aprobó esto?».

Se indica al agente que prefiera un grupo siempre que pueda decidir cualquier miembro de un equipo, y que designe a una sola persona cuando la skill lo requiera.

### Decidir {#deciding}

El agente explica la solicitud en texto sin formato y los controles aparecen debajo, en el chat, pero **solo para el aprobador designado**. Si el destino es un grupo, varias personas pueden tenerlos a la vez. Todos los demás ven un mensaje de espera de solo lectura.

Antes de decidir, puedes preguntar al agente sobre la solicitud. Escribe una pregunta en el chat y se abrirá una [consulta](./workflow-executions.md#consultations) en la que responde el agente y en la que puede participar la persona que inició la ejecución. La decisión la cierra.

| Decisión | Qué significa | Qué hace el agente |
|---|---|---|
| **Aprobar** | Adelante | Continúa, con las herramientas de los pasos cubiertos desbloqueadas |
| **Rechazar** | No hagas esto | Marca la tarea como `fallido` u `omitido` |
| **Devolver** | Revísalo y vuelve a solicitarlo | Devuelve el trabajo en lugar de resolver la solicitud |

Una decisión reanuda la ejecución de inmediato, se tome donde se tome (en el chat o desde la lista de [Aprobaciones](#browsing-approvals)), aunque nadie tenga abierto el chat de la ejecución. Tampoco se pierde una decisión tomada antes de que aparezcan los controles: la ejecución la recoge en cuanto llega a ese punto.

**Devolver** es una tercera decisión junto a las otras dos, no una variante de **Rechazar**: una tasa alta de devoluciones apunta a un problema de calidad en una etapa anterior, no a un trabajo que nunca debió solicitarse.

Cada decisión admite un **comentario** opcional. La decisión en sí es **definitiva**: dos miembros de un grupo de aprobadores pueden competir de verdad por decidir primero, así que una segunda decisión que cambiaría la registrada se rechaza en lugar de sobrescribirla. Editar el comentario después sigue estando permitido, y eso no altera ni quién decidió ni cuándo, de modo que el tiempo transcurrido entre la solicitud y la decisión sigue siendo el real del aprobador.

Solo el aprobador designado puede decidir, **sin excepción: ni siquiera un Superadministrador** que no sea el destinatario. La misma regla se extiende al estado de las tareas: cambiar el estado de una tarea, ya sea a mano o pidiéndoselo al agente de ejecución, está limitado a la persona que inició la ejecución y al aprobador de una aprobación **que cubra esa tarea**. Un aprobador puede mover los pasos que cubre su decisión (la tarea que nombra la aprobación y todo lo que viene después hasta la siguiente aprobación), y eso es lo que permite que una aprobación reanude la ejecución; no puede hacer avanzar una tarea fuera de lo que se le pidió aprobar, ya que eso permitiría a cualquier aprobador de la ejecución sustituir al destinatario.

### Qué autoriza una solicitud {#what-a-request-authorizes}

Una solicitud no es solo una frase con la que estar de acuerdo. En **Esto autoriza** enumera todas las
llamadas que permitiría: la herramienta y, para cada una de sus entradas, los valores que esa entrada
puede tomar. Esa lista es sobre lo que decides, y el servidor exige a la ejecución que se atenga
a ella a partir de ese momento.

El límite de una entrada se escribe de una de estas cinco formas:

| Se muestra como | Significa |
|---|---|
| `es "ap-northeast-1"` | Exactamente ese valor y ningún otro |
| `es uno de ["t3.micro", "t3.small"]` | Cualquiera de los valores enumerados |
| `es como máximo 2` | Un número no mayor que ese |
| `es como mínimo 8` | Un número no menor que ese |
| `coincide con "^dev-"` | Texto con esa forma; aquí, cualquiera que empiece por `dev-` |

Una entrada marcada como **opcional** se puede omitir; todas las demás entradas enumeradas deben proporcionarse.
Todo lo que **no aparezca en la lista se rechaza**, de modo que una ejecución no puede colar una entrada que
nunca se te mostró.

Lee los límites antes de decidir, y considera que un límite amplio es una decisión amplia: aprobar
`es como máximo 100` cuando el trabajo necesita dos equivale a conceder autoridad sobre cien servidores. Si
los límites son más amplios de lo que justifica el trabajo, usa **Devolver** y dilo: el
agente puede volver a solicitarlo con límites más estrechos.

Una llamada marcada como **Cualquier entrada** es la única excepción. El diseño del flujo de trabajo indicó que esa herramienta
solo lee (un listado, una búsqueda), así que la solicitud no te pide que aceptes los valores
con los que se la llama, y la ejecución puede llamarla con lo que necesite. Todo lo demás sobre
ella no cambia: la cubre tu decisión y no se la puede llamar hasta que la concedas. Si una herramienta
mostrada así parece que podría cambiar algo, es motivo para usar **Devolver** y preguntar
por ella.

Procura leer esto en el sentido correcto. Una llamada que aparece **sin** entradas debajo
significa lo contrario: esa herramienta se puede llamar, y sin pasarle nada en absoluto.

Una solicitud que no autoriza ninguna llamada a herramientas no muestra esa lista. Se trata de una aprobación
que condiciona una acción que A2Flow no realiza por sí mismo, como aceptar la redacción de un
aviso.

### Qué desbloquea la aprobación {#what-approval-unlocks}

**La barrera de aprobación la aplica el servidor, no el agente.** Un paso cubierto por una aprobación no puede llamar a ninguna de sus [herramientas MCP](./mcp-servers.md) vinculadas hasta que se conceda esa aprobación: la llamada se rechaza antes de llegar al servidor. Cada paso cubierto recibe un **certificado** de corta duración cuando empieza, y todas sus llamadas posteriores a herramientas deben presentar ese certificado.

Todos los pasos necesitan ese certificado, no solo aquellos para los que se pidió aprobación a alguien. Un paso que no cubre ninguna aprobación recibe uno en el momento en que se marca como **en curso**, con la autoridad de quien inició la ejecución. Así, el registro siempre indica en nombre de quién se hizo una llamada a una herramienta, y no existe ningún camino sin atribuir hacia una herramienta. Una aprobación simplemente sustituye esa autoridad por la del propio aprobador.

Esto aporta dos cosas que una instrucción al modelo no podría dar:

- **Ni una inyección de prompt ni un error pueden saltarse la aprobación.** La barrera es una regla que comprueba el servidor, no una frase en las instrucciones del agente más un frontend que se niega a reanudar.
- **Las herramientas concedidas quedan congeladas.** Un certificado contiene las herramientas que su paso tenía vinculadas cuando empezó, y las herramientas de un paso cubierto ya no se pueden editar en absoluto. Los pasos de una ejecución y sus herramientas proceden del diseño publicado del flujo de trabajo y el agente no puede cambiarlos, así que nada de lo que ocurra después de la decisión puede ampliar una concesión. Aprobar que un paso lea un archivo no se convierte en aprobar que lo elimine.
- **Los argumentos aprobados también quedan congelados.** Una solicitud también contiene las llamadas que autoriza (cada herramienta junto con los límites de los valores con los que se la puede llamar), y eso es lo que te muestra antes de decidir. Cada llamada posterior se comprueba con ella, así que aprobar «iniciar un servidor pequeño en Tokio» nunca se convierte en aprobar que se inicien diez grandes en otro lugar. Consulta [Qué autoriza una solicitud](#what-a-request-authorizes).

**Lo que cubre una decisión** es el paso que nombra la solicitud **y todos los pasos siguientes, hasta la próxima aprobación**. Un flujo de trabajo suele mostrar la solicitud como un paso propio, por ejemplo «Solicitar aprobación» seguido de «Lanzar instancia», y una sola decisión cubre ambos, de modo que no se vuelve a preguntar al aprobador por cada paso del mismo trabajo. Conviene conocer dos consecuencias:

- Donde confluyen dos ramas aprobadas, el paso en el que se unen necesita **ambas** decisiones antes de poder actuar.
- Una solicitud nunca cubre nada anterior a ella. Una aprobación solo alcanza hacia delante.

Cada llamada a herramienta sobre la que se ha decidido, permitida o rechazada, queda registrada en la página de [Invocaciones de herramientas](./workflow-executions.md#tool-invocations) de la ejecución junto con el certificado que presentó, de modo que después se puede responder a «¿quién autorizó esto y con qué base?».

Nada de esto requiere configuración; la duración del certificado se puede ajustar en la [referencia de configuración](../operations/configuration.md#mcp-tools-and-approvals).

> **Alcance de la garantía.** El gateway MCP se ejecuta actualmente dentro del proceso del backend, así que un certificado demuestra su posesión ante un verificador que comparte ese proceso; no es una defensa frente a un atacante que ya controla el backend. Lo que aporta es un único punto de control que, ante un fallo, se mantiene cerrado, una concesión que no se puede ampliar a posteriori y un registro verificable.

## Consultar las aprobaciones {#browsing-approvals}

Abre **Aprobaciones** en la barra lateral de administración para consultar todas las solicitudes de aprobación. Esta vista es solo para consultar: las decisiones se toman con los controles **Aprobar** / **Rechazar** / **Devolver** del chat.

| Columna | Se muestra de forma predeterminada |
|---|---|
| Título, estado (`pendiente` / `aprobado` / `rechazado` / `devuelto`), descripción, fecha de creación | Sí |
| Ejecución del flujo de trabajo: un enlace a la ejecución de la que procede | Sí |
| Etiquetas: de solo lectura, las etiquetas de la ejecución a la que pertenece (consulta [Etiquetas de ejecuciones y aprobaciones](./tags.md#execution-and-approval-tags)) | Sí |
| Decidido por: el usuario o el nombre del grupo de aprobadores, con un enlace a su página | Mediante el selector de columnas |
| El comentario del aprobador y la fecha de la decisión | Mediante el selector de columnas |

Cada fila incluye también la acción **Abrir sesión del flujo de trabajo**, que lleva directamente al chat de la ejecución, igual que la de la lista de [Ejecuciones de flujos de trabajo](./workflow-executions.md).

La página de detalle de una aprobación concedida muestra además lo que autorizó en **Herramientas MCP autorizadas**: una entrada por cada paso cubierto que haya empezado, cada una con las herramientas que se le concedieron, el periodo de validez y si su certificado se ha revocado. Es normal que el panel se vaya llenando poco a poco: un paso recibe su certificado cuando empieza, así que una aprobación recién concedida puede no mostrar nada todavía. Una entrada con la lista de herramientas vacía tampoco es un fallo; significa que ese paso hace su trabajo sin llamar a ninguna herramienta MCP.

**Llamadas autorizadas** muestra la misma lista que leyó el aprobador antes de decidir: las llamadas que permitía la solicitud y los límites de sus entradas. A diferencia del panel anterior, se rellena en el momento en que se hace la solicitud, no a medida que empiezan los pasos, y nunca cambia después: es el registro de aquello sobre lo que se decidió realmente. Una aprobación hecha antes de que A2Flow registrara estos límites muestra aquí una raya.

El campo **Vigente desde** nombra el paso en el que empieza la aprobación. También queda cubierto todo lo que viene después, hasta la siguiente aprobación.
