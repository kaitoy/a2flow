---
title: Cómo funciona
sidebar_position: 1
---

# Cómo funciona

A2Flow convierte una [skill de agente](../guides/agent-skills.md) en un flujo de trabajo cuyos pasos quedan decididos antes de que se ejecute nada y, después, ejecuta ese flujo de trabajo dentro de un chat que comparten el agente y las personas implicadas. Cada etapa entrega a la siguiente una copia congelada de lo anterior, de modo que una ejecución se mantiene fiel a lo publicado aunque el diseño siga evolucionando.

![Diagrama de flujo que muestra una skill de agente a partir de la cual se genera un flujo de trabajo, que se lanza como una ejecución dentro de una sesión del flujo de trabajo, cuyas tareas solicitan aprobación humana o llaman a una herramienta MCP a través del gateway MCP para llegar a un servidor MCP.](./img/overview-lifecycle.svg#gh-light-mode-only)
![Diagrama de flujo que muestra una skill de agente a partir de la cual se genera un flujo de trabajo, que se lanza como una ejecución dentro de una sesión del flujo de trabajo, cuyas tareas solicitan aprobación humana o llaman a una herramienta MCP a través del gateway MCP para llegar a un servidor MCP.](./img/overview-lifecycle-dark.svg#gh-dark-mode-only)

| Etapa | Qué ocurre | Más información |
|---|---|---|
| **Diseñar** | Una skill se convierte en un flujo de trabajo: una ejecución de diseño con IA divide la solicitud en pasos y vincula las herramientas que necesita cada paso. | [Diseñar un flujo de trabajo](./workflow-design.md) |
| **Ejecutar** | Al ejecutar un flujo de trabajo, el diseño publicado se copia en una nueva ejecución y se abre su chat. | [Ejecutar un flujo de trabajo](./workflow-execution.md) |
| **Conversar** | El agente y varias personas comparten ese chat, y el agente puede dibujar en él superficies interactivas en lugar de limitarse a escribir texto. | [Sesiones](./sessions.md) |
| **Aprobar** | Una tarea que necesita una decisión humana no puede actuar hasta que alguien decide, y la decisión se firma en un certificado. Todas las demás tareas también llevan uno, con la autoridad de quien inició la ejecución. | [Barrera de aprobación](./approvals.md) |
| **Actuar** | Cada llamada a una herramienta la decide una cadena de políticas antes de salir de A2Flow, y queda registrada una vez decidida. | [Gateway y proxy MCP](./mcp-gateway-and-proxy.md) |

Detrás de todo esto hay dos almacenes: la [base de datos](./database.md) donde vive cada registro y el [almacenamiento de secretos](./secrets.md) del que se resuelven las credenciales.

## Los dos chats {#the-two-chats}

A2Flow tiene exactamente dos tipos de chat. Son el mismo mecanismo aplicado a agentes distintos, y la diferencia entre ellos está en lo que se le permite hacer a cada agente.

| Chat | Dirigido por | Qué puede hacer |
|---|---|---|
| **Sesión de diseño** | El agente de diseño, siguiendo la skill | Escribe y reorganiza las plantillas de tareas del flujo de trabajo. No ejecuta nada. |
| **Sesión del flujo de trabajo** | El agente de ejecución, siguiendo la revisión de la skill a la que está fijada la ejecución | Avanza por las tareas de la ejecución, pide aprobaciones y llama a herramientas MCP. |

Ninguno de los dos chats es un registro propio. Una sesión de diseño se identifica por su flujo de trabajo y una sesión del flujo de trabajo por su ejecución, y la conversación que hay detrás se crea con el primer uso y se conserva bajo ese ID; por eso, al volver a abrir cualquiera de ellas, se continúa donde se dejó.
