---
title: Terminología
sidebar_position: 1
---

# Terminología

Estos son los conceptos que sostienen casi todo el dominio y que conviene tener claros:

| Término | Qué es |
|---|---|
| **[Flujo de trabajo](../guides/workflows.md)** | Una unidad de trabajo reutilizable y diseñada de antemano: una skill de agente más las plantillas de tareas generadas para ella. |
| **Sesión de diseño** | El chat en el que se producen y refinan las plantillas de tareas de un flujo de trabajo. Hay exactamente una por flujo de trabajo y existe antes que cualquier ejecución. |
| **[Ejecución del flujo de trabajo](../guides/workflow-executions.md)** | Una ejecución concreta de un flujo de trabajo: los metadatos del flujo de trabajo y de la skill, capturados en el momento de ejecutar, y el elemento padre de los `WorkflowTask`, los `Approval` y los metadatos de mensajes de esa ejecución. |
| **Sesión del flujo de trabajo** | El chat en el que transcurre una ejecución: el equivalente, en tiempo de ejecución, de una sesión de diseño. |
| **Sesión de rama** | Una sesión bifurcada a partir de una sesión del flujo de trabajo cuando el grafo de tareas de la ejecución se ramifica, de modo que la rama avanza a la par que el resto de la ejecución. Termina con un resumen cuando acaba sus tareas. |
| **[Tenant](./tenants.md)** | El límite organizativo de nivel superior: casi todos los registros pertenecen exactamente a uno y ninguna solicitud pasa de uno a otro. |
| **[Grupo de usuarios](../guides/users-and-groups.md#user-groups)** | Un conjunto de usuarios con nombre dentro de un tenant, con una serie de roles que heredan todos sus miembros. |
| **[Etiqueta](../guides/tags.md)** | Una etiqueta común a todo el tenant para clasificar secretos, servidores MCP, skills de agente, bases de conocimiento, flujos de trabajo, mocks de herramientas y grupos de usuarios: un único vocabulario compartido por los siete. Una etiqueta marcada como **Control de acceso** también restringe los registros que la llevan a los miembros de los grupos que la tengan. |
| **[Skill de agente](../guides/agent-skills.md)** | Un procedimiento `SKILL.md` en un repositorio Git, versionado como el código; de él se genera un flujo de trabajo, y cada ejecución aplica su revisión publicada. |
| **[Base de conocimiento](../guides/knowledge-bases.md)** | Una wiki que el LLM redacta a partir de páginas web y documentos registrados, con una página por tema. Un flujo de trabajo vinculado a ella hace que sus agentes de diseño y de ejecución consulten ahí. |
| **[Servidor MCP](../guides/mcp-servers.md)** | Un servidor de Model Context Protocol registrado cuyas herramientas el agente puede vincular a las tareas de un flujo de trabajo. |
| **[Secreto](../guides/secrets.md)** | Un conjunto con nombre de entradas de credenciales de clave/valor, al que se hace referencia en otros lugares como `name/key` y que se resuelve de forma diferida en el momento de usarlo. |
| **[Certificado de herramienta](../guides/approvals.md#human-approval)** | El certificado X.509 de corta duración que una tarea debe presentar en cada llamada a una herramienta MCP. Congela el conjunto de herramientas de la tarea en el momento de emitirse, ya sea al concederse una aprobación o al iniciarse una tarea que a nadie se le pidió aprobar, e indica de quién es la autoridad que lleva. |
