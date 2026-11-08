---
title: Base de datos
sidebar_position: 7
---

# Base de datos

Todos los datos persistentes viven en una única base de datos relacional, seleccionada con `DB_URL` en `backend/.env`:

| Backend | `DB_URL` | Notas |
|---|---|---|
| SQLite (predeterminado) | `sqlite:///a2flow.db` | Archivo local sin configuración |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Lo usa la pila de Docker Compose |

El sufijo del controlador asíncrono (`aiosqlite` / `asyncpg`) se añade automáticamente. Los cambios de esquema se gestionan como migraciones versionadas de [Alembic](https://alembic.sqlalchemy.org/) y se aplican automáticamente al arrancar: volver a desplegar la aplicación (reiniciar un contenedor) es lo que ejecuta las migraciones pendientes, así que no hace falta ningún paso de migración aparte.

La base de datos es también lo que coordina un backend con varias réplicas: una ejecución del agente mantiene un bloqueo consultivo de PostgreSQL mientras dura su flujo SSE, de modo que dos réplicas nunca dirigen a la vez la misma conversación. Consulta [Escalado horizontal](../operations/scaling.md) para saber qué protege esto y qué restricción impone al agrupamiento de conexiones.

## Qué contiene {#what-it-holds}

| Tabla | Contiene |
|---|---|
| `users` | Los usuarios de la aplicación y los roles que se les han concedido; consulta [Usuarios y grupos](../guides/users-and-groups.md) |
| `auth_sessions` | Las sesiones de inicio de sesión del lado del servidor |
| `login_failures` | Los [inicios de sesión fallidos](../guides/users-and-groups.md#failed-sign-ins) recientes, que se cuentan para bloquear una cuenta ante intentos repetidos de adivinar la contraseña; las filas de más de un día se eliminan |
| `impersonation_events` | El registro de auditoría de las sesiones de [suplantación](../concepts/impersonation.md) |
| `agent_skills` | Las definiciones de [skills de agente](../guides/agent-skills.md) y el repositorio del que se clona cada una |
| `mcp_servers` | Los [servidores MCP](../guides/mcp-servers.md) registrados y cómo llegar a ellos |
| `knowledge_bases`, `knowledge_sources`, `knowledge_pages` | Las [bases de conocimiento](../guides/knowledge-bases.md): los documentos subidos y las URL registradas de cada una, y las páginas redactadas a partir de ellos |
| `secrets` | Los [conjuntos de credenciales](../guides/secrets.md) con nombre, cifrados localmente o referenciados en Vault |
| `workflows` | Las definiciones de [flujos de trabajo](../guides/workflows.md) y su estado en el ciclo de vida |
| `workflow_task_templates` | La lista de tareas diseñada de antemano de un flujo de trabajo |
| `workflow_published_versions` | El diseño congelado al publicar, con el que se ejecuta un flujo de trabajo `modificado` |
| `workflow_executions` | Una fila por [ejecución](../guides/workflow-executions.md), con los metadatos del flujo de trabajo y de la skill capturados al ejecutar |
| `workflow_tasks` | Las tareas individuales de una ejecución, copiadas de las plantillas |
| `workflow_task_tool_bindings` | Las herramientas MCP vinculadas a una tarea |
| `message_meta` | Datos por mensaje de los dos chats compartidos: quién envió un mensaje y qué tarea estaba en curso |

Eliminar un flujo de trabajo elimina en cascada sus plantillas, pero conserva intactas sus ejecuciones pasadas: una ejecución es un registro de lo que ocurrió, no parte del diseño del que procede.
