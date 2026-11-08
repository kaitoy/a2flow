---
title: Métricas de operaciones
sidebar_position: 6
---

# Métricas de operaciones

Los datos de operaciones de los flujos de trabajo (acumulación de aprobaciones, volumen de ejecuciones, fallos y tiempo de entrega) se exponen para paneles de terceros de dos formas, ambas limitadas al tenant del llamante y, salvo la lista de fallos que se indica más abajo, disponibles para cualquier usuario autenticado.

Las ejecuciones que una [etiqueta de control de acceso](../guides/tags.md#access-control-tags) oculta al llamante quedan fuera de todas las vistas siguientes, igual que no aparecen en la propia lista de ejecuciones, de modo que una métrica nunca nombra una ejecución que su lector no podría abrir.

Las ejecuciones iniciadas desde un flujo de trabajo todavía en `borrador` (una [ejecución de prueba previa a la publicación](../guides/workflows.md#running-a-workflow) de un Desarrollador o Superadministrador) se registran con `isDraft: true` y **quedan excluidas de todas las métricas siguientes**, tanto los KPI de Prometheus como los subrecursos agregados, incluidas las vistas de aprobaciones acumuladas, para que los datos de prueba desechables nunca distorsionen las cifras. El indicador se fija cuando empieza la ejecución; publicar el flujo de trabajo después no reclasifica las ejecuciones que ya ocurrieron.

## Endpoint de Prometheus {#prometheus-endpoint}

`GET /api/v1/metrics` presenta los KPI de valor único en el formato de exposición de texto de [Prometheus](https://prometheus.io/). Cada muestra lleva una etiqueta `tenant`.

Aprobaciones:

| Métrica | Significado |
|---|---|
| `a2flow_approvals_pending` | Solicitudes de aprobación a la espera de una decisión |
| `a2flow_approvals_pending_over_threshold{threshold}` | De ellas, las que llevan esperando más que el umbral (24 h de forma predeterminada) |
| `a2flow_approval_pending_age_seconds_max` | Cuánto lleva esperando la solicitud más antigua |
| `a2flow_approvals_decided_today{decision}` | Aprobaciones decididas hoy, por `approved` / `rejected` / `returned` |

Ejecuciones de flujos de trabajo:

| Métrica | Significado |
|---|---|
| `a2flow_workflow_executions_active` | Ejecuciones actualmente en curso (`running` o `scheduled`) |
| `a2flow_workflow_executions_finished_today{status}` | Ejecuciones que han terminado hoy, por estado final |
| `a2flow_workflow_executions_started_recently{window,workflow}` | Ejecuciones iniciadas en las últimas 24 h, por flujo de trabajo |
| `a2flow_workflow_executions_failed_recently{window}` | Ejecuciones que han terminado con fallo en las últimas 24 h |
| `a2flow_workflow_tasks_failed_recently{window,error_kind}` | Tareas que han fallado en las últimas 24 h, por causa |
| `a2flow_workflow_execution_lead_time_seconds_avg{window,workflow}` | Duración media, de principio a fin, de las ejecuciones terminadas en las últimas 24 h |

Correo de notificación:

| Métrica | Significado |
|---|---|
| `a2flow_email_queue_depth{status}` | Correos en la [cola de salida](../guides/notifications.md#the-delivery-queue), por `pending` / `sending` / `sent` / `failed` |
| `a2flow_email_queue_oldest_pending_age_seconds` | Cuánto lleva esperando el correo sin entregar más antiguo; aumenta cuando el relé no está accesible |

`?thresholdHours=` anula el límite de las aprobaciones estancadas. `TIMEZONE` (un nombre IANA, `UTC` de forma predeterminada; consulta [Configuración del servidor](./configuration.md#server-settings)) determina dónde empieza «hoy»; un nombre no reconocido se sustituye por UTC en lugar de impedir el arranque.

El endpoint está protegido por la cookie de sesión normal, así que la configuración de scraping debe incluir una. `GET` es un método seguro, por lo que no hace falta un token CSRF:

```yaml
- job_name: a2flow
  metrics_path: /api/v1/metrics
  http_headers:
    Cookie: { values: ["a2flow_session=<token>"] }
```

El tiempo de inactividad de la sesión se desliza con cada solicitud, así que un scraping en marcha mantiene viva su propia sesión indefinidamente; no sobrevive a un reinicio del backend ni a un cierre de sesión explícito, que es cuando hay que renovar el token. Un scraping cubre exactamente un tenant; para vigilar varios, configura un job por tenant.

## Subrecursos agregados {#aggregate-sub-resources}

Todo aquello cuya clave natural sea un ID de usuario, un ID de ejecución o un mensaje de error de texto libre se mantiene deliberadamente fuera de Prometheus, porque son conjuntos de etiquetas sin límite. Esas vistas se sirven en su lugar como subrecursos JSON de las colecciones existentes, en el sobre habitual `{meta, data, error}`:

| Endpoint | Devuelve |
|---|---|
| `GET /api/v1/workflow-executions/by-workflow` | Recuentos de ejecuciones por flujo de trabajo (`total` / `running` / `completed` / `failed`; `running` incluye las ejecuciones `scheduled`) y tiempo de entrega medio |
| `GET /api/v1/workflow-executions/lead-time-trend` | Tiempo de entrega medio diario, un intervalo por día natural, incluidos los vacíos |
| `GET /api/v1/workflow-executions/failures` | Ejecuciones que requieren revisión, cada una con sus tareas fallidas y la causa registrada. Solo para Administrador, ya que cita títulos de tareas y mensajes de error de ejecuciones en las que el llamante puede no participar |
| `GET /api/v1/approvals/by-approver` | Aprobaciones pendientes acumuladas por aprobador designado |
| `GET /api/v1/approvals/by-workflow` | Las mismas aprobaciones acumuladas, agrupadas por flujo de trabajo |

Los endpoints de ejecuciones aceptan `since` / `until` (ISO-8601; de forma predeterminada los últimos 30 días, con un máximo de 366) y `limit`; los endpoints de aprobaciones aceptan `thresholdHours` (24 de forma predeterminada) y `limit`. Las entradas de aprobaciones acumuladas se devuelven ordenadas de mayor a menor espera individual, así que `?limit=5` son las cinco peores. Las duraciones son siempre segundos enteros.

`by-approver` agrupa por el **destino** de una aprobación, que puede ser un usuario o un grupo. Cada entrada lleva un `groupKind` con el valor `"user"` o `"group"` para distinguirlos: una entrada `"user"` da solo el ID, mientras que una entrada `"group"` lleva además el nombre del grupo en `groupLabel`.

Una tarea que falla registra el **motivo**: junto a `status="failed"` se guardan `error_kind` (uno de `api_error`, `timeout`, `script_error`, `invalid_input`, `permission_denied`, `rejected`, `other`) y un `error_message` de texto libre. Ambos son campos normales de la tarea, así que una lista de tareas se puede filtrar por ellos; p. ej., `?q=errorKind:eq:timeout`.
