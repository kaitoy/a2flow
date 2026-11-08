---
title: Roles y autorización
sidebar_position: 3
---

# Roles y autorización

Cada usuario tiene un conjunto de **roles** que le conceden las operaciones que puede realizar. Los roles son **independientes** (no hay jerarquía), con una excepción: **el Superadministrador omite todas las comprobaciones basadas en roles** y, por eso, es **mutuamente excluyente** con cualquier otro rol: un usuario es Superadministrador o tiene alguna combinación de los otros cinco roles, nunca ambas cosas. Dos comprobaciones de la capa de propiedad son una excepción deliberada a esa omisión, y ambas se ven en la [matriz de acceso a sesiones](./authorization.md#workflow-execution-access) de más abajo. Un usuario **sin ningún rol** es válido: aún puede gestionar su propia [cuenta](../guides/users-and-groups.md#users) (avatar e idioma), pero nada más.

## Roles efectivos {#effective-roles}

Un rol llega a un usuario de una de dos formas, y toda comprobación de autorización usa la **unión** de ambas, es decir, los **roles efectivos** del usuario:

- **Directamente**, concedido en el registro del usuario desde la página [Usuarios](../guides/users-and-groups.md#users).
- **Heredado** de un [grupo de usuarios](../guides/users-and-groups.md#user-groups) al que pertenece: asignar un rol a un grupo se lo concede a todos sus miembros.

![Diagrama de flujo que muestra cómo los roles concedidos directamente en el registro del usuario y los heredados de grupos de usuarios alimentan los roles efectivos del usuario, la unión que usa toda comprobación de autorización.](./img/authorization-effective-roles.svg#gh-light-mode-only)
![Diagrama de flujo que muestra cómo los roles concedidos directamente en el registro del usuario y los heredados de grupos de usuarios alimentan los roles efectivos del usuario, la unión que usa toda comprobación de autorización.](./img/authorization-effective-roles-dark.svg#gh-dark-mode-only)

Un rol que se tiene solo a través de un grupo vale exactamente lo mismo que uno concedido directamente: supera los mismos controles, hace al usuario apto como aprobador y lo protege de la [suplantación](./impersonation.md) de la misma manera. Nada se almacena en caché (la unión se resuelve en cada solicitud), así que añadir a alguien a un grupo o quitarlo surte efecto de inmediato, sin ningún paso de resincronización.

Un grupo también puede ser destinatario por derecho propio: una [aprobación](../guides/approvals.md#human-approval) puede enviarse a un grupo en lugar de a una persona, y cualquier miembro que tenga `approver` puede resolverla.

**Un grupo nunca puede conceder `super_admin`**: la opción no se ofrece en la interfaz, la API la rechaza (HTTP 422) y una restricción de comprobación de la base de datos respalda ambas cosas. Como un Superadministrador tiene ámbito de plataforma y un grupo pertenece exactamente a un [tenant](./tenants.md), un Superadministrador tampoco puede ser miembro de un grupo.

## Los roles {#the-roles}

| Rol | Concede |
|---|---|
| `super_admin` | Todo (omite todos los controles por rol; **no** omite las dos comprobaciones de aprobador designado de la [matriz de abajo](./authorization.md#workflow-execution-access)) |
| `admin` | CRUD de usuarios, CRUD de secretos, eliminación de ejecuciones y visibilidad de solo lectura de todas las ejecuciones, sus tareas y su historial de chat, y de todas las aprobaciones de su tenant (consulta [La ejecución del flujo de trabajo y su sesión](./authorization.md#workflow-execution-access); salvo para eliminarla, un Administrador no puede dirigir el agente de una ejecución, cambiar el estado de una de sus tareas ni resolver una aprobación) |
| `developer` | CRUD de secretos, CRUD de servidores MCP, CRUD de [mocks de herramientas](../guides/tool-mocks.md), CRUD de skills de agente, generación y edición de flujos de trabajo (incluida la regeneración del **Prompt generado** por IA de un flujo de trabajo, aunque solo un Superadministrador puede editar ese campo directamente), CRUD de plantillas de tareas, dirección del chat de la sesión de diseño y ejecución de flujos de trabajo (`POST /workflows/{id}/execute`), incluidos los flujos de trabajo en `borrador` y las ediciones sin publicar de uno `modificado`, para hacer pruebas antes de publicar. Publicar y desactivar **no** están incluidos: eso le corresponde a `reviewer` |
| `reviewer` | Publicar y desactivar un flujo de trabajo, las dos operaciones que `developer` ya no realiza. Comparte toda la visibilidad de lectura de `developer` sobre un flujo de trabajo: un flujo de trabajo en `borrador`, las ediciones sin publicar de uno `modificado` y el historial de chat de la sesión de diseño se leen igual para un Revisor que para un Desarrollador. No puede editar un flujo de trabajo ni sus plantillas de tareas, ni dirigir su sesión de diseño |
| `requester` | Ejecutar flujos de trabajo **publicados** (y en estado `modificado`) (`POST /workflows/{id}/execute`), siempre con el último diseño publicado |
| `approver` | Poder ser el aprobador designado de una aprobación de flujo de trabajo, ya sea individualmente o como miembro de un grupo al que se dirige una aprobación, y resolver sus propias aprobaciones |

El usuario **`root`** inicial precargado tiene `super_admin` y ámbito de plataforma (sin tenant). El usuario **`admin`** precargado dentro del tenant **Default** tiene `admin`, limitado a ese tenant; todos los demás usuarios empiezan sin roles.

## Qué controlan los roles {#what-roles-gate}

**Las lecturas siguen abiertas.** Los roles solo controlan las escrituras, la ejecución de flujos de trabajo y las aprobaciones; cualquier usuario autenticado puede hacer `GET` de las colecciones (la interfaz las necesita para resolver nombres, elegir aprobadores y listar flujos de trabajo). La API nunca devuelve los *valores* de los secretos, sea cual sea el rol.

El **Prompt** y el **Prompt generado** de un flujo de trabajo, el texto que se le indica a una ejecución, solo se muestran a un Administrador, Desarrollador, Revisor o Superadministrador. Todos los demás leen el flujo de trabajo y sus ejecuciones con esos campos vacíos. El [historial de versiones](../guides/workflows.md#version-history) del flujo de trabajo se limita a los mismos roles; un Solicitante o un Aprobador no puede abrirlo. La **Descripción** del flujo de trabajo sigue visible para todos los que pueden abrirlo.

La única excepción no es un rol: un registro con una [etiqueta de control de acceso](../guides/tags.md#access-control-tags) solo es visible para los usuarios cuyos grupos, entre todos, tengan todas esas etiquetas del registro, y para un Administrador o un Superadministrador, que la omiten. Los demás no ven ni el registro ni ningún indicio de que exista.

Los roles se asignan desde la página de administración [Usuarios](../guides/users-and-groups.md#users) o, de forma masiva, desde la página [Grupos de usuarios](../guides/users-and-groups.md#user-groups); solo un Superadministrador puede conceder o revocar `super_admin`. Una solicitud rechazada devuelve HTTP 403 (`FORBIDDEN`).

### Qué oculta la interfaz {#what-the-ui-hides}

La interfaz de administración oculta las acciones y las entradas de navegación que los roles de un usuario no permiten, de modo que normalmente una solicitud rechazada es inalcanzable, no solo denegada:

| Pantalla | Sin el rol |
|---|---|
| **Página de lista** | Se ocultan el botón Añadir y la columna Acciones de cada fila: Eliminar y, en Servidores MCP, «Explorar el registro», que solo lleva al formulario de creación |
| **Página de detalle** | Se muestra en **solo lectura**: cada campo aparece como un valor atenuado en lugar de un control de entrada, Guardar y Eliminar desaparecen y Cancelar pasa a ser Volver |
| **Formulario de creación** (`/<section>/new`) | Una pantalla de «Acceso denegado»: llegar a ella implica un enlace directo, ya que el botón Añadir que lleva ahí ya está oculto |

Como las lecturas siguen abiertas, una página de detalle puede abrirla alguien que no puede escribir en ella: las skills de agente, los servidores MCP, los mocks de herramientas, los secretos, los tenants, los usuarios, los flujos de trabajo y las plantillas de tareas adoptan todos la vista de solo lectura anterior. Las entradas de un secreto muestran entonces solo sus claves (de todos modos, los valores nunca se devuelven), y el campo de contraseña de un usuario se omite por completo. Los campos que son inmutables para *todos* (el `name` de un tenant, el `username` de un usuario) se muestran igual sea cual sea el rol. Los formularios de creación no tienen una vista de solo lectura, y por eso responden con una pantalla en lugar de un formulario.

## Acceso a las sesiones {#session-access}

A2Flow tiene dos tipos de chat, y se controlan de dos formas distintas:

- Una **sesión de diseño** es el chat en el que se diseña un flujo de trabajo. El acceso lo decide el **rol**: diseñar es trabajo de desarrollo, así que los Desarrolladores del tenant la comparten y pueden dirigirla; los Revisores también pueden leerla, para revisar el diseño antes de publicarlo, pero no dirigirla.
- Una **sesión del flujo de trabajo** es el chat en el que transcurre una ejecución. El acceso lo decide la **participación**: la comparten quien inició la ejecución y las personas a las que se pide aprobar algo en ella, sean cuales sean sus roles.

![Matriz de acceso que muestra que los Desarrolladores, el creador del flujo de trabajo y el Superadministrador acceden a una sesión de diseño, con acceso de solo lectura para los Revisores, mientras que el iniciador de la ejecución, sus aprobadores designados y el Superadministrador acceden a una sesión del flujo de trabajo, con acceso de solo lectura para el Administrador.](./img/authorization-session-matrix.svg#gh-light-mode-only)
![Matriz de acceso que muestra que los Desarrolladores, el creador del flujo de trabajo y el Superadministrador acceden a una sesión de diseño, con acceso de solo lectura para los Revisores, mientras que el iniciador de la ejecución, sus aprobadores designados y el Superadministrador acceden a una sesión del flujo de trabajo, con acceso de solo lectura para el Administrador.](./img/authorization-session-matrix-dark.svg#gh-dark-mode-only)

### Sesión de diseño {#design-session-access}

El chat de diseño de un flujo de trabajo (`GET /workflows/{id}/messages`, `POST /workflows/{id}/agent`) se comparte por roles, no por participación en cada registro, para que un equipo pueda refinar un diseño en común.

| Quién | Leer el historial | Dirigir el agente |
|---|---|---|
| Cualquier **Desarrollador** del tenant | ✅ | ✅ |
| Cualquier **Revisor** del tenant | ✅ | ❌ 403 |
| El **creador** del flujo de trabajo (`createdBy`), incluso después de perder `developer` | ✅ | ✅ |
| **Superadministrador** | ✅ | ✅ |
| Todos los demás | ❌ 403 | ❌ 403 |

Admitir expresamente al creador significa que nadie se queda fuera de un chat que inició. El ID de un flujo de trabajo de otro tenant es un **404**, nunca un 403, salvo con `GET .../messages` cuando un Superadministrador tiene seleccionado [Todos los tenants](./tenants.md#all-tenants): el flujo de trabajo se resuelve sea cual sea el tenant, y esta misma comprobación de rol, creador o Superadministrador es lo que hace las veces de límite del tenant.

### La ejecución del flujo de trabajo y su sesión {#workflow-execution-access}

Además de los roles, cada operación sobre una ejecución requiere que quien llama sea el **iniciador** de la ejecución (el usuario que ejecutó el flujo de trabajo) o un **aprobador designado de una de sus aprobaciones**: el usuario nombrado o un miembro con `approver` de un grupo al que se dirija una (consulta [Aprobación humana](../guides/approvals.md#human-approval)). Así se conserva el diseño de aprobador compartido (el aprobador se une al chat del iniciador) y se mantiene fuera a terceros. La lectura es más amplia, y las operaciones que actúan, más estrictas:

| Operación | Endpoint | Iniciador | Aprobador designado | Administrador (mismo tenant) | Superadministrador |
|---|---|---|---|---|---|
| Leer la ejecución | `GET /workflow-executions/{id}` | ✅ | ✅ | ✅ | ✅ |
| Listar o abrir sus tareas | `GET .../workflow-tasks` | ✅ | ✅ | ✅ | ✅ |
| Leer el historial de la sesión del flujo de trabajo | `GET .../messages` | ✅ | ✅ | ✅ | ✅ |
| Dirigir su agente | `POST .../agent` | ✅ | ✅ | ❌ | ✅ |
| Cambiar el **estado** de una tarea (a mano o a través del agente) | `PATCH /workflow-tasks/{id}` | ✅ | Solo en una tarea cubierta por una aprobación dirigida a esa persona | ❌ | Solo en una tarea que ninguna aprobación cubra |
| Resolver una aprobación | `PATCH /approvals/{id}` | ❌ | Solo el aprobador de esa aprobación | ❌ | ❌ |
| Eliminar la ejecución | `DELETE /workflow-executions/{id}` | Solo si es Administrador | Solo si es Administrador | ✅ | ✅ |

Quien quede fuera de esas columnas recibe HTTP 403. La misma lista `GET /approvals` muestra a un Administrador todas las aprobaciones del tenant, en línea con la fila de lectura anterior.

La **lista de tareas de una ejecución queda fijada al ejecutar el flujo de trabajo**: las tareas se copian de las plantillas publicadas del flujo de trabajo y, después, solo cambia su `status` (y la causa de un fallo). Nadie añade, quita, renombra, redescribe ni vuelve a enlazar las tareas de una ejecución a través de la API; para cambiar los pasos, edita las [plantillas de tareas](../guides/workflows.md#adjusting-the-task-templates) y vuelve a ejecutar.

**Las tres últimas filas merecen una segunda lectura.**

La fila de estado y la de resolución son las **excepciones de la capa de propiedad a la omisión del Superadministrador** anunciadas al principio de esta página: solo el aprobador designado puede resolver una aprobación, y el estado de una tarea solo pueden cambiarlo el iniciador o un aprobador al que se dirija una aprobación **que cubra esa tarea**; no basta con ser aprobador de la ejecución y, una vez que una aprobación cubre la tarea, tampoco puede hacerlo un Superadministrador ni un Administrador. Un aprobador solo puede hacer avanzar una tarea dentro del alcance de lo que se le pidió aprobar, es decir, la tarea que nombra la aprobación y los pasos siguientes hasta la próxima aprobación; eso permite que una decisión reanude la ejecución sin que un aprobador impulse pasos ajenos. De lo contrario, pasar una tarea directamente a `completado` permitiría a cualquiera sustituir al destinatario (consulta [Aprobación humana](../guides/approvals.md#human-approval)). La regla es la misma tanto si el cambio se hace a mano como si se le pide al agente de ejecución en el chat de la sesión del flujo de trabajo: el agente rechaza un cambio de estado que quien lo dirige no podría hacer directamente.

**Eliminar** una ejecución tiene la forma contraria: es un simple control por rol, sin ningún componente de propiedad, de modo que un Administrador puede eliminar cualquier ejecución del tenant, mientras que un iniciador que no sea Administrador no puede eliminar la suya. Al eliminarla se eliminan también las tareas de la ejecución y su sesión del flujo de trabajo.

## Secciones de toda la plataforma {#platform-wide-sections}

[Tenants](../guides/users-and-groups.md#tenants) y [Configuración del sistema](../guides/system-settings.md) son las dos secciones de administración que el **Superadministrador** se reserva. A diferencia de lo que ocurre en el resto, aquí también se controlan las lecturas: ambas contienen configuración de la plataforma, no datos de un tenant, así que la entrada de la barra lateral, la tarjeta de bienvenida y todos los endpoints que hay detrás están cerrados para los demás roles.

## La aptitud del aprobador con el tiempo {#approver-eligibility}

⚠️ La aptitud del aprobador se valida al crear la aprobación: `list_users` / `list_user_groups` solo ofrecen destinos que realmente pueden aprobar, y `request_approval` rechaza cualquier otro (incluido un grupo sin ningún miembro apto). Lo que ocurre *después* varía según el destino, y la diferencia es deliberada:

- **Destino de usuario**: revocar más tarde el rol `approver` **no** invalida las aprobaciones ya dirigidas a ese usuario. Puede seguir resolviéndolas, de modo que un flujo de trabajo en curso nunca se queda atascado.
- **Destino de grupo**: la pertenencia y el rol se vuelven a comprobar en el momento de decidir, porque «el grupo» es un conjunto cambiante y no una persona fija. Eso permite que un miembro recién añadido se haga cargo de una solicitud pendiente, pero tiene dos caras: quitarle al grupo la concesión de `approver`, o dejarlo sin miembros aptos, hace que la solicitud pendiente **no pueda resolverla nadie** y que su ejecución espere indefinidamente. Volver a conceder el rol o volver a añadir un miembro la desbloquea de inmediato.
