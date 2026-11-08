---
title: Notificaciones
sidebar_position: 11
---

# Notificaciones

El trabajo de los flujos de trabajo ocurre en segundo plano: una ejecución de diseño termina mientras estás en otra cosa, o una aprobación espera a alguien que no ha abierto la aplicación. Las notificaciones son la forma en que esos eventos llegan a quien los necesita.

En la barra de herramientas superior, tanto en el encabezado del chat como en la barra lateral de administración, hay un **icono de campana** con una insignia que indica el número de notificaciones sin leer.

![Diagrama de flujo que muestra cómo un evento de flujo de trabajo se dirige al único usuario afectado, o a todos los miembros aptos del grupo de aprobadores, y se reparte entre la campana, la página de notificaciones y, si está habilitado, el correo electrónico.](./img/notifications-routing.svg#gh-light-mode-only)
![Diagrama de flujo que muestra cómo un evento de flujo de trabajo se dirige al único usuario afectado, o a todos los miembros aptos del grupo de aprobadores, y se reparte entre la campana, la página de notificaciones y, si está habilitado, el correo electrónico.](./img/notifications-routing-dark.svg#gh-dark-mode-only)

## Los cinco eventos {#the-five-events}

| Tipo | Cuándo se genera | Quién lo recibe |
|---|---|---|
| borrador listo | La ejecución de diseño en segundo plano de [Generar flujo de trabajo](./workflows.md#generating-a-workflow) ha terminado y las plantillas de tareas del borrador están listas para revisarlas. | Quien inició la generación |
| generación fallida | Esa misma ejecución de diseño ha fallado. Se ejecuta sin supervisión y sin ningún cliente conectado, así que esta es la forma de enterarte; el motivo aparece en la página de detalle del flujo de trabajo y en su chat de diseño. | Quien inició la generación |
| solicitud de aprobación | El agente pide una decisión durante la ejecución y se queda esperando. | El [aprobador designado](./approvals.md#human-approval); si el destino es un grupo, una por cada miembro apto |
| ejecución finalizada | Todas las tareas de una ejecución han llegado a un estado final. Se genera una sola vez por ejecución. | Quien inició la ejecución |
| solicitud de entrada | Está a punto de empezar una tarea cuyo servidor MCP pedirá [confirmaciones](./workflow-executions.md#mcp-server-confirmations), y la ejecución espera a que la reanudes desde el chat. | Quien inició la ejecución |

Al hacer clic en una notificación, se marca como leída y te lleva al lugar al que apunta: los eventos de una ejecución, al chat de la ejecución; los de un flujo de trabajo, a su página de detalle.

## Dónde aparecen las notificaciones {#where-notifications-appear}

| | **El menú desplegable de la campana** | **La [página de notificaciones](./notifications.md#notification-history-page)** |
|---|---|---|
| **Muestra** | Solo las no leídas: lo que aún requiere atención | El historial completo, incluidas las leídas |
| **Cómo se accede** | Con la campana de la barra de herramientas | Con el botón de perfil de la barra de herramientas → **Notificaciones** |
| **Marcar como leído** | Por fila (✓), y **Marcar todo como leído** en el encabezado del panel mientras queden notificaciones sin leer | Por fila (✓) |
| **Eliminar** | No disponible | Por fila (✕), tras una confirmación |

Nada en el menú desplegable elimina una notificación; marcarla como leída solo la quita de en medio. La lista se actualiza sola cada medio minuto, de modo que las notificaciones nuevas llegan sin recargar la página.

## Página de historial de notificaciones {#notification-history-page}

La página de notificaciones muestra todas las que has recibido en una tabla que se puede ordenar y filtrar, con el título, el tipo y la hora de creación. Filtra la columna **Leído** por **Sí** o **No** para ver solo las notificaciones leídas o las no leídas. Este es el único lugar donde se puede eliminar definitivamente una notificación.

Las notificaciones propias de A2Flow aparecen en [tu idioma](./users-and-groups.md#language), mientras que el título y la descripción de una aprobación se mantienen tal como los escribió el agente. La ordenación y el filtrado por título funcionan sobre el texto en inglés, por lo que en otros idiomas la columna **Título** no ofrece ninguna de las dos opciones; filtra por **Tipo** en su lugar.

Las notificaciones son siempre individuales: solo ves las tuyas, y cada una desaparece junto con la cuenta, la ejecución o el flujo de trabajo al que pertenece.

## Entrega de correo {#email-delivery}

Cuando un superadministrador ha configurado un servidor SMTP en [Configuración del sistema](./system-settings.md), los mismos cinco eventos **también se envían por correo electrónico** al destinatario, para que una solicitud de aprobación no tenga que esperar a que alguien abra la aplicación.

El mensaje lleva como asunto el título de la notificación, como texto su cuerpo y un enlace a aquello a lo que se refiere: la ejecución o el flujo de trabajo. El enlace se construye a partir de la **URL base de la aplicación** configurada; si no hay ninguna, el mensaje se envía sin enlace.

Los destinatarios a los que no se puede llegar se descartan antes de contactar con ningún relé: el usuario interno del sistema, las cuentas deshabilitadas o eliminadas, las cuentas con la dirección sin verificar y las cuentas sin dirección. No existe la opción de darse de baja por usuario: la entrega de correo está activada o desactivada para toda la plataforma.

### La cola de entrega {#the-delivery-queue}

No se envía nada mientras haya una operación de flujo de trabajo en curso. La notificación y su mensaje ya generado se escriben juntos, de modo que un fallo del sistema nunca puede dejar una notificación cuyo correo no se haya puesto en cola. Después, un worker vacía esa cola:

- **Con ritmo controlado.** Un límite de velocidad mantiene el relé en un número fijo de mensajes por segundo, y cada lote completo sale por una misma conexión reutilizada.
- **Con reintentos.** Un fallo transitorio (el relé está caído o rechaza las credenciales) programa otro intento con una espera creciente: 15 s, 30 s, 1 min, 2 min, duplicándose hasta llegar a una hora. Los intentos previstos de forma predeterminada permiten aguantar aproximadamente una hora de interrupción.
- **Se da por perdido cuando no hay remedio.** Un fallo que el relé notifica como permanente, por ejemplo un destinatario desconocido, no se reintenta en absoluto. Un mensaje que ha agotado sus intentos, o que ha fallado de forma permanente, permanece en la cola como `fallido` con su último error: un mensaje no entregable que se puede revisar, no una pérdida silenciosa. Los mensajes entregados se purgan a los 30 días; los no entregables se conservan.

Solo un proceso envía a la vez, y eso es lo que hace que el límite de velocidad sea exacto y no aproximado. Ejecutar más de un worker aporta conmutación por error, no más rendimiento. Si un proceso de envío se cae a mitad de un lote, no consume ningún intento: la siguiente pasada recupera su trabajo.

De forma predeterminada, el propio proceso de la API ejecuta el worker. Con Docker Compose se ejecuta en su lugar un servicio de worker dedicado, que mantiene el correo fuera del proceso que atiende las solicitudes. Todos los parámetros ajustables figuran en la [referencia de configuración](../operations/configuration.md#outgoing-email-queue).

Los síntomas de acumulación de mensajes y de bloqueo del relé se pueden ver en el [endpoint de métricas](../operations/metrics.md).
