---
title: Despliegue
sidebar_position: 1
---

# Despliegue

Un despliegue consta del frontend, el backend y una base de datos relacional; [Ejecutar con Docker Compose](../getting-started/docker-compose.md) es el camino más corto hacia los tres. Lo que sigue es lo que cambia cuando la pila se coloca detrás de un proxy y contiene datos que merece la pena conservar.

![Diagrama de arquitectura que muestra el navegador llegando a un proxy inverso que dirige las solicitudes de API (/api/*) directamente a la API del backend y las solicitudes de páginas al frontend, y a la API del backend, que también ejecuta el worker de correo, accediendo al estado duradero (base de datos, almacén de skills, clave secreta), a los servicios externos (proveedor de LLM, servidores MCP) y a un relé SMTP.](./img/deployment-topology.svg#gh-light-mode-only)
![Diagrama de arquitectura que muestra el navegador llegando a un proxy inverso que dirige las solicitudes de API (/api/*) directamente a la API del backend y las solicitudes de páginas al frontend, y a la API del backend, que también ejecuta el worker de correo, accediendo al estado duradero (base de datos, almacén de skills, clave secreta), a los servicios externos (proveedor de LLM, servidores MCP) y a un relé SMTP.](./img/deployment-topology-dark.svg#gh-dark-mode-only)

El navegador se comunica con un único origen, y el proxy inverso lo dirige por ruta: `/api/*` y `/openapi.json` al backend, todo lo demás al frontend. Ambos están en el mismo dominio, así que las cookies de autenticación siguen siendo de origen propio, y los streams de larga duración de cada chat abierto van directamente al backend en lugar de pasar por el frontend. El servicio `ingress` de `compose.yml` (Envoy) es un ejemplo funcional de este enrutamiento.

Sin esa ruta, el frontend reenvía `/api/*` al backend por sí mismo, que es como funciona un arranque sin contenedores. El comportamiento es el mismo, pero cada chat abierto mantiene además una conexión en el frontend, así que también hay que escalar el frontend según el número de chats simultáneos. Todas las variables que se mencionan aquí se describen en [Referencia de configuración](./configuration.md).

## Proxy inverso y balanceador de carga {#reverse-proxy-and-load-balancer}

**No se necesitan sesiones persistentes (sticky sessions) ni afinidad de sesión.** Consulta [Escalado horizontal](./scaling.md): lo que mantiene una conversación asignada a un solo conductor a la vez es un bloqueo consultivo de PostgreSQL, no la afinidad de enrutamiento, y solo durante un único stream SSE.

Las rutas SSE del agente (`POST /api/v1/workflow-executions/{id}/agent` y `POST /api/v1/workflows/{id}/agent`) necesitan lo siguiente en el proxy inverso que las dirige al backend:

| Ajuste | Valor necesario | Motivo |
|---|---|---|
| Almacenamiento en búfer de la respuesta | Desactivado en esas dos rutas | La aplicación envía `X-Accel-Buffering: no`, que nginx respeta por respuesta aunque el búfer esté activado globalmente. Cualquier otro proxy necesita desactivarlo en su propia configuración |
| Compresión | Nunca aplicada a `text/event-stream` | La aplicación nunca comprime una respuesta, así que cualquier compresión que vea el cliente procede de esta capa |
| Tiempo de espera de lectura / inactividad | Muy superior a la ejecución de agente más larga que esperes | Una ejecución de agente no tiene límite de tiempo en el servidor, así que un tiempo de espera de lectura del proxy es lo único que puede terminar un stream, y uno bajo trunca sin avisar una respuesta larga legítima. Dimensiónalo según tu ejecución más larga, no según una solicitud típica |

Un despliegue gradual termina a la fuerza cualquier stream SSE que siga abierto 30 segundos después de que el contenedor reciba SIGTERM (`--timeout-graceful-shutdown 30`, definido en el `CMD` del `Dockerfile` del backend). Es seguro: el bloqueo consultivo se libera con la conexión y el cliente reanuda con una solicitud nueva, igual que ya ocurre con un stream abandonado.

## Detrás de HTTPS {#behind-https}

Hay tres ajustes cuyos valores predeterminados solo sirven para el desarrollo local con HTTP. Cámbialos los tres antes de que un despliegue atienda a usuarios reales:

| Variable | Establécela en | Si se deja el valor predeterminado |
|---|---|---|
| `SESSION_COOKIE_SECURE` | `true` | Las cookies de sesión y CSRF se envían sin `Secure`, de modo que el navegador también las manda por HTTP sin cifrar |
| `CORS_ORIGINS` | El origen de cara al navegador, p. ej. `https://a2flow.example.com` | Solo `http://localhost:3000` puede llamar a la API |
| `APP_BASE_URL` | El mismo origen | Los correos de notificación se envían sin los enlaces directos a la aplicación; consulta [Correo de notificación](./configuration.md#notification-email) |

## Disposición de procesos {#process-layout}

Junto a la API, un despliegue ejecuta el [proxy MCP](../architecture/mcp-gateway-and-proxy.md#the-sandbox): el proceso que realmente inicia los servidores MCP que un tenant ha registrado o se conecta a ellos. Mantenerlo separado es precisamente el objetivo: es donde se ejecuta código de terceros, así que no tiene acceso a la base de datos, ni clave de cifrado de secretos, ni clave de API del LLM. `compose.yml` lo ejecuta como el contenedor `mcp-proxy`, en una red que solo comparte con la API, por lo que no puede llegar a la base de datos en absoluto; un despliegue que monte sus propios contenedores debería mantener el proxy fuera de la red de la base de datos de la misma forma, y configurarlo en [Proxy MCP](./configuration.md#mcp-sandbox).

Dos cosas que hay que hacer bien:

- **La API tiene que arrancar primero.** Emite el material con el que ambos extremos se identifican mutuamente, así que el proxy no aceptará nada hasta que se haya escrito. Condiciona el arranque del proxy a la comprobación de estado de la API, como hace `compose.yml`.
- **Necesitan un directorio compartido.** `MCP_PROXY_TLS_DIR` tiene que ser el mismo almacenamiento en ambos lados: con escritura para la API y de solo lectura para el proxy. Allí no se guarda nada duradero: se reescribe siempre que falta o está a punto de caducar.
- **El proxy tiene que poder crear sandboxes.** Inicia cada servidor en un [sandbox propio](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox) y comprueba al arrancar que puede hacerlo; si no puede, se detiene con un error en lugar de ejecutar servidores sin sandbox. Dentro de un contenedor, esto requiere tres opciones de seguridad, que `compose.yml` concede al servicio `mcp-proxy` y solo a él: `seccomp=unconfined`, `apparmor=unconfined` y `systempaths=unconfined`. En un host con Ubuntu 24.04 o posterior, también hay que permitir los espacios de nombres de usuario sin privilegios: `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`.

Se puede prescindir del proxy: deja `MCP_PROXY_URL` sin definir y la API accederá a los servidores MCP por sí misma, que es lo que hace un arranque de desarrollo local. Eso significa que un servidor registrado se ejecuta junto a las credenciales del despliegue, así que no es una opción para un entorno donde cualquiera puede registrar uno.

El backend también se distribuye con dos puntos de entrada contra la misma base de datos. El que ejecutes determina desde dónde se entrega el correo de notificación:

| Disposición | Cómo | Cuándo usarla |
|---|---|---|
| Solo API | El valor predeterminado: `EMAIL_WORKER_IN_PROCESS` es `true`, así que `uvicorn main:app` también vacía la cola de correo | Un despliegue de un solo proceso, o uno lo bastante pequeño como para que un relé atascado en la ruta de las solicitudes sea aceptable |
| API + worker | Ejecuta `python -m worker` junto a la API y establece `EMAIL_WORKER_IN_PROCESS=false` en ella | Cualquier caso en el que un relé colgado no deba afectar a nada que atienda solicitudes. Es lo que hace `compose.yml` |

Dos cosas sobre el proceso del worker:

- **No migra ni carga datos iniciales.** Ambas cosas corresponden al arranque de la API, así que el worker tiene que iniciarse después de que la API esté en marcha; `compose.yml` lo condiciona a la comprobación de estado de la API.
- **Más de una réplica aporta conmutación por error, no rendimiento.** Compiten por el bloqueo consultivo `email-queue` y todas menos una permanecen inactivas por diseño, que es lo que mantiene exacta la velocidad de envío.

## Comprobaciones de estado {#health-checks}

Apunta tu orquestador o balanceador de carga a `GET /api/v1/health`. Consulta [Comprobaciones de estado](./health.md).

## Estado que debe persistir {#state-that-has-to-persist}

Tres cosas sobreviven a un contenedor y deben estar en almacenamiento duradero para que un despliegue vuelva a funcionar intacto:

| Qué | Dónde está | Si se pierde |
|---|---|---|
| **La base de datos** | La base de datos indicada en `DB_URL` | Todo: ahí está cada registro. Consulta [Base de datos](../architecture/database.md) |
| **El almacén de skills de agente** | `SKILLS_DIR` | Las ejecuciones no pueden cargar la revisión de la skill a la que están fijadas (HTTP 409 `SKILL_NOT_READY`). Es estado duradero, no una caché; consulta [Almacén de skills de agente](./configuration.md#agent-skill-store) |
| **La clave de cifrado de secretos** | `SECRET_ENCRYPTION_KEY`, o el archivo de `SECRET_KEY_FILE` | Todos los secretos locales almacenados se vuelven indescifrables, y la autoridad de certificación ya no puede emitir ni verificar los certificados que necesita cada llamada a una herramienta MCP. Consulta [Gestión de secretos](./configuration.md#secret-management) |

Cómo copiar y restaurar cada una de ellas se explica en [Copia de seguridad y restauración](./backup.md).
