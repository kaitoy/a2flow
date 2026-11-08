---
title: Sesiones
sidebar_position: 4
---

# Sesiones

Una sesión es un chat que comparten varias partes: el agente, la persona que lo abrió y cualquier otra a la que el trabajo involucre. También es donde el agente dibuja superficies interactivas, de modo que un intercambio puede ser un formulario que rellenar en lugar de un párrafo al que responder con texto.

## Quién la comparte {#who-shares-one}

| Sesión | La comparten | Todos los demás |
|---|---|---|
| **Sesión del flujo de trabajo** | El iniciador de la ejecución y el aprobador designado de cualquiera de sus [aprobaciones](./approvals.md) | Un Administrador del tenant la ve en solo lectura; nadie más tiene acceso |
| **Sesión de diseño** | Todos los Desarrolladores del tenant, además de los Superadministradores y el creador del flujo de trabajo | Sin acceso |

Una aprobación dirigida a un grupo incorpora a todos los miembros que tienen `approver`, de modo que el chat sigue la pertenencia al grupo: ese acceso existe precisamente para poder decidir. Como varias personas publican en una misma conversación, cada mensaje lleva un **avatar de remitente**, y cada participante ve todas las respuestas a medida que se escriben, sin recargar.

## Cómo transcurre un turno {#how-a-turn-runs}

![Diagrama de secuencia de un turno de chat: el mensaje del usuario viaja del frontend al backend y al modelo, la respuesta transmitida del modelo y cualquier superficie render_a2ui regresan, y la superficie rellenada por el usuario hace de nuevo el mismo recorrido de ida y vuelta.](./img/sessions-turn-flow.svg#gh-light-mode-only)
![Diagrama de secuencia de un turno de chat: el mensaje del usuario viaja del frontend al backend y al modelo, la respuesta transmitida del modelo y cualquier superficie render_a2ui regresan, y la superficie rellenada por el usuario hace de nuevo el mismo recorrido de ida y vuelta.](./img/sessions-turn-flow-dark.svg#gh-dark-mode-only)

El backend conecta el protocolo AG-UI con el agente: traduce los eventos en ambos sentidos, mantiene la conversación sincronizada y transmite los eventos al navegador a medida que llegan, de modo que el texto aparece de forma incremental y no en un solo bloque al final. El estado de la conversación se conserva bajo el ID del chat, así que al volver a abrirlo se continúa donde se dejó.

Una sesión del flujo de trabajo no necesita que nadie tenga el chat abierto: todos sus turnos los ejecuta el propio A2Flow. Esos turnos son el **arranque** de la ejecución, en cuanto se crea; el turno que la **reanuda** una vez decidida una [aprobación](../guides/approvals.md); el turno que la reanuda cuando llega el momento que una tarea [tenía que esperar](../guides/workflows.md#how-the-agent-works-through-the-tasks); y el turno que responde a lo que envíe un participante. El chat solo le entrega el mensaje a A2Flow y muestra el turno mientras se ejecuta, a todos los que estén mirando, en el servidor en el que se ejecute. (La sesión de diseño es la excepción: sus turnos se siguen ejecutando desde el chat del Desarrollador que envió el mensaje).

## Superficies interactivas {#interactive-surfaces}

La herramienta `render_a2ui` la adjunta el frontend o, en un turno que ejecuta el propio A2Flow, el backend con esa misma definición, y lleva el esquema del catálogo de componentes de [A2UI](https://a2ui.org) con el que el agente puede dibujar. Cuando el modelo la llama, el backend no ejecuta nada: reenvía la llamada, y es el navegador quien dibuja el resultado.

| Componente | Para qué se usa |
|---|---|
| `Text`, `Card`, `Row`, `Column` | Estructura y texto |
| `TextField` | Entrada libre |
| Un selector de opciones | Elegir entre los valores permitidos. Un selector de opción única con cinco o más opciones se contrae en una lista desplegable, de modo que el agente puede listar todos los tipos de instancia o regiones de EC2 sin sepultar la conversación |
| `Button` | Enviar la superficie |

Al hacer clic en un botón se devuelve **todo el modelo de datos** de la superficie: cada valor escrito o seleccionado, no solo el botón pulsado. Eso es lo que permite al agente responder a lo que el usuario introdujo realmente, y lo que permite que un chat recargado vuelva a mostrar una superficie ya respondida con los valores del propio usuario y no con los predeterminados del agente.

### La pregunta de un servidor durante una llamada {#a-servers-question-mid-call}

Hay una superficie que el agente no dibuja. Un servidor MCP puede detenerse a mitad de una llamada a una herramienta para preguntarle algo a una persona (una *elicitation*), y la llamada sigue abierta mientras espera. Solo puede hacerlo una herramienta que el diseño del flujo de trabajo haya marcado como que pregunta, y una tarea que use una de ellas no empieza hasta que el iniciador de la ejecución esté en el chat: la sesión se detiene en **Esperando al iniciador**, se notifica al iniciador y la tarea empieza en el turno que inicia su **Reanudar**. A continuación, A2Flow registra la pregunta y la añade al flujo del turno en curso como una actividad propia, de modo que todos los espectadores la ven al instante. La respuesta pasa por una ruta específica y no por la entrada del chat, porque la sesión sigue en mitad de un turno: quien la recoge es la llamada a la herramienta en espera, no un turno nuevo. Consulta [Confirmaciones de un servidor MCP](../guides/workflow-executions.md#mcp-server-confirmations) para ver lo que ve la persona.

## La actividad del agente en el chat {#agent-activity-in-the-chat}

Para que puedas ver lo que hace el agente entre respuestas, su trabajo intermedio aparece integrado en el flujo del chat:

- **Indicador de actividad**: mientras una ejecución está en marcha pero aún no hay nada en pantalla, aparece un pulso discreto al final de la lista de mensajes.
- **Líneas de llamadas a herramientas**: cada llamada a una herramienta del backend (por ejemplo, `list_workflow_tasks`, `update_workflow_task`) se convierte en una línea de estado compacta que pasa de un indicador giratorio (`ejecutando…`) a una marca de verificación (`listo`). Las llamadas enrutadas a través del [gateway MCP](./mcp-gateway-and-proxy.md) se muestran con el **nombre real de la herramienta MCP** y una etiqueta `MCP`. Las herramientas de cliente `render_a2ui` y `render_approval`, la herramienta que escribe un archivo de sesión y la que propone las [respuestas sugeridas](../guides/workflow-executions.md#suggested-replies) conservan su interfaz específica y no se muestran como líneas de herramientas.
- **Detalles de la llamada**: una línea de herramienta con argumentos o resultado **se expande al hacer clic** para mostrar ambos como JSON con formato, de modo que se puede inspeccionar lo que el agente envió y recibió realmente sin salir del chat. Una línea respondida por un [mock de herramienta](./mcp-gateway-and-proxy.md#tool-mocks-and-dry-runs) lleva una insignia `Simulado`, y el chat es el *único* lugar donde inspeccionarla, ya que una llamada simulada nunca llega al proxy y, por tanto, no deja registro de auditoría.
- **Razonamiento**: cuando un modelo capaz de razonar transmite su razonamiento, los pensamientos se muestran en un panel atenuado «Pensando». Un modelo que razona internamente sin emitir resúmenes de sus pensamientos no genera ningún panel.

Al reanudar una sesión, las **llamadas a herramientas MCP**, las **tarjetas de archivo** y las **respuestas sugeridas** del último turno se reconstruyen a partir del historial; las demás llamadas a herramientas internas de A2Flow y el razonamiento solo se ven en vivo. Una tarjeta de archivo se reconstruye porque el archivo sobrevive a la ejecución que lo produjo y el chat es el único lugar donde aparece su enlace de descarga; las sugerencias se reconstruyen porque la pregunta a la que responden sigue abierta.

## Archivos en una sesión {#files-in-a-session}

Una sesión del flujo de trabajo contiene archivos además de mensajes: los que un participante adjuntó desde la entrada del chat y los que el agente escribió mientras trabajaba. Una sesión de diseño no tiene ninguno.

Los definen tres reglas:

- **Ámbito.** Un archivo pertenece exactamente a una ejecución. Nada apunta a un archivo sin nombrar la ejecución en la que está, de modo que los archivos de una sesión son inalcanzables desde otra.
- **Duración.** Los archivos duran tanto como su ejecución y se eliminan con ella. No hay una limpieza aparte ni caducidad.
- **Acceso.** No tienen permiso propio: para adjuntar hay que tener derecho a dirigir la ejecución, y para descargar, derecho a leer su chat. Son las mismas dos reglas que usa el propio chat.

El agente puede leer y añadir, pero nunca reemplazar ni quitar: una escritura con un nombre ya usado se guarda con una variante numerada. Así, un archivo que adjuntó un participante se queda exactamente como lo adjuntó, haga lo que haga la ejecución después.

Lo que el agente sabe de los archivos no procede del navegador. El servidor lee la lista de archivos de la sesión y la inyecta en el contexto de la ejecución junto con el prompt del flujo de trabajo, de la misma manera y por la misma razón: una lista proporcionada por el cliente sería una instrucción proporcionada por el cliente.

Los archivos se guardan en la base de datos, así que heredan su durabilidad y sus copias de seguridad, y no necesitan un volumen compartido entre réplicas. Las descargas siempre se sirven como adjunto con un tipo de contenido genérico, de modo que ningún navegador puede representar nada de lo que haya guardado un participante o el agente.
