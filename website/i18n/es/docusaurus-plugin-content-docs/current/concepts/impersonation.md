---
title: Suplantación
sidebar_position: 4
---

# Suplantación

La suplantación permite a un usuario con privilegios **actuar como** otro usuario, ya sea para reproducir lo que esa persona ve o para hacer algo en su nombre. Cada solicitud hecha durante la suplantación se atribuye al usuario suplantado, y cada sesión de suplantación queda registrada. Para iniciar una se necesita `admin` (o `super_admin`).

## Quién puede suplantar a quién {#who-can-impersonate-whom}

| Suplantador ＼ Destino | Tiene `super_admin` | Tiene `admin` | Cualquier otro usuario |
|---|---|---|---|
| **Superadministrador** | ❌ | ✅ en toda la plataforma | ✅ en toda la plataforma |
| **Administrador** | ❌ | ❌ | ✅ solo en su propio tenant |
| Cualquier otro rol | ❌ | ❌ | ❌ La acción ni siquiera se ofrece |

Lo importante es la forma de esa tabla: la suplantación nunca sirve para obtener un privilegio que el suplantador no tenga ya. Un Administrador corriente no puede suplantar a otro Administrador, y un Superadministrador no gana nada suplantando a uno, porque ya omite todos los controles que un Administrador superaría.

El **destino** se evalúa según sus [roles efectivos](./authorization.md#effective-roles), de modo que un `admin` heredado de un [grupo de usuarios](../guides/users-and-groups.md#user-groups) protege a quien lo tiene exactamente igual que uno concedido directamente; de lo contrario, el grupo serviría para eludir la tabla anterior.

Otros cuatro destinos se rechazan sean cuales sean sus roles: **tú mismo**, el **usuario del sistema** precargado, un usuario **deshabilitado** y uno **eliminado de forma lógica**. Y, para un Administrador, un destino de otro [tenant](./tenants.md) responde **HTTP 404, no 403**: una referencia entre tenants nunca confirma que el usuario exista.

## Iniciar y detener {#starting-and-stopping}

Inicia la suplantación con la acción **Suplantar** de la lista [Usuarios](../guides/users-and-groups.md#users); al confirmar, llegas a la página de bienvenida actuando como ese usuario. Mientras está activa, una insignia en el encabezado muestra «Actuando como `<user>`» junto con el botón **Dejar de suplantar**.

Solo puede haber una suplantación abierta a la vez: al iniciar una nueva se cierra la que estuviera abierta. Detenerla siempre es seguro, aunque no haya ninguna abierta.

## La identidad efectiva {#effective-identity}

La suplantación es **una sustitución mediante un encabezado de la solicitud, no un cambio de sesión**. La cookie de sesión real nunca cambia: el navegador simplemente adjunta a cada solicitud el ID del usuario seleccionado, y el backend resuelve a partir de él la identidad efectiva. De ahí se derivan dos consecuencias:

- La sesión del usuario real sigue viva por debajo, así que al detener la suplantación nunca hace falta volver a iniciar sesión.
- Todo lo que toca una solicitud (lecturas, escrituras y los campos de auditoría `createdBy` / `updatedBy`) se atribuye al usuario suplantado, exactamente como si hubiera iniciado sesión él mismo. **Las comprobaciones de roles también se hacen con los roles efectivos del usuario suplantado**, de modo que un Superadministrador que actúa como Solicitante queda sujeto a los controles de un Solicitante y ve la interfaz que ve un Solicitante.

Los endpoints de inicio y detención son la excepción deliberada: se controlan con los roles del usuario **real**, no con los de la identidad efectiva. De lo contrario, un administrador que suplantara a un usuario deliberadamente sin privilegios no superaría la comprobación de roles en su propia llamada de «detener» y se quedaría atascado ahí.

## Cuándo deja de ser válida una suplantación {#stale-impersonations}

La idoneidad se vuelve a comprobar en **cada** solicitud, no solo al iniciar la suplantación: la tabla anterior depende de los roles, y los roles cambian. Si la suplantación ya no es válida, la solicitud no falla: vuelve silenciosamente al usuario real y cierra el registro obsoleto. Esto incluye los casos en que el destino se deshabilita o se elimina, en que el destino asciende (también al añadirlo a un grupo que concede `admin`), en que el suplantador pierde `admin` (directamente o al salir de un grupo que lo concede) o `super_admin`, en que el suplantador deja de compartir el tenant del destino y en que la suplantación se ha detenido en otro lugar.

Hacer fallar la solicitud sería peor que inútil: la selección se guarda en el almacenamiento local del navegador, así que un error permitiría que un solo valor obsoleto dejara a un administrador legítimo sin acceso a toda la aplicación.

## Registro de auditoría {#audit-trail}

Cada sesión de suplantación queda anotada en un registro de auditoría persistente (quién, a quién y cuándo) en la tabla `impersonation_events` (consulta la [referencia de configuración](../operations/configuration.md)). Como lo que se guarda en `createdBy` / `updatedBy` es el usuario suplantado, este registro es lo único que responde a «¿quién estaba realmente detrás de esa escritura?», y precisamente por eso no es opcional.

Un Administrador consulta ese registro en la pestaña **Suplantaciones** de [Registros de auditoría](../guides/audit-logs.md#impersonations), que enumera todas las sesiones que afectaron a las cuentas de su tenant, incluidas las que abrió un Superadministrador.
