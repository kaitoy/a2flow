---
title: Ejecutar con Docker Compose
sidebar_position: 2
---

# Ejecutar con Docker Compose

Como alternativa, puedes compilar e iniciar toda la pila con Docker Compose ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)):

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

Abre [http://localhost:3000](http://localhost:3000). Los datos de la base de datos se conservan entre reinicios en el volumen `pgdata`.

Define `APP_PORT` en `.env` para publicar la aplicación en otro puerto del host; la URL base de la aplicación lo sigue automáticamente. Para que la aplicación se abra con otra dirección —un nombre de host, por ejemplo—, define en su lugar `APP_BASE_URL` en `.env` con esa dirección, como `http://a2flow.internal:3000`. La aplicación se sigue publicando en `APP_PORT`, así que, si esa dirección lleva puerto, ajusta `APP_PORT` para que coincida.

## Qué se inicia {#what-comes-up}

| Contenedor | Qué hace |
|---|---|
| **db** | PostgreSQL 17. Aquí se guarda todo lo que registra A2Flow |
| **backend** | El agente y la API |
| **worker** | Envía los [correos de notificación](../guides/notifications.md#the-delivery-queue) que el backend pone en cola |
| **mcp-proxy** | Ejecuta los [servidores MCP](../guides/mcp-servers.md) que registras; consulta [por qué está separado](../architecture/mcp-gateway-and-proxy.md#the-sandbox) |
| **ingress** | El punto de entrada con el que se comunica tu navegador. Envía las solicitudes de las pantallas al frontend y las solicitudes de la API directamente al backend |
| **frontend** | Las pantallas que utilizas |
| **caddy** | Solo con `compose.https.yml`; consulta [Servir por HTTPS](#https) |
| **openbao** | Solo con `--profile openbao`; consulta [Probar secretos de Vault con OpenBao](#openbao) |
| **keycloak** | Solo con `--profile keycloak`; consulta [Probar el inicio de sesión único con Keycloak](#keycloak) |

Solo se puede acceder desde fuera al ingress —o a Caddy en su lugar, con `compose.https.yml`— (y, con sus perfiles, a la interfaz de OpenBao y a Keycloak); el resto se comunica por la red interna de Docker.

El primer inicio tarda más que los siguientes: se compilan las imágenes, se crea el esquema de la base de datos y el proxy MCP espera a que el backend le entregue el certificado que necesita antes de aceptar nada.

## Servir por HTTPS {#https}

Al añadir `compose.https.yml`, [Caddy](https://caddyserver.com/) se coloca delante del ingress. Pasa a ser el único punto de entrada, en los puertos 80 y 443, obtiene un certificado para la dirección de `APP_BASE_URL` y redirige el HTTP sin cifrar a HTTPS. Una dirección `https://` también hace seguras las cookies de inicio de sesión, y el [inicio de sesión único](../guides/single-sign-on.md) construye a partir de ella su **URI de redirección**.

```bash
echo APP_BASE_URL=https://a2flow.example.com >> .env
docker compose -f compose.yml -f compose.https.yml up --build
```

Abre la dirección que definiste. No puede llevar puerto: solo se publican el 80 y el 443, y Caddy no arranca con una dirección que lo lleve. Lo que ocurre después depende del nombre de host:

| `APP_BASE_URL` | Certificado | Antes de empezar |
|---|---|---|
| Un nombre de host público, como `https://a2flow.example.com` | Se obtiene de Let's Encrypt y se renueva automáticamente | Haz que el DNS del nombre apunte a este host y que los puertos 80 y 443 sean accesibles desde internet |
| Sin definir (`https://localhost`) | Lo emite una autoridad de certificación que Caddy crea para sí mismo | Nada, aunque el navegador avisa del certificado hasta que confíes en esa autoridad (ver abajo) |

Para que el navegador confíe en `https://localhost`, copia el certificado raíz de la autoridad y añádelo a los certificados raíz de confianza de tu sistema operativo o navegador:

```bash
docker compose -f compose.yml -f compose.https.yml cp caddy:/data/caddy/pki/authorities/local/root.crt .
```

Los certificados y la autoridad local se guardan en el volumen `caddy-data`. Consérvalo: si lo eliminas, se emiten certificados nuevos y el certificado raíz en el que ya confiabas deja de coincidir.

## Probar secretos de Vault con OpenBao {#openbao}

[OpenBao](https://openbao.org/) es una bifurcación de código abierto de Vault a la que A2Flow se conecta exactamente igual que a HashiCorp Vault. La pila puede iniciar una instancia junto a A2Flow, de modo que puedes probar los [secretos de tipo Vault](../guides/secrets.md) sin tener un Vault propio.

```bash
docker compose --profile openbao up --build
```

OpenBao guarda sus datos en el mismo PostgreSQL que A2Flow, por lo que sobreviven a los reinicios, y se desella solo en cada inicio. La clave con la que se desella está en el volumen `openbao-unseal`: haz una copia de seguridad de ella junto con `pgdata`, ya que sin ella no se pueden leer los datos. Esta configuración sirve para probar la integración, no para producción.

### 1. Inicializar OpenBao (solo en el primer inicio) {#1-initialize-openbao-first-start-only}

```bash
docker compose exec openbao bao operator init -recovery-shares=1 -recovery-threshold=1
```

Anota el **Initial Root Token** que aparece: solo se muestra una vez.

### 2. Crear un AppRole para A2Flow {#2-create-an-approle-for-a2flow}

La interfaz no permite crear un rol de AppRole, así que este paso se hace por línea de comandos. Sustituye `<root-token>` por el token del paso 1:

```bash
docker compose exec -e BAO_TOKEN=<root-token> openbao sh -c '
  bao secrets enable -path=secret kv-v2
  bao auth enable approle
  printf "path \"secret/data/a2flow/*\" { capabilities = [\"read\"] }" | bao policy write a2flow -
  bao write auth/approle/role/a2flow token_policies=a2flow token_ttl=1h
  bao read -field=role_id auth/approle/role/a2flow/role-id; echo
  bao write -f -field=secret_id auth/approle/role/a2flow/secret-id; echo'
```

Las dos últimas líneas muestran el **role id** y el **secret id**. La política permite a A2Flow leer únicamente las rutas bajo `a2flow/`.

### 3. Crear un secreto en la interfaz de OpenBao {#3-create-a-secret-in-the-openbao-ui}

1. Abre [http://localhost:8200/ui](http://localhost:8200/ui) e inicia sesión con el método **Token** y el token raíz. OpenBao no conserva la sesión iniciada con el token raíz al recargar la página, así que muévete haciendo clic en lugar de escribir URL.
2. Abre el motor **secret/** y elige **Create secret**.
3. Introduce `a2flow/demo` como ruta, añade las entradas `username` y `password`, y guarda.

### 4. Conectar A2Flow {#4-connect-a2flow}

1. Inicia sesión en A2Flow como `root`. En **Configuración del sistema**, establece **Dirección de Vault global** en `http://openbao:8200` y guarda.
2. Abre **Tenants** y, después, **Default**. Marca **Iniciar sesión en el Vault global**, elige **AppRole** como **Método de autenticación de Vault**, introduce el role id y el secret id del paso 2, y guarda.
3. Inicia sesión como `admin`. En **Secretos**, crea un secreto de tipo **HashiCorp Vault** con `secret` como **Montaje de Vault** y `a2flow/demo` como **Ruta de Vault**.

Haz referencia a él como a cualquier otro secreto, por ejemplo como `${secret:<nombre>/password}` en una variable de entorno de un [servidor MCP](../guides/mcp-servers.md). Allí donde elijas el secreto se muestran sus claves `username` y `password`, leídas de OpenBao en ese momento, lo que demuestra que la conexión funciona.

Define `OPENBAO_PORT` en `.env` para publicar la interfaz de OpenBao en un puerto del host distinto de 8200. El propio A2Flow siempre accede a ella como `http://openbao:8200` en la red interna.

## Probar el inicio de sesión único con Keycloak {#keycloak}

[Keycloak](https://www.keycloak.org/) es un proveedor de identidad de código abierto. La pila puede iniciar uno junto a A2Flow, ya configurado para él, de modo que puedes probar el [inicio de sesión único](../guides/single-sign-on.md) sin un IdP propio.

```bash
docker compose --profile keycloak up --build
```

Keycloak se publica en [http://keycloak.localhost:8180](http://keycloak.localhost:8180), y en su consola de administración se inicia sesión como `admin` / `admin` (define `KEYCLOAK_ADMIN_PASSWORD` en `.env` para cambiar la contraseña). Chrome, Edge y Firefox encuentran `keycloak.localhost` por sí solos; en otro navegador, añade primero la línea `127.0.0.1 keycloak.localhost` a tu archivo hosts. Keycloak no conserva nada al recrear el contenedor: vuelve a empezar desde la configuración siguiente, así que se pierden los cambios hechos en su consola.

Arranca con esto ya preparado:

| Qué | Valor |
|---|---|
| Realm | `a2flow` |
| URL del emisor | `http://keycloak.localhost:8180/realms/a2flow` |
| ID de cliente | `a2flow` |
| Secreto de cliente | `a2flow-dev-secret` |
| URI de redirección | `http://localhost:3000` (o tu `APP_BASE_URL`) y `https://localhost`, cada una seguida de la ruta de retorno de A2Flow |
| Claim de grupos | `groups` |
| Usuarios | `alice` en el grupo `a2flow-admins`, `bob` en el grupo `a2flow-users`. Ambos tienen la contraseña `password` |

### 1. Conectar A2Flow {#1-connect-a2flow}

1. Inicia sesión en A2Flow como `admin` y abre **Configuración del tenant** en la barra lateral de administración.
2. En la sección **Inicio de sesión único**, rellena **URL del emisor**, **ID de cliente** y **Secreto de cliente** con los valores de la tabla anterior, marca **Habilitar el inicio de sesión único** y guarda.
3. Abre **Grupos de usuarios**, abre un grupo —o crea uno— que tenga los roles que quieras, escribe `a2flow-admins` en **Grupo del IdP** y guarda.

### 2. Iniciar sesión {#2-sign-in}

1. Cierra la sesión. En la pantalla de inicio de sesión, escribe `default` en **Tenant** y pulsa **Iniciar sesión con SSO**.
2. En la página de inicio de sesión de Keycloak, inicia sesión como `alice` / `password`. Vuelves a A2Flow con la sesión iniciada como Alice, miembro del grupo del paso 1.
3. Prueba también con `bob`: su único grupo, `a2flow-users`, no está asignado a ningún grupo de usuarios, así que el inicio de sesión se rechaza, hasta que lo asignes a uno.

Keycloak también habla SAML, pero A2Flow inicia sesión solo mediante OpenID Connect.
