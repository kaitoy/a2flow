---
title: Tenants
sidebar_position: 2
---

# Tenants

Un **tenant** es el límite organizativo de nivel superior de A2Flow. Casi todos los registros pertenecen exactamente a uno, un pequeño conjunto de elementos se sitúa deliberadamente por encima de todos ellos y ninguna solicitud pasa jamás de un tenant a otro. Crear y editar los propios registros de tenant es una tarea de administración, explicada en [Tenants](../guides/users-and-groups.md#tenants); esta página trata de lo que ese límite significa para todo lo demás.

## Qué abarca un tenant {#what-a-tenant-scopes}

| Ámbito | Qué hay en él |
|---|---|
| **Ámbito de tenant** | Skills de agente, flujos de trabajo y sus sesiones de diseño, plantillas de tareas, ejecuciones y sus sesiones del flujo de trabajo, aprobaciones, secretos, servidores MCP, mocks de herramientas, etiquetas, grupos de usuarios y la mayoría de los usuarios |
| **Ámbito de plataforma** | Los propios registros de tenant, la [Configuración del sistema](../guides/system-settings.md), las cuentas de Superadministrador y el usuario del sistema precargado |

Un [usuario](../guides/users-and-groups.md#users) pertenece **como máximo a un** tenant. Un [grupo de usuarios](../guides/users-and-groups.md#user-groups) pertenece **exactamente a uno**, y por eso un grupo nunca puede conceder `super_admin`, un rol que por definición tiene ámbito de plataforma (consulta [Roles efectivos](./authorization.md#effective-roles)). En el primer arranque se precarga un tenant **Default**, que contiene el usuario `admin` inicial precargado; el usuario `root` precargado tiene ámbito de plataforma y no pertenece a ningún tenant.

## El límite del tenant {#the-tenant-boundary}

Toda lectura y escritura con ámbito de tenant se resuelve dentro del tenant de quien la hace, y un registro que solo existe en otro tenant se notifica como **HTTP 404, no 403**: el límite oculta la existencia del registro en lugar de anunciarla. Esto vale tanto para un ID de flujo de trabajo escrito en una URL como para un ID pasado a una API, y es la razón por la que una referencia entre tenants nunca confirma que el registro sea real.

La única lectura que ni devuelve un registro ni finge que no existe es la resolución masiva de nombres: `POST /api/v1/users/resolve-names` elimina de su respuesta a los usuarios ajenos al tenant de quien llama, de modo que la interfaz recurre al ID sin más, pero etiqueta los dos tipos de cuenta que legítimamente poseen registros dentro de todos los tenants; consulta [Resolver nombres de forma masiva](../guides/users-and-groups.md#users).

## Actuar en nombre de un tenant {#acting-as-a-tenant}

Un Superadministrador, con ámbito de plataforma, no tiene tenant propio, y sin embargo casi todo lo que merece la pena consultar pertenece a uno. El **selector de tenants** del encabezado de la aplicación, visible solo para Superadministradores, es la forma de elegir en nombre de qué tenant se actúa. La elección se recuerda entre recargas y se aplica en todas partes, incluidos la sección de administración y el chat. Si no hay ningún tenant seleccionado, las solicitudes con ámbito de tenant se rechazan con HTTP 403.

Cambiar de tenant no cambia los *roles*: un Superadministrador sigue omitiendo todos los controles por rol, sea cual sea el tenant seleccionado.

El selector solo aparece para quien no tiene tenant propio. Un **usuario con ámbito de tenant siempre queda limitado a su propio tenant**, y el encabezado `X-Tenant-Id` que establece el selector se ignora por completo en su caso: enviarlo a mano no concede nada, así que no es posible escapar del límite desde el cliente.

### Todos los tenants {#all-tenants}

El selector también ofrece la opción **Todos los tenants**, que permite explorar a la vez los datos de todos los tenants en las páginas de lista y de detalle de administración, que quedan en solo lectura. Con esta opción activa, esas páginas añaden la columna **Tenant** como primera columna por la izquierda (y un campo equivalente) para distinguir las filas de los distintos tenants.

Mientras suplantas a otro usuario, la selección Todos los tenants queda en suspenso: las páginas se comportan como si estuviera seleccionado el tenant de ese usuario y la columna Tenant no se muestra. Vuelve a aplicarse cuando dejas de suplantar.

| Selección | Lecturas | Escrituras | Historial de chat | Endpoints del agente |
|---|---|---|---|---|
| Tenant propio (implícito, todo usuario con ámbito de tenant) | Tenant propio | Tenant propio | Tenant propio | ✅ |
| Un tenant (Superadministrador) | Ese tenant | Ese tenant | Ese tenant | ✅ |
| **Todos los tenants** (Superadministrador) | Todos los tenants | ❌ 403 | Todos los tenants | ❌ 403 |
| Sin selección (Superadministrador) | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 |

«Historial de chat» se refiere a `GET /workflows/{id}/messages` y `GET /workflow-executions/{id}/messages`, de modo que un Superadministrador que revise el flujo de trabajo o la ejecución de otro tenant también puede leer su conversación. Los endpoints del agente que *dirigen* esos chats (`POST .../agent`) son escrituras y siempre requieren tener seleccionado un tenant concreto. Con la selección Todos los tenants, el ID de un flujo de trabajo se resuelve sea cual sea el tenant, así que ahí la propia comprobación de roles de la sesión de diseño hace las veces de límite del tenant; consulta [Sesión de diseño](./authorization.md#design-session-access).
