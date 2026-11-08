---
title: Diseñar un flujo de trabajo
sidebar_position: 2
---

# Diseñar un flujo de trabajo

Un flujo de trabajo nunca se crea desde cero. Se genera a partir de una [skill de agente](../guides/agent-skills.md), un repositorio Git que A2Flow clona y mantiene actualizado, y después se refina hasta que merece la pena congelar el diseño.

![Máquina de estados que muestra un flujo de trabajo que pasa de una skill de agente publicada, a través de la generación, a borrador o fallido, y luego de borrador a publicado y modificado, con la publicación volviendo desde modificado.](./img/workflow-design-status.svg#gh-light-mode-only)
![Máquina de estados que muestra un flujo de trabajo que pasa de una skill de agente publicada, a través de la generación, a borrador o fallido, y luego de borrador a publicado y modificado, con la publicación volviendo desde modificado.](./img/workflow-design-status-dark.svg#gh-dark-mode-only)

Con una skill sin revisión publicada no se puede generar ni ejecutar nada. Lo que siguen ambos agentes es el clon, así que, mientras no exista, no hay nada que seguir.

## La ejecución de diseño {#the-design-run}

Al generar, el flujo de trabajo se registra de inmediato y el trabajo de diseño se hace en segundo plano. Es una ejecución completa del agente contra un LLM, así que el registro se actualiza solo mientras avanza el trabajo, sin mantener una pantalla abierta para ello.

1. El prompt del diálogo Generar se envía como primer mensaje de la **sesión de diseño** del flujo de trabajo.
2. El agente de diseño lee la skill, divide la solicitud en pasos y los registra como **plantillas de tareas**: un grafo de dependencias en el que cada paso declara qué pasos deben terminar antes que él.
3. Para cada paso que lo necesite, vincula las herramientas MCP que ese paso puede llamar.
4. La conversación se resume en el **Prompt generado** del flujo de trabajo, el texto que recibe cada ejecución como contexto, junto con una breve **Descripción** para quienes lo ejecutan, y el flujo de trabajo pasa a `borrador`.

La solicitud escrita en el diálogo Generar no se guarda como campo del flujo de trabajo. Perdura como primer mensaje de la conversación de diseño; por eso se puede volver a abrir el mismo chat más adelante para refinar el resultado, y por eso una ejecución que no registró nada aún deja un punto de partida útil en lugar de un registro vacío.

## Qué contiene una plantilla de tarea {#what-a-task-template-carries}

| Una plantilla contiene | Notas |
|---|---|
| **Título y descripción** | El paso tal como lo leerá el agente de ejecución. Los títulos se mantienen breves para que se lean como chips en las listas de tareas. |
| **Depende de** | Aristas hacia otras plantillas del mismo flujo de trabajo. Se rechaza cualquier arista que cierre un ciclo. |
| **Herramientas MCP** | Los pares `(server, tool)` que este paso puede llamar, cada uno de los cuales indica si una [aprobación](./approvals.md) que cubra el paso debe limitar los valores con los que se llama. Las herramientas de solo lectura se marcan como que no necesitan aprobación de entrada; este es el único lugar donde se puede tomar esa decisión, ya que una ejecución no puede editar sus propias vinculaciones. |
| *Sin estado* | El ciclo de vida pertenece a una ejecución, no al diseño. |

Las plantillas se refinan desde el chat de diseño, desde los formularios de administración o combinando ambos; [Flujos de trabajo](../guides/workflows.md#adjusting-the-task-templates) explica esas pantallas. El agente de diseño edita directamente las plantillas y no ejecuta nada, y eso es lo que hace que la sesión de diseño se pueda compartir con seguridad con todo un equipo.

## Vincular herramientas durante el diseño {#binding-tools-at-design-time}

Elegir herramientas y llamarlas se rigen de forma distinta, a propósito.

| Operación | Quién la hace | Cómo se restringe |
|---|---|---|
| **Listar** lo que ofrece un servidor | El agente de diseño, mientras decide | Sin restricciones: descubrir herramientas es precisamente el objetivo de una ejecución de diseño |
| **Llamar** a una herramienta | El agente de ejecución, durante la ejecución | Solo las herramientas vinculadas a una tarea que la ejecución tenga en curso; consulta [Gateway y proxy MCP](./mcp-gateway-and-proxy.md) |

Por tanto, una vinculación escrita aquí no es una sugerencia para el modelo. Es la concesión que el [gateway](./mcp-gateway-and-proxy.md) hace cumplir durante la ejecución, y el conjunto que el [certificado](./approvals.md) de la tarea congela en el momento en que la tarea se inicia, o en el momento en que se concede su aprobación, si resulta que la necesita.

## Publicar {#publishing}

Publicar congela el diseño. El nombre del flujo de trabajo, su descripción, su prompt vigente y su lista completa de plantillas, con las aristas de dependencia y las vinculaciones de herramientas, se capturan como una nueva versión publicada numerada; las versiones anteriores permanecen en el [historial de versiones](../guides/workflows.md#version-history). En este punto no se ejecuta ninguna IA: publicar es una instantánea, no una revisión.

Editar después hace que el flujo de trabajo pase a `modificado` y no cambia nada de lo que se ejecuta: las ejecuciones siguen usando la versión publicada hasta que se vuelva a publicar. A una ejecución ya en marcha no le afecta en ningún caso, porque tomó su propia copia en el momento de iniciarse.

La versión publicada es también la única que ve la mayoría de la gente. Mientras un flujo de trabajo está `modificado`, su nombre, descripción, prompt y plantillas de tareas sin publicar solo se muestran a un **Desarrollador** o a un **Superadministrador**; todos los demás roles leen siempre la versión publicada (también en la lista de flujos de trabajo, donde la búsqueda y la ordenación por nombre siguen igualmente el nombre publicado) y ven el estado como `publicado`. Un Desarrollador puede ejecutar cualquiera de los dos diseños: el publicado, como solicitud real, o las ediciones, como [ejecución de prueba](../guides/workflows.md#trying-the-edits-out), que puede simular sus herramientas y queda fuera de las métricas de operaciones.
