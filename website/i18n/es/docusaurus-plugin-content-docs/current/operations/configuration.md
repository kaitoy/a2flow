---
title: Referencia de configuración
sidebar_position: 2
---

# Referencia de configuración

Todos los ajustes siguientes son variables de entorno. El backend las lee de `backend/.env` ([backend/.env.example](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example) es la plantilla comentada); las dos variables del frontend se leen del entorno de proceso del propio frontend. Los ajustes del modelo y de la clave de API tienen su propia página en [Configuración del LLM](../getting-started/llm-configuration.md).

## Configuración del servidor {#server-settings}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `HOST` | `0.0.0.0` | Dirección en la que escucha el backend |
| `PORT` | `8000` | Puerto en el que escucha el backend |
| `RELOAD` | `false` | Recarga automática de uvicorn para el desarrollo local. Solo se lee cuando el backend se inicia con `python -m backend.main`; el comando de inicio de la imagen de Docker no se ve afectado en ningún caso |
| `TIMEZONE` | `UTC` | Nombre IANA de la zona horaria local del despliegue. Determina dónde empieza un día natural para las [métricas de operaciones](./metrics.md) (los recuentos de «hoy» y los intervalos diarios de la tendencia del tiempo de entrega), y es la zona en la que el agente del flujo de trabajo interpreta el requisito de hora de una tarea cuando este no indica zona horaria. Un nombre no reconocido se sustituye por `UTC` en lugar de impedir el arranque, así que una errata desajusta las horas locales en vez de detener la aplicación |
| `APP_BASE_URL` | — | La dirección en la que los usuarios abren este despliegue en un navegador: esquema, host y un puerto opcional, sin ruta, p. ej. `https://a2flow.example.com`. Los correos de notificación enlazan a ella, el [inicio de sesión único](#single-sign-on) construye a partir de ella su **URI de redirección** y fija los valores por defecto de `CORS_ORIGINS` y `SESSION_COOKIE_SECURE`. Con cualquier otra forma, el backend no arranca. Sin ella, los mensajes se envían sin enlace de vuelta y el inicio de sesión único no está disponible |

## Configuración del frontend {#frontend-settings}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Adónde reenvía el frontend `/api/*` cuando ningún proxy inverso lo dirige antes al backend (al trabajar sin contenedores), y dónde comprueba la sesión iniciada la página de documentación de la API. Se lee una vez al iniciar el proceso. En la pila de Docker Compose es la dirección del backend en la red interna, no una pública |
| `APP_PORT` | `3000` | Solo para Docker Compose: el puerto del host en el que se publica la aplicación, es decir, el del servicio `ingress`, que sirve tanto las pantallas como la API. Salvo que `.env` defina `APP_BASE_URL`, la pila pasa como URL base `http://localhost:` seguido de este puerto |
| `OPENBAO_PORT` | `8200` | Solo para Docker Compose, con `--profile openbao`: el puerto del host en el que se publica la interfaz de OpenBao; consulta [Probar secretos de Vault con OpenBao](../getting-started/docker-compose.md#openbao). A2Flow accede a él por la red interna en cualquier caso |

## Base de datos de la aplicación {#application-database}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `DB_URL` | `sqlite:///a2flow.db` | URL de la base de datos. Se admiten SQLite (relativa al directorio de trabajo) y PostgreSQL |
| `DB_POOL_SIZE` | `5` | Solo PostgreSQL. Conexiones que mantiene abiertas cada uno de los dos grupos de conexiones de un proceso del backend. Como mínimo `1`. Consulta [Agrupación de conexiones](./scaling.md#connection-pooling) para ver cómo se suman entre réplicas |
| `DB_MAX_OVERFLOW` | `10` | Solo PostgreSQL. Conexiones adicionales que cada grupo puede abrir por encima de `DB_POOL_SIZE` bajo carga, y que se cierran cuando la carga baja. Como mínimo `0` |

El sufijo del controlador asíncrono (`sqlite+aiosqlite` / `postgresql+asyncpg`) se añade automáticamente, así que basta con el esquema simple:

```env
DB_URL=postgresql://user:password@localhost:5432/a2flow
```

Los cambios de esquema se registran como migraciones versionadas de [Alembic](https://alembic.sqlalchemy.org/) y se aplican automáticamente al arrancar, de modo que es el propio redespliegue de la aplicación lo que pone el esquema al día. Ejecutar más de una réplica del backend requiere PostgreSQL; consulta [Escalado horizontal](./scaling.md). El contenido de cada tabla se describe en [Base de datos](../architecture/database.md).

## Usuarios iniciales {#seeded-users}

Al arrancar, el backend crea un **usuario del sistema** oculto y dos cuentas reales, cada una de ellas solo en el primer arranque que no encuentra su registro de destino:

- Un usuario inicial **`root`** con el rol **Superadministrador** (consulta [Autorización](../concepts/authorization.md)), de ámbito de plataforma (`tenantId: null`). Se omite en cuanto existe *cualquier* usuario real (que no sea del sistema), por lo que solo se ejecuta en el primer arranque de todos.
- Un tenant **Default** (`slug: default`) y, dentro de él, un usuario inicial **`admin`** con el rol **Administrador**. El tenant (por `slug`) y el usuario (por `username` dentro de ese tenant) se comprueban de forma independiente, así que cualquiera de los dos se puede volver a crear sin duplicar el otro.

El **usuario del sistema** oculto es el propietario de los registros de arranque (no puede iniciar sesión y queda excluido de la lista de usuarios).

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `ROOT_PASSWORD` | generada | Contraseña del usuario inicial `root` |
| `ADMIN_PASSWORD` | generada | Contraseña del usuario inicial `admin` del tenant Default |

Si alguna no está definida (o está vacía), se genera una contraseña aleatoria y se registra **una sola vez**, con nivel `WARNING`, al crear ese usuario; no se puede recuperar una vez que esa línea del registro haya pasado. Para cualquier uso que vaya más allá de las pruebas locales, define ambas explícitamente antes del primer arranque, o copia las contraseñas generadas de los registros de arranque de inmediato y cámbialas después. Los nombres de usuario son fijos: `root` y `admin`.

## Duración de la sesión {#session-lifetime}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `SESSION_IDLE_TIMEOUT_SECONDS` | `28800` (8 horas) | Tiempo de inactividad deslizante. Las solicitudes autenticadas renuevan la hora de última actividad de la sesión, como máximo una vez cada 5 minutos (o la mitad de este valor, si es menor), por lo que una sesión puede terminar hasta ese tiempo antes; una sesión inactiva durante más tiempo se rechaza y se elimina |
| `SESSION_COOKIE_SECURE` | `true` si `APP_BASE_URL` empieza por `https://`; si no, `false` | Marca las cookies de sesión y CSRF como `Secure` (solo HTTPS). Defínela solo para cambiar ese valor por defecto |

Las propias cookies son cookies de sesión (sin `Max-Age` ni `Expires`), así que también se borran al cerrar el navegador. El navegador llega al backend en el mismo origen que el frontend (`/api/*` se dirige a él por ruta, ya sea en el proxy inverso o en el propio frontend), de modo que las cookies son de origen propio y `SameSite=Lax` se aplica sin problemas.

## CORS {#cors}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `CORS_ORIGINS` | `APP_BASE_URL`, o `http://localhost:3000` sin ella | Lista separada por comas de los orígenes autorizados a llamar a la API del backend |

Añade cada origen desde el que se sirve el frontend:

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` se rechaza al arrancar: `allow_credentials=True` está siempre activado, y combinarlo con un origen comodín no es válido según la especificación de CORS.

## Inicio de sesión único {#single-sign-on}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `OIDC_ALLOWED_PRIVATE_HOSTS` | vacío | Nombres de host separados por comas, como `keycloak.internal,localhost`, que la URL del emisor del [inicio de sesión único](../guides/single-sign-on.md) de un tenant puede tener aunque se resuelvan a una dirección privada; sirve para un proveedor de identidad local. Cualquier otro emisor debe resolverse a una dirección pública |

El inicio de sesión único depende también de la URL base del despliegue, `APP_BASE_URL` (consulta [Configuración del servidor](#server-settings)). Sin ella, el inicio de sesión único no está disponible y **Configuración del tenant** muestra un aviso en lugar de la **URI de redirección**. Dos requisitos:

- **La URL base es solo el origen**: esquema, host y un puerto opcional, como `https://a2flow.example.com`, sin ruta. El backend no arranca con ningún otro valor.
- **El backend debe ver el origen público.** Detrás de un proxy inverso, haz que el proxy conserve la cabecera `Host` original al reenviar una petición y que establezca `X-Forwarded-Proto` con el esquema original, y haz que el backend confíe en el proxy indicando su dirección en `FORWARDED_ALLOW_IPS` (por defecto solo se confía en `127.0.0.1`). Si no, cada inicio de sesión SSO requiere una redirección adicional.

## Almacén de skills de agente {#agent-skill-store}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `SKILLS_DIR` | `backend/.skills` | Raíz del almacén en el que se clonan de forma superficial los repositorios de skills de agente. Con `docker compose` es `/var/lib/a2flow/skills`, respaldado por el volumen con nombre `skills` |
| `SKILLS_PRUNE_GRACE_SECONDS` | `3600` | Tiempo que sobrevive el directorio de una revisión, lo referencie algo o no. Una actualización elimina las revisiones a las que no está fijada ninguna ejecución, y el periodo de gracia cubre el intervalo entre que una ejecución lee la revisión actual e inserta la fila que la nombra |
| `SKILLS_CLONE_TIMEOUT_SECONDS` | `120` | Limita cuánto pueden tardar las solicitudes HTTP individuales de una clonación. Sin él, un remoto que no responde bloquea la clonación indefinidamente y deja la skill en `Clonando` |

El almacén guarda un directorio inmutable por revisión, y una revisión no se modifica nunca una vez publicada, así que una actualización nunca molesta a un agente que esté cargando una existente:

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

Esto es **estado duradero, no una caché**: una ejecución queda fijada a la revisión con la que empezó, por lo que borrar el directorio deja a las ejecuciones existentes sin poder cargar su skill (HTTP 409 `SKILL_NOT_READY`) hasta que un administrador vuelva a actualizarla, y una actualización obtiene el HEAD actual del repositorio, no la revisión fijada. Haz copia de seguridad ([Copia de seguridad y restauración](./backup.md)) y da a todas las réplicas del backend el mismo directorio ([Escalado horizontal](./scaling.md)).

## Bases de conocimiento {#knowledge-bases}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `KNOWLEDGE_SOURCE_MAX_BYTES` | `20971520` (20 MiB) | Documento más grande que se puede subir a una [base de conocimiento](../guides/knowledge-bases.md) y página web más grande que se descarga para ella. Una subida mayor se rechaza en cuanto supera este límite |
| `KNOWLEDGE_INGEST_CHUNK_CHARS` | `40000` | Caracteres de una fuente que el LLM lee cada vez. Una fuente más larga se lee por partes, una tras otra. Redúcelo para un modelo con una ventana de contexto pequeña |
| `KNOWLEDGE_FETCH_TIMEOUT_SECONDS` | `30` | Tiempo que puede tardar, por solicitud, la descarga de una fuente de página web |

Las fuentes y las páginas se guardan en la base de datos, igual que los archivos de sesión, así que no necesitan un volumen propio. Leer una fuente llama al LLM configurado para los agentes ([Configuración del LLM](../getting-started/llm-configuration.md)), varias veces en el caso de un documento grande.

## Archivos de sesión {#session-files}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `SESSION_FILE_MAX_BYTES` | `20971520` (20 MiB) | Tamaño máximo de un solo archivo que se puede adjuntar a una [sesión del flujo de trabajo](../guides/workflow-executions.md#files-in-the-session). Una subida se rechaza en cuanto supera este límite, de modo que nunca se retiene entero un cuerpo mayor |
| `SESSION_FILES_MAX_TOTAL_BYTES` | `209715200` (200 MiB) | Tamaño combinado de todo lo que contiene una sesión. Los archivos solo se eliminan cuando se elimina su ejecución, así que esto es lo que limita una sesión de larga duración |

Los archivos de sesión se guardan en la base de datos y no en disco, por lo que no necesitan un directorio propio, ni un volumen compartido entre réplicas, ni más copia de seguridad que la de la propia base de datos ([Copia de seguridad y restauración](./backup.md)). Aumentar estos límites aumenta cuánto de la base de datos puede ocupar una ejecución y cuánta memoria consume una sola subida o descarga, porque los bytes se leen enteros.

## Gestión de secretos {#secret-management}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `SECRET_ENCRYPTION_KEY` | — | Clave Fernet con la que se cifran los [secretos](../guides/secrets.md) de tipo `local` antes de almacenarlos |
| `SECRET_KEY_FILE` | `.secret_key` | Ruta del archivo de clave en disco, junto al archivo de la base de datos SQLite. Con `docker compose` es `/var/lib/a2flow/secret-key/.secret_key`, respaldado por el volumen con nombre `secret-key` que comparten el backend y el worker de correo |

La clave de cifrado se resuelve en el primer uso, en este orden:

1. `SECRET_ENCRYPTION_KEY`, que debe ser una clave Fernet válida.
2. El archivo de clave de `SECRET_KEY_FILE`.
3. Si ninguna de las dos existe, se genera una clave, se guarda en ese archivo y se registra un WARNING.

**Haz copia de seguridad de la clave.** Perderla hace indescifrables todos los secretos locales almacenados, y esa misma clave protege la clave de firma de la [CA de aprobaciones](../architecture/approvals.md).

No hay ninguna variable de entorno para HashiCorp Vault: el administrador de un tenant configura el Vault propio de este en [Configuración del tenant](../guides/users-and-groups.md#tenant-vault), y un Superadministrador configura la dirección del Vault global en [Configuración del sistema](../guides/system-settings.md#global-vault), con la [credencial de cada tenant para él](../guides/users-and-groups.md#global-vault-credential) en la página del tenant. La dirección del Vault propio de un tenant pasa por las mismas comprobaciones SSRF que las demás URL que introducen los usuarios, así que debe ser pública. La dirección del Vault global está exenta, ya que solo un Superadministrador puede establecerla y un Vault suele estar en una dirección privada.

## Herramientas MCP y aprobaciones {#mcp-tools-and-approvals}

Cada llamada a una herramienta MCP debe presentar un certificado X.509 de corta duración emitido para la tarea que la realiza, que se concede cuando se concede la [aprobación](../guides/approvals.md#human-approval) de la tarea o cuando empieza una tarea para la que no se pidió aprobación a nadie. La raíz de firma se genera en el primer uso y se almacena cifrada con la misma clave que los secretos locales, así que no hay que configurar nada aquí para que esto funcione.

| Variable | Valor predeterminado | Qué limita |
|---|---|---|
| `MCP_TOOL_CERT_TTL_SECONDS` | `3600` | Tiempo durante el que el certificado de una tarea sigue siendo válido, es decir, el intervalo en el que puede llamar a sus herramientas |
| `MCP_TOOL_CERT_SIGNATURE_WINDOW_SECONDS` | `60` | Tolerancia al desfase de reloj de la firma de prueba de posesión que acompaña a cada llamada a través del proxy |
| `MCP_CA_COMMON_NAME` / `MCP_CA_VALIDITY_DAYS` | `A2Flow MCP Approval CA` / `3650` | Sujeto y vigencia de la raíz generada. Solo se leen cuando se genera la raíz por primera vez; cambiarlos después no afecta a una raíz existente |
| `MCP_REGISTRY_URL` | `https://registry.modelcontextprotocol.io` | URL base del registro en el que busca el cuadro de diálogo [Explorar el registro](../guides/mcp-servers.md#registering-from-the-mcp-registry) |
| `MCP_ELICITATION_TIMEOUT_SECONDS` | `900` | Tiempo que una llamada a herramienta espera a que el iniciador de la ejecución responda a la [confirmación](../guides/workflow-executions.md#mcp-server-confirmations) de un servidor MCP antes de que la pregunta caduque. El iniciador acaba de reanudar la tarea, así que esto solo limita una pregunta abandonada |
| `AGENT_TURN_TIMEOUT_SECONDS` | `3600` | Duración máxima de un turno del agente en una ejecución, esperas incluidas. Mantenlo muy por encima de `MCP_ELICITATION_TIMEOUT_SECONDS`, ya que un turno cuya llamada a herramienta espera a una persona sigue en marcha |

## Proxy MCP {#mcp-sandbox}

Un servidor MCP registrado no es código de A2Flow, así que se ejecuta en [un lugar aparte](../architecture/mcp-gateway-and-proxy.md#the-sandbox) del agente y sus secretos. El despliegue con Docker Compose lo deja todo preparado; un despliegue que monta sus propios contenedores lo configura aquí.

Sin definir, que es lo que ocurre en un arranque local sencillo, el agente accede a los servidores MCP por sí mismo, en su propio proceso. Es práctico para el desarrollo, pero no es lo que quieres en un entorno donde cualquiera puede registrar un servidor.

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `MCP_PROXY_URL` | sin definir | Dónde está el proxy. Al definirla, los servidores MCP salen del proceso del agente |
| `MCP_PROXY_SERVER_NAME` / `MCP_PROXY_PORT` | `mcp-proxy` / `8443` | El nombre con el que se accede al proxy y el puerto en el que escucha. El nombre forma parte de su certificado, así que ambos extremos deben coincidir |
| `MCP_PROXY_TLS_DIR` | un directorio junto a la aplicación | Donde el agente publica lo que el proxy necesita para identificarse. El proxy lee ese mismo directorio, en modo de solo lectura |
| `MCP_BACKEND_TLS_DIR` | un directorio junto a la aplicación | Donde el agente guarda su *propia* clave. A propósito no es el directorio anterior: nada de lo que se ejecute en el proxy debe poder leerla |
| `MCP_TRANSPORT_CERT_VALIDITY_DAYS` | `365` | Vigencia de ese material. Se vuelve a emitir automáticamente cuando quedan menos de 30 días, así que no requiere atención |
| `MCP_SANDBOX_DIR` | sin definir | Donde está el directorio personal de cada tenant para los [inicios de servidor en sandbox](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox): aquí se guardan los paquetes que descargan los servidores de un tenant, un directorio por tenant. Si está definida, cada servidor iniciado localmente se ejecuta en su propio sandbox; el proxy se niega a arrancar sin ella. Queda sin definir en un arranque local sencillo, donde los servidores se inician sin sandbox |

## Correo de notificación {#notification-email}

Son los mismos valores que la interfaz de administración edita en [Configuración del sistema](../guides/system-settings.md), y se pueden definir desde el entorno para que un despliegue incluya su configuración de correo en lugar de dejarla como un paso manual.

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `SMTP_ENABLED` | `false` | Interruptor general de la entrega de correo. Debe ser explícitamente `true`; nunca se deduce de que las demás variables estén definidas |
| `SMTP_HOST` / `SMTP_PORT` | — / `587` | El relé al que se entregan los mensajes. Aquí sirve un simple nombre de host interno: se pasa al cliente SMTP, no se accede a él como URL |
| `SMTP_SECURITY` | `starttls` | `none`, `starttls` o `ssl` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | — | Credenciales de SMTP AUTH. La contraseña solo se almacena cifrada, nunca se registra y ninguna respuesta de la API la devuelve |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | — | Dirección del remitente, obligatoria cuando la entrega está activada, y el nombre para mostrar opcional que la acompaña |

A diferencia de todo lo demás en esta página, estas variables no se leen de nuevo en cada uso: se escriben en el único registro de configuración. Eso les da sus propias reglas:

- **Se vuelven a aplicar en cada arranque**, no solo en el primero, así que rotar la contraseña de un relé es cuestión de redesplegar.
- **Solo se escriben las variables que defines realmente**, así que dejar una sin definir conserva lo que esté almacenado, incluido cualquier ajuste que un administrador haya configurado a mano en la interfaz.
- **Un valor con formato incorrecto se registra como advertencia y se omite por completo.** Un puerto erróneo, una dirección no válida o `SMTP_ENABLED=true` sin host dejan intacta la configuración almacenada; la aplicación arranca igualmente.

Como el indicador de activación es independiente, el host y las credenciales de un relé se pueden preparar en un despliegue y activar la entrega en otro posterior.

## Cola de correo saliente {#outgoing-email-queue}

Estos son los parámetros de la cola que vacía los mensajes hacia el relé; consulta [La cola de entrega](../guides/notifications.md#the-delivery-queue) para ver cómo se comporta. En un despliegue normal no hace falta definir nada de esto.

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `EMAIL_WORKER_IN_PROCESS` | `true` | Si el proceso de la API también ejecuta el worker que vacía la cola, de modo que `uvicorn main:app` por sí solo entrega el correo. Establécelo en false si ejecutas un proceso de worker dedicado; consulta [Disposición de procesos](./deployment.md#process-layout). Dejar ambos activados es seguro, pero inútil: un bloqueo consultivo elige exactamente un remitente en todo el despliegue |
| `EMAIL_SEND_RATE_PER_SECOND` | `5.0` | Mensajes por segundo que se entregan al relé; el worker hace una pausa de `1 / rate` antes de cada envío. Redúcelo para no superar un límite más estricto del relé |
| `EMAIL_QUEUE_BATCH_SIZE` / `EMAIL_QUEUE_POLL_INTERVAL_SECONDS` | `20` / `5.0` | Cuántos mensajes reclama cada pasada y cuánto duerme el worker cuando la cola está vacía. El intervalo de sondeo es el mínimo de la latencia de entrega de una notificación generada mientras el worker duerme |
| `EMAIL_MAX_ATTEMPTS` | `9` | Intentos de entrega antes de que un mensaje pase a ser no entregable (dead letter). La espera entre reintentos es de 15 s, 30 s, 1 min, 2 min y así sucesivamente, con un máximo de una hora, así que el valor predeterminado aguanta aproximadamente una hora de caída del relé. Un fallo que el relé comunica como permanente se da por perdido en el primer intento en cualquier caso |
| `EMAIL_SENT_RETENTION_DAYS` | `30` | Tiempo que se conservan los mensajes entregados antes de que el worker los purgue. Son un registro de lo que se envió, no estado de la cola. Los mensajes no entregables no se purgan nunca |

## Agente {#agent}

| Variable | Valor predeterminado | Qué hace |
|---|---|---|
| `EXECUTION_MAX_PARALLEL_SESSIONS` | `4` | Número máximo de sesiones en las que una ejecución trabaja a la vez: su sesión principal más las sesiones de rama que se bifurcan cuando su grafo de tareas se ramifica. Al llegar al límite, una tarea lista espera a su sesión en lugar de bifurcar otra. `1` desactiva la bifurcación. Como mínimo `1` |
| `ROLE_DESCRIPTION` | Una descripción genérica de asistente | Texto de rol en torno al cual se construye el prompt de sistema del agente, junto con las reglas del flujo de trabajo y el esquema de la interfaz |
| `SESSION_RUNNER_CONCURRENCY` | `4` | Cuántos turnos ejecuta a la vez una réplica en nombre de la propia ejecución: inicios y reanudaciones tras decidirse una aprobación. Cada uno es una conversación en vivo con el modelo, así que esto limita las llamadas al modelo de una réplica para ejecuciones que nadie está mirando. Como mínimo `1` |
