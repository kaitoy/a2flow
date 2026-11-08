---
title: Escalado horizontal
sidebar_position: 3
---

# Escalado horizontal

El frontend no guarda estado propio ni conserva nada entre solicitudes, así que escala libremente; y cuando el proxy inverso dirige `/api/*` directamente al backend, como se describe en [Despliegue](./deployment.md), los streams del chat ni siquiera pasan por él. Todo lo que sigue se refiere al backend.

## Qué requiere ejecutar más de una réplica {#what-running-more-than-one-replica-requires}

| Requisito | Motivo |
|---|---|
| **PostgreSQL** | SQLite admite un solo escritor y un solo proceso. Todas las réplicas comparten una base de datos, que es también lo que las coordina |
| **Un `SKILLS_DIR` compartido** | Cada réplica debe montar el mismo [almacén de skills de agente](./configuration.md#agent-skill-store) (ReadWriteMany). Una ejecución queda fijada a la revisión de la skill con la que empezó, y cualquier réplica puede atender la siguiente solicitud de esa ejecución |
| **Ningún proxy de agrupación por transacción** | Consulta [Agrupación de conexiones](#connection-pooling) más abajo |
| **Un `MCP_PROXY_TLS_DIR` compartido** | Cada réplica escribe y lee ahí el material que la identifica ante el [proxy MCP](../architecture/mcp-gateway-and-proxy.md#the-sandbox), y el proxy lee el mismo directorio. Una réplica con el suyo propio emitiría material que el proxy nunca ha visto |
| Sesiones persistentes | No son necesarias. El bloqueo consultivo de abajo hace el trabajo para el que se recurriría a la afinidad de enrutamiento |

El propio proxy MCP escala con sus propias reglas: entre llamadas no guarda nada más que una caché de descargas, así que sus réplicas no necesitan ninguna coordinación; pueden compartir `MCP_SANDBOX_DIR` o tener cada una el suyo. Dimensiónalo según cuántas llamadas a herramientas se ejecutan a la vez, no según cuántas réplicas del backend hay.

## Un solo conductor por conversación {#one-driver-per-conversation}

Las escrituras en una conversación ya son seguras entre réplicas: el servicio de sesiones toma `SELECT ... FOR UPDATE` sobre la fila a la que añade datos durante toda la transacción, de modo que las adiciones se serializan y no se pueden perder ni el estado de la conversación ni sus filas de eventos.

Las lecturas son la parte que necesita ayuda. El runtime del agente mantiene una sesión en memoria durante toda una invocación, así que los eventos que otra réplica añade en ese intervalo nunca le llegan, y el resto de la ejecución razona sobre una conversación a la que le faltan. Serializar las escrituras no puede remediarlo; solo puede hacerlo mantener una sesión con un único conductor a la vez.

Por eso, cada ejecución de agente (`POST /api/v1/workflow-executions/{id}/agent`, `POST /api/v1/workflows/{id}/agent`) toma un **bloqueo consultivo de PostgreSQL a nivel de sesión** y lo mantiene durante todo el stream SSE:

![Diagrama de secuencia de dos réplicas que compiten por ejecutar la misma sesión: la réplica 1 toma un bloqueo consultivo de PostgreSQL y abre el stream para el cliente A, mientras que la solicitud posterior a la réplica 2 para la misma sesión se rechaza con 409 mientras se mantiene el bloqueo, y este solo se libera cuando termina el stream de la réplica 1.](./img/scaling-lock-race.svg#gh-light-mode-only)
![Diagrama de secuencia de dos réplicas que compiten por ejecutar la misma sesión: la réplica 1 toma un bloqueo consultivo de PostgreSQL y abre el stream para el cliente A, mientras que la solicitud posterior a la réplica 2 para la misma sesión se rechaza con 409 mientras se mantiene el bloqueo, y este solo se libera cuando termina el stream de la réplica 1.](./img/scaling-lock-race-dark.svg#gh-dark-mode-only)

Una segunda ejecución simultánea de la misma sesión se rechaza antes de enviar ninguna cabecera SSE, en lugar de dejar que diverja en silencio. Las sesiones distintas nunca compiten, y el bloqueo se espera brevemente antes de desistir, de modo que un cliente que interrumpe un stream y reintenta de inmediato no se rechaza mientras la ejecución abandonada aún se está cerrando.

La intervención humana no se ve afectada: una llamada a una herramienta del frontend termina la ejecución y cierra el stream, lo que libera el bloqueo, y la aprobación se reanuda como un turno *nuevo* que puede ejecutarse en cualquier réplica.

Cada réplica ejecuta además un **ejecutor de sesiones** que realiza los turnos que ningún navegador conduce: el inicio de una ejecución y su reanudación tras una aprobación. Toma el mismo bloqueo sin esperar, así que una sesión que ya se está ejecutando en otra parte se deja a esa réplica, y recoge cualquier turno que una réplica detenida haya dejado sin terminar. Cuántos de esos turnos ejecuta una réplica a la vez lo determina `SESSION_RUNNER_CONCURRENCY` (consulta la [referencia de configuración](./configuration.md#agent)).

## Migraciones de esquema durante un despliegue {#schema-migrations-during-a-rollout}

Cada réplica aplica las migraciones de esquema pendientes al arrancar y, en una base de datos nueva, también crea las cuentas y los ajustes iniciales. Varias réplicas que se despliegan a la vez lo intentarían todas al mismo tiempo, así que se turnan: la primera en arrancar hace el trabajo y las demás esperan a que termine, hasta diez minutos, antes de continuar sin nada pendiente. Una réplica que siga esperando pasado ese tiempo se detiene y su orquestador la reinicia.

## Agrupación de conexiones {#connection-pooling}

Como el bloqueo es a nivel de sesión y no de transacción, el despliegue no debe colocar un proxy de **agrupación por transacción** (PgBouncer en modo `transaction` y la mayoría de los agrupadores de PostgreSQL sin servidor) entre la aplicación y PostgreSQL. El bloqueo no sobreviviría entre sentencias. Lo mismo vale para las actualizaciones del chat en vivo: cada proceso del backend mantiene una conexión abierta para enterarse de los turnos escritos en otras réplicas, de modo que un chat abierto en una réplica muestra en el momento un turno que se ejecuta en otra. Se requiere agrupación a nivel de sesión o una conexión directa.

### Presupuesto de conexiones {#connection-budget}

Cada proceso del backend abre conexiones a la base de datos desde estas fuentes:

| Fuente | Conexiones |
|---|---|
| El grupo que atiende las solicitudes de la API | Hasta `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` |
| El grupo del historial de conversaciones | Hasta `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` |
| Cada ejecución de agente en curso: un chat abierto en un navegador o un turno que el servidor ejecuta por su cuenta (hasta `SESSION_RUNNER_CONCURRENCY` a la vez) | 1 durante toda la ejecución |
| El remitente del correo de notificación y los trabajos en segundo plano, como la actualización de una skill o la ingesta de una base de conocimiento | 1 cada uno mientras se ejecutan |
| Actualizaciones del chat en vivo desde otras réplicas | 1, siempre abierta |

Con los valores predeterminados, eso supone hasta 30 conexiones agrupadas por proceso, más una para las actualizaciones del chat en vivo y una por cada ejecución en curso. El `max_connections` predeterminado del propio PostgreSQL es 100, así que cuatro o cinco réplicas ocupadas pueden alcanzarlo. Antes de añadir réplicas, aumenta `max_connections` en el servidor o reduce `DB_POOL_SIZE` y `DB_MAX_OVERFLOW` (consulta la [referencia de configuración](./configuration.md#application-database)). Si aun así no basta, coloca PgBouncer en modo **session** delante de PostgreSQL.

## Correo de notificación {#notification-email}

El worker de correo saliente no necesita ninguna coordinación por tu parte: tanto si se ejecuta en los procesos de la API como si lo hace en uno dedicado, el bloqueo consultivo `email-queue` elige exactamente un remitente en todo el despliegue, de modo que las réplicas nunca envían por duplicado y el límite de velocidad configurado se mantiene exacto. Añadir réplicas del worker aporta conmutación por error, no rendimiento; consulta [Disposición de procesos](./deployment.md#process-layout).
