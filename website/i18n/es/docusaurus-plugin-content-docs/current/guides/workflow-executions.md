---
title: Ejecuciones de flujos de trabajo
sidebar_position: 4
---

# Ejecuciones de flujos de trabajo

Una ejecución es una pasada de un [flujo de trabajo](./workflows.md). Guarda su propia copia del nombre, la descripción, las tareas y las etiquetas del flujo de trabajo, de modo que el historial de la ejecución sigue siendo fiel a lo que realmente se ejecutó aunque después se edite o elimine el flujo de trabajo del que procede.

Abre **Ejecuciones de flujos de trabajo** en la barra lateral de administración para consultarlas. A diferencia de las demás secciones, una ejecución es un historial y no un registro que se edite, así que no hay formulario de edición: sus pantallas muestran la ejecución o te permiten unirte a ella. Su columna y su campo **Etiquetas** son de solo lectura por el mismo motivo; consulta [Etiquetas de ejecuciones y aprobaciones](./tags.md#execution-and-approval-tags).

| Pantalla | Cómo llegar | Qué muestra |
|---|---|---|
| Lista de **Ejecuciones de flujos de trabajo** | Barra lateral de administración → Ejecuciones de flujos de trabajo | Todas las ejecuciones, con su estado y las acciones de cada fila |
| **Sesión del flujo de trabajo** | La acción Abrir sesión del flujo de trabajo de una fila | El chat en el que transcurre la ejecución: únete, obsérvala, responde |
| **Tareas del flujo de trabajo** | El enlace a las tareas de una fila | Las tareas de la ejecución y sus estados, de solo lectura, como Tabla o Gráfico |
| **Invocaciones de herramientas** | El encabezado del detalle de la ejecución | Las llamadas a herramientas MCP que hizo la ejecución y cómo se decidió cada una |

**Simulado** marca una ejecución que simuló alguna de sus herramientas con un [mock de herramienta](./tool-mocks.md).

El [menú **Columnas**](./admin-ui.md#choosing-columns) ofrece dos columnas más que empiezan ocultas. **Flujo de trabajo** muestra el flujo de trabajo del que procede la ejecución con su nombre actual y enlaza a él: el nombre de cada fila es una instantánea fijada al iniciarse la ejecución, así que esta columna permite ver cómo se llama hoy ese flujo de trabajo. **Borrador** muestra una marca de verificación en las [ejecuciones de prueba](./workflows.md#running-a-workflow): las iniciadas desde un flujo de trabajo que seguía en `borrador` o desde las [ediciones sin publicar](./workflows.md#trying-the-edits-out) de uno `modificado`. En ambos casos se probó un diseño que nadie había aprobado, por lo que queda fuera de las [métricas de operaciones](../operations/metrics.md); la columna funciona como filtro Sí/No para ocultarlas.

La página de detalle de una ejecución muestra su **Versión**: la versión publicada del flujo de trabajo de la que copió sus tareas, como `v3`, o `—` en una ejecución de prueba, que ejecutó un diseño no registrado en ninguna versión. Consulta [Historial de versiones y reversión](./workflows.md#version-history).

## Estado de la ejecución {#run-status}

![Máquina de estados que muestra una ejecución que empieza en ejecución, pasa a programado mientras solo espera a que llegue una hora concreta y vuelve al reanudarse, y termina en completado cuando todas las tareas han finalizado sin fallos, o en fallido cuando todas han finalizado con al menos un fallo.](./img/workflow-executions-status.svg#gh-light-mode-only)
![Máquina de estados que muestra una ejecución que empieza en ejecución, pasa a programado mientras solo espera a que llegue una hora concreta y vuelve al reanudarse, y termina en completado cuando todas las tareas han finalizado sin fallos, o en fallido cuando todas han finalizado con al menos un fallo.](./img/workflow-executions-status-dark.svg#gh-dark-mode-only)

Una ejecución empieza en estado `en ejecución` y se cierra cuando tiene al menos una tarea y todas sus tareas han alcanzado un estado terminal: `completado`, `fallido` u `omitido`. Una ejecución cuyas tareas incluyan un fallo termina en `fallido`. La hora de finalización se registra en ese momento y ninguna edición posterior la cambia, y una ejecución sin ninguna tarea permanece en `en ejecución`. Estos son los números que cuentan las [métricas de operaciones](../operations/metrics.md).

Mientras una ejecución sin terminar no tiene nada que hacer salvo esperar a que llegue una hora concreta (una tarea pidió esperar, su sesión muestra **Programada hasta …** y todas las demás sesiones están inactivas o terminadas), la ejecución muestra `programado` en lugar de `en ejecución`. Vuelve a `en ejecución` en cuanto se reanuda una sesión, ya sea porque ha llegado la hora o porque alguien le ha enviado un mensaje. Las [métricas de operaciones](../operations/metrics.md) cuentan una ejecución en estado `programado` como activa, igual que una en estado `en ejecución`.

Cuando una tarea falla, cualquier tarea que siga esperándola, directamente o más abajo en la cadena, pasa a `omitido`, puesto que ya no puede ejecutarse; eso es lo que permite que la ejecución se cierre en lugar de quedarse colgada de una tarea que nunca empezará. Las tareas de ramas que no dependen de la fallida no se ven afectadas, así que una ejecución aún puede seguir en estado `en ejecución` durante un tiempo tras un fallo, hasta que esas también terminen.

## La pantalla de la sesión del flujo de trabajo {#the-workflow-session-screen}

La sesión del flujo de trabajo es el chat en el que transcurre una ejecución. Se abre con el mensaje inicial de la ejecución y con el agente ya trabajando: la ejecución empieza en cuanto se crea, abra o no alguien esta pantalla.

![Diagrama de flujo que muestra la disposición de la pantalla de la sesión del flujo de trabajo: la cronología de tareas y los mensajes agrupados por tarea están uno junto al otro, y los mensajes conducen a la entrada del chat.](./img/workflow-executions-layout.svg#gh-light-mode-only)
![Diagrama de flujo que muestra la disposición de la pantalla de la sesión del flujo de trabajo: la cronología de tareas y los mensajes agrupados por tarea están uno junto al otro, y los mensajes conducen a la entrada del chat.](./img/workflow-executions-layout-dark.svg#gh-dark-mode-only)

### Quién la comparte {#who-shares-it}

El chat de una ejecución lo **comparten sus participantes**; no es privado de quien la inició:

| Quién | Qué obtiene |
|---|---|
| El **iniciador** que inició la ejecución | Toda la conversación y la entrada del chat |
| Un **aprobador designado** de una de sus [aprobaciones](./approvals.md) | La misma conversación y el mismo estado: aprobar reanuda la ejecución original en lugar de iniciar una nueva y vacía. Lo único sobre lo que puede actuar es su aprobación: un formulario de entrada que el agente muestre para cualquier otro paso, o una [confirmación que pida un servidor MCP](#mcp-server-confirmations), es de solo lectura para él, con la nota «Esperando la respuesta del iniciador.» debajo |
| Un **Administrador** del tenant | Visibilidad de solo lectura |
| Cualquier otra persona | Sin acceso |

Cuando una aprobación se dirige a un **grupo**, todos los miembros con el rol Aprobador son participantes, así que el chat sigue a los miembros del grupo: añadir a alguien a un grupo de aprobadores le abre todas las ejecuciones que se ha pedido aprobar a ese grupo, y quitarlo se las vuelve a cerrar. Es la consecuencia directa de que «cualquier miembro puede resolverla»: decidir es para lo que existe el acceso al chat. Un miembro sin el rol Aprobador no obtiene nada por pertenecer al grupo.

### Avatares de remitente {#sender-avatars}

Como varias personas publican en un mismo chat (el solicitante, los aprobadores y el agente), cada mensaje lleva un **avatar de remitente**. Al pasar el cursor por encima se muestra el nombre del remitente; la insignia del agente muestra el nombre del flujo de trabajo. El clic en un botón dentro de una superficie interactiva renderizada se atribuye de la misma manera: junto a esa superficie aparece el avatar del usuario que actuó, una vez resuelto el clic.

### La cronología de tareas {#the-task-timeline}

Una **cronología de tareas** contraíble recorre el borde izquierdo: las tareas de la ejecución en orden, cada una con una insignia numerada y coloreada según su estado, con la que está en curso resaltada. El chat envuelve cada serie de mensajes consecutivos de una misma tarea en un **grupo de tarea** (un riel izquierdo coloreado según el estado, con un encabezado numerado que coincide con la insignia de la cronología), de modo que el límite de cada tarea se ve de un vistazo.

Ambos están vinculados en los dos sentidos:

- Al desplazar el chat se resalta en la cronología la tarea situada en la parte superior de la vista.
- Al pasar el cursor por una entrada de la cronología o por un grupo del chat se resalta su homólogo.
- Al hacer clic en una entrada de la cronología, el chat se desplaza hasta el grupo de esa tarea.

### Actualizaciones en directo {#live-updates}

Todos los participantes que observan la ejecución ven cada respuesta a medida que se escribe, sea quien sea el autor del mensaje que la originó, y también los turnos que A2Flow ejecuta por su cuenta, como el inicio, la reanudación tras una aprobación y la reanudación de una sesión que esperaba a que llegara una hora concreta. La vista sigue los mensajes nuevos hasta el final solo si ya estás cerca del final.

Un mensaje que envías espera al agente: mientras este sigue trabajando en un turno, el mensaje se rechaza y puedes volver a enviarlo cuando la respuesta haya terminado. Una sesión que espera una aprobación no admite mensajes, porque lo que la hace avanzar es la decisión de la aprobación. Una pregunta que envíes entonces va, en su lugar, a una [consulta](#consultations).

La [sesión de diseño](./workflows.md#adjusting-the-task-templates) también es un chat compartido, con los mismos avatares. La comparten los Desarrolladores del tenant en lugar de los participantes de una ejecución, y se actualiza sola cada pocos segundos en lugar de mostrar las respuestas de los demás a medida que se escriben.

### Sesiones de rama {#branch-sessions}

Cuando el grafo de tareas de la ejecución se ramifica, A2Flow puede repartir la ejecución en varias sesiones para que las ramas avancen a la vez; consulta [Ramas paralelas](../architecture/workflow-execution.md#parallel-branches). Aparece entonces una fila de pestañas debajo de la ruta de navegación, una por sesión, cada una con su estado:

| Pestaña | Qué es |
|---|---|
| **Principal** | La sesión en la que empezó la ejecución. Se ocupa de las uniones y de las tareas que siguen a una rama terminada |
| **Rama 1**, **Rama 2**, … | Una sesión de rama, bifurcada cuando una rama quedó lista mientras su sesión estaba ocupada |
| **Consulta 1**, … | Una [consulta](#consultations), abierta por una pregunta hecha mientras una sesión esperaba una aprobación |

| Estado | Significado |
|---|---|
| En cola | Un turno está a punto de empezar |
| En ejecución | El agente está trabajando |
| Esperando entrada | Un formulario de entrada espera una respuesta |
| Esperando aprobación | Una aprobación solicitada por esta sesión sigue sin decidirse |
| Esperando al iniciador | La siguiente tarea [hará preguntas al iniciador](#mcp-server-confirmations) mientras se ejecuta, así que espera a que este la reanude desde el chat |
| Programada hasta … | Una tarea debe esperar hasta una hora concreta; la sesión se reanuda sola a la hora indicada. Un mensaje enviado a ella la reanuda antes |
| Inactiva | Ahora mismo no hay nada que hacer; la sesión espera su siguiente tarea |
| Terminada | La sesión terminó su trabajo. Una rama terminada deja un resumen para la sesión principal |
| Error | El último turno falló |

Haz clic en una pestaña para abrir el chat de esa sesión; la vista sigue a la sesión seleccionada y la URL la conserva, de modo que un enlace a la página abre la misma pestaña. Una ejecución que nunca se ramifica y no tiene ninguna consulta no muestra pestañas.

### Consultas {#consultations}

Una sesión que espera una aprobación no admite mensajes, pero la solicitud puede seguir planteando preguntas, como cuánto costará la instancia o por qué se eligió este destino. Mientras la sesión espera, una nota sobre la entrada del chat indica que las preguntas van a una consulta.

1. Escribe la pregunta en el chat de la sesión en espera y envíala.
2. Se abre una pestaña **Consulta** con tu pregunta, y el agente responde allí. Parte de todo lo que la sesión en espera sabía hasta la solicitud de aprobación y también puede leer las [bases de conocimiento](./knowledge-bases.md) vinculadas al flujo de trabajo. No puede usar las herramientas de los servidores MCP, así que una pregunta que requiera volver a mirar el sistema de destino tendrá que esperar a que la ejecución continúe.
3. Sigue preguntando en esa pestaña. Todos los que comparten el chat pueden escribir allí, así que el aprobador y la persona que inició la ejecución también pueden hablar de la solicitud entre sí. Cada mensaje muestra quién lo envió.
4. Decide la aprobación como siempre. La decisión cierra la consulta: su pestaña cambia a **Terminada** y ya no admite más mensajes.

| Una consulta | |
|---|---|
| Puede | Responder a partir del contexto de la solicitud, las bases de conocimiento vinculadas, las tareas y aprobaciones de la ejecución y los archivos de la sesión |
| No puede | Usar ninguna herramienta de un servidor MCP, cambiar una tarea, solicitar una aprobación, programar una espera ni añadir un archivo |
| Deja tras de sí | Nada en la ejecución. La sesión en espera nunca ve lo que se dijo allí; la conversación sigue pudiendo leerse en su pestaña |

Otra pregunta hecha antes de que se decida la misma aprobación va a la misma consulta.

### Respuestas sugeridas {#suggested-replies}

Cuando el agente se detiene a esperarte (hizo una pregunta, quiere un valor o necesita tu visto bueno), aparece una fila de **respuestas sugeridas** sobre la entrada del chat: unas pocas respuestas breves que espera, como `Sí, adelante` u `Omite este paso`.

| | |
|---|---|
| **Al hacer clic en una** | Pone ese texto en la entrada del chat. No se envía nada: edítalo o envíalo tal cual |
| **Mientras el agente trabaja** | La fila se oculta; vuelve con la siguiente pregunta del agente |
| **Después de responder** | La fila desaparece, y la siguiente pregunta trae sus propias sugerencias |
| **Tras recargar** | Ahí sigue la misma fila, para todos los participantes que pueden enviar |

Las sugerencias son lo que el agente cree que escribirías, no un menú con las únicas respuestas permitidas: una pregunta con un conjunto fijo de respuestas se formula como una opción dentro del mensaje. La fila es una función de la sesión del flujo de trabajo; la sesión de diseño no la tiene.

### Confirmaciones de un servidor MCP {#mcp-server-confirmations}

Algunos servidores MCP se detienen en mitad de una llamada a una herramienta para preguntar algo a una persona antes de continuar; Azure MCP Server, por ejemplo, pide consentimiento antes de cada operación sobre un secreto de Key Vault. Una herramienta así se marca como **que pregunta al iniciador** en el diseño del flujo de trabajo: indica al agente de diseño qué herramienta de qué tarea pregunta, al generar el flujo de trabajo o en su sesión de diseño. Una herramienta sin marcar no puede preguntar, y su llamada falla en lugar de esperar.

Una tarea que usa una herramienta marcada espera al iniciador de la ejecución antes de empezar, para que esté presente cuando lleguen las preguntas:

1. Cuando la ejecución llega a la tarea, su sesión muestra **Esperando al iniciador** y el iniciador recibe una [notificación](./notifications.md) `solicitud de entrada`. Mientras tanto, no corre ningún plazo.
2. El iniciador abre el chat de la ejecución. Sobre la entrada del chat, una nota indica la tarea, con un botón **Reanudar**. Los demás solo ven que la ejecución espera al iniciador.
3. **Reanudar** envía un mensaje en nombre del iniciador y la tarea empieza. Escribir cualquier mensaje propio tiene el mismo efecto.
4. Cada pregunta aparece en el chat como una tarjeta titulada «*servidor* solicita confirmación», que nombra la herramienta que está a la espera, con un pequeño formulario debajo.


| | |
|---|---|
| **Quién responde** | Solo el iniciador de la ejecución. Los aprobadores y Administradores ven la pregunta con «Esperando la respuesta del iniciador.» debajo |
| **Aceptar** | Envía los valores del formulario. Su significado depende del servidor: el formulario de Azure MCP Server es una elección entre **Approve** y **Reject** |
| **Rechazar** | Se niega a responder |
| **Cancelar** | Descarta la pregunta sin elegir |
| **Mientras espera** | El turno del agente sigue en curso, así que la entrada del chat permanece deshabilitada |
| **Si nadie responde** | La pregunta caduca (a los 15 minutos, salvo que el despliegue [indique otra cosa](../operations/configuration.md#mcp-tools-and-approvals)) y se comunica al servidor que se descartó |

La tarjeta pertenece al turno que preguntó. Cuando ese turno termina, lo que registra el resultado es la propia línea de la llamada a la herramienta en el chat.

### Archivos en la sesión {#files-in-the-session}

Una sesión del flujo de trabajo contiene archivos además de mensajes. Adjunta uno con el botón del **clip** que hay junto a la entrada del chat o suéltalo en cualquier parte del cuadro de entrada: cada archivo aparece como un chip sobre el cuadro, y la × del chip lo quita. No se envía nada hasta que envías el mensaje, así que quitar un chip simplemente descarta ese archivo: nunca llega a la ejecución.

El mensaje que envías indica lo que lo acompañaba, de modo que la transcripción sigue mostrando el adjunto tras recargar. El servidor informa al agente de los archivos por separado, y este puede hacer lo siguiente:

| Puede | No puede |
|---|---|
| Listar los archivos de la sesión | Cambiar un archivo que haya adjuntado alguien |
| Leer uno, siempre que sea de texto | Eliminar un archivo |
| Añadir un archivo nuevo propio | Acceder a los archivos de otra ejecución |

Un archivo que escribe el agente aparece en el chat como una tarjeta con un botón **Descargar**. Como el agente solo añade, un archivo que escribe con un nombre que ya existe en la sesión se guarda con una variante numerada (`report (2).csv`) en lugar de reemplazar lo que hay; la tarjeta nombra el archivo tal como se guardó realmente.

La lectura se limita al texto. Una hoja de cálculo, una imagen o un archivo comprimido se guardan y descargan intactos, pero el agente no puede leerlos; dale una exportación de texto si necesita el contenido.

| | |
|---|---|
| **Quién puede adjuntar** | El iniciador de la ejecución y sus aprobadores designados, las mismas personas que pueden hacerla avanzar. Un Administrador que solo observa no puede adjuntar |
| **Quién puede descargar** | Todos los que pueden leer el chat, incluidos los Administradores |
| **Cuánto duran** | Lo mismo que la ejecución. Al eliminar la ejecución se eliminan sus archivos |
| **Límites de tamaño** | Se definen por despliegue; consulta [Configuración](../operations/configuration.md#session-files) |

Una vez enviados, los archivos no se pueden quitar de uno en uno, así que los archivos de una sesión desaparecen cuando lo hace la ejecución.

## Tareas del flujo de trabajo {#workflow-tasks}

Aquí las tareas de la ejecución son de solo lectura: las plantillas se editan en el [flujo de trabajo](./workflows.md#adjusting-the-task-templates), y los estados de una ejecución los hacen avanzar el agente de ejecución y el flujo de aprobación.

Cada tarea lleva un estado (`pendiente`, `en curso`, `completado`, `fallido` u `omitido`) y sus dependencias. Un conmutador **Tabla / Gráfico** alterna entre la lista y el gráfico de dependencias, que apila las tareas en una sola columna vertical por orden de dependencia, con los requisitos previos encima de las tareas que dependen de ellos, y cada una se ramifica hacia la derecha en los servidores MCP de los que vincula herramientas y luego en las herramientas individuales. El gráfico permite desplazarse, hacer zoom y ajustar la vista; no permite editar.

## Invocaciones de herramientas {#tool-invocations}

Esta página enumera las llamadas a herramientas MCP realizadas durante la ejecución y lo que el [gateway](../architecture/mcp-gateway-and-proxy.md) decidió sobre cada una: las llamadas `permitido` que llegaron al servidor de destino y las `denegado` que una regla vetó, con la herramienta, el servidor, el motivo de la denegación y el [certificado de herramienta](./approvals.md#human-approval) presentado. Los argumentos solo aparecen como un resumen; los valores en bruto nunca se guardan.

Las llamadas a una herramienta [simulada](./tool-mocks.md) no aparecen aquí, sea cual sea su resultado. El gateway comprueba una llamada simulada como cualquier otra, pero una llamada que desde el principio iba a responderse con una respuesta guardada no llega a ningún servidor, así que ni su aprobación ni su rechazo pertenecen a este registro. Una llamada simulada se inspecciona en la transcripción del chat de la ejecución.

## Eliminar una ejecución {#deleting-a-run}

La acción **Eliminar** de una fila quita la ejecución tras un mensaje de confirmación: se eliminan el registro, sus tareas y su sesión del flujo de trabajo.
