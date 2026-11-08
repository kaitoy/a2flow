---
title: Registros de auditoría
sidebar_position: 12
---

# Registros de auditoría

**Registros de auditoría** reúne los cuatro registros que A2Flow conserva de lo que hizo en tu nombre: las llamadas a herramientas que hicieron sus agentes, las sesiones en las que una persona actuó como otra, la autoridad que aportó cada aprobación concedida y los correos que envió. Todos son de solo adición: nada en esta pantalla edita ni elimina un registro, y eso es lo que los convierte en pruebas.

Abre **Registros de auditoría** en la barra lateral de administración. Sobre la tabla hay cuatro pestañas:

| Pestaña | Cada fila es |
|---|---|
| **Invocaciones de herramientas** | Una decisión que el gateway MCP tomó sobre una llamada a una herramienta |
| **Suplantaciones** | Una sesión en la que un administrador actuó como otro usuario |
| **Certificados** | La autoridad que respalda las llamadas a herramientas de cada tarea |
| **Correos** | Un mensaje de notificación puesto en cola para su entrega |

Cada lista se comporta como cualquier otra tabla de administración (ordenación, filtrado, selector de columnas, paginación): consulta [Interfaz de administración](./admin-ui.md#the-list-screen). Al hacer clic en la primera celda de una fila se abre una página de detalle de solo lectura que muestra los valores largos que la celda de la tabla recorta.

## Quién puede verlo {#who-sees-it}

La sección solo se muestra a **Administrador** y **Superadministrador**. Los demás usuarios ven una pantalla de acceso denegado, y la sección no aparece en su barra lateral.

Esto es más estricto que en la mayoría de las secciones, cuya lectura está abierta a cualquiera que haya iniciado sesión. Estas listas abarcan todas las ejecuciones, cuentas y mensajes del tenant, así que aquí no basta con el acceso de participante que te permite ver los registros de *tu propia* ejecución. Las vistas más limitadas siguen donde estaban: las llamadas a herramientas de una ejecución siguen en su página de [Invocaciones de herramientas](./workflow-executions.md#tool-invocations), y el certificado de una aprobación sigue en la propia [aprobación](./approvals.md), aunque solo esta lista muestra además los certificados concedidos a tareas para las que no se pidió aprobación a nadie.

Un Superadministrador ve el tenant que tenga seleccionado en el selector de tenants, y puede seleccionar **Todos los tenants** para consultarlos todos a la vez. En ese modo, cada lista añade una columna **Tenant** como primera columna por la izquierda.

## Invocaciones de herramientas {#tool-invocations}

Las llamadas a herramientas que llegaron al gateway MCP y lo que este decidió sobre cada una: `permitido` para las que pasaron al servidor de destino y `denegado` para las que vetó una regla.

| Columna | Notas |
|---|---|
| **Herramienta** / **Servidor** | Qué se llamó y dónde |
| **Decisión** | `permitido` o `denegado` |
| **Motivo de la denegación** | Por qué se rechazó una llamada, con las palabras de la propia regla |
| **Ejecución del flujo de trabajo** | La ejecución a la que pertenecía la llamada, con un enlace a ella |
| **Aprobación** / **Certificado** | El certificado que presentó la llamada y la aprobación que lo respalda, si fue una aprobación quien lo concedió |
| **Resumen de los argumentos** | Una huella digital de lo que pedía la llamada |

Los argumentos en sí nunca se guardan, solo la huella digital que cubre la firma presentada, lo que permite volver a comprobar más tarde una llamada registrada sin conservar lo que contenía. La página de detalle muestra la huella digital completa, la firma y el instante exacto que se firmó.

Las llamadas a una herramienta [simulada con un mock](./tool-mocks.md) no aparecen aquí, sea cual sea su resultado, ya que una llamada simulada no llega a ningún servidor. Esas llamadas se inspeccionan en la transcripción del chat de la ejecución.

## Suplantaciones {#impersonations}

Una fila por cada sesión en la que un administrador actuó como otro usuario, desde el momento en que empezó hasta que terminó. Una fila sin **Finalizada el** es una sesión todavía en curso, marcada como **Activo**.

| Columna | Notas |
|---|---|
| **Suplantador** | Quién actuó, con un enlace a su cuenta |
| **Usuario de destino** | Como quién actuó, con un enlace a esa cuenta |
| **Estado** | **Activo** mientras la sesión está abierta, **Finalizada** cuando se cierra |
| **Iniciada el** / **Finalizada el** | Cuándo empezó y cuándo terminó |

Las filas se delimitan por el tenant de la cuenta **suplantada**, no por el de quien actuó. Es deliberado: un Superadministrador no pertenece a ningún tenant, así que delimitarlas por quien actuó ocultaría sus sesiones a todos los tenants, y son precisamente las que un administrador más necesita ver. Consulta [Suplantación](../concepts/impersonation.md).

## Certificados {#certificates}

Lo que cada tarea estaba realmente autorizada a llamar. Cada llamada a una herramienta presenta un certificado, así que esta lista es el registro completo de la autoridad sobre herramientas concedida y agotada, incluidas las tareas para las que no se pidió aprobación a nadie.

Una tarea recibe su certificado en uno de dos momentos, y la columna **Autoridad** indica cuál:

| Autoridad | Se emite | Concedido por |
|---|---|---|
| **Aprobador** | cuando se concedió una [aprobación](./approvals.md) sobre la tarea | el aprobador que la concedió |
| **Iniciador de la ejecución** | cuando la tarea se marcó como **en curso** sin que se hubiera solicitado ninguna aprobación | quien inició la ejecución |

| Columna | Notas |
|---|---|
| **Serie** | Identifica el certificado; es el valor que la lista de invocaciones de herramientas muestra junto a las llamadas que lo presentaron |
| **Autoridad** | **Aprobador** o **Iniciador de la ejecución**: de dónde procede la concesión |
| **Concedido por** | La persona a la que se atribuye |
| **Aprobación** | La aprobación para la que se emitió, con un enlace a ella. Vacío en una concesión del iniciador de la ejecución, que no tiene ninguna aprobación detrás |
| **Estado** | **En curso**, o **Revocado** cuando la autoridad se ha agotado |
| **Herramientas permitidas** | Las herramientas que concede este certificado |
| **No antes de** / **No después de** | El periodo en el que es válido |
| **Revocado el** / **Motivo de revocación** | Cuándo y por qué dejó de contar |

**Herramientas permitidas** se lee del propio certificado emitido y no de una copia aparte, de modo que lo que muestra esta pantalla nunca puede diferir de lo que se autorizó realmente, aunque después se reescribieran las vinculaciones de las tareas de la ejecución. Nunca se muestra ni se puede descargar material de claves.

## Correos {#emails}

Los mensajes de notificación que A2Flow ha puesto en cola para su entrega y cómo le fue a cada uno.

| Columna | Notas |
|---|---|
| **Para** / **Asunto** | A quién iba dirigido y sobre qué |
| **Estado** | `pendiente`, `enviando`, `enviado` o `fallido` |
| **Intentos** | Cuántos intentos de entrega se han hecho |
| **Enviado el** | Cuándo salió |
| **Último error** | Por qué falló el intento más reciente |

Un mensaje que no se pudo entregar pasa a `fallido` y se **conserva** en lugar de eliminarse, de modo que una notificación que nunca llegó sigue visible con el motivo registrado. El cuerpo del mensaje se congela cuando se genera la notificación, no se redacta en el momento del envío; la página de detalle lo muestra completo, exactamente como se entregó.

Un Superadministrador puede eliminar una fila `enviado` o `fallido`; un Administrador no. A ambos se les rechaza eliminar una fila que aún esté `pendiente` o `enviando`, ya que el proceso de envío de correo podría tenerla en sus manos. Consulta [Notificaciones](./notifications.md) para saber cómo llegan estos mensajes a la cola, y [Configuración del sistema](./system-settings.md) para el servidor de correo por el que pasan.
