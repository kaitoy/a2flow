---
title: Etiquetas
sidebar_position: 10
---

# Etiquetas

Las etiquetas sirven para clasificar los registros. Los siete catálogos etiquetables comparten un mismo vocabulario, de modo que una etiqueta `aws` acota tanto los secretos como los servidores MCP.

![Diagrama de flujo que muestra un único vocabulario de etiquetas compartido por tenant, aplicado a siete catálogos etiquetables: Secretos, Servidores MCP, Skills de agente, Bases de conocimiento, Flujos de trabajo, Mocks de herramientas y Grupos de usuarios.](./img/tags-vocabulary.svg#gh-light-mode-only)
![Diagrama de flujo que muestra un único vocabulario de etiquetas compartido por tenant, aplicado a siete catálogos etiquetables: Secretos, Servidores MCP, Skills de agente, Bases de conocimiento, Flujos de trabajo, Mocks de herramientas y Grupos de usuarios.](./img/tags-vocabulary-dark.svg#gh-dark-mode-only)

Abre **Etiquetas** en la barra lateral de administración para gestionar el vocabulario. Cada etiqueta tiene un **Nombre** único dentro del tenant, una **Descripción** opcional, un **color** elegido de una paleta fija de ocho posiciones (cualquier otro valor de color se rechaza) y una casilla **Control de acceso**, desactivada de forma predeterminada, que convierte la etiqueta de simple rótulo en una barrera (consulta [Etiquetas de control de acceso](#access-control-tags)).

Para crear o editar una etiqueta normal se necesita el rol de administrador **o** de desarrollador, que es la unión de los roles que pueden escribir en alguno de los siete recursos etiquetables, de modo que quien vaya a necesitar una etiqueta siempre puede crearla. Una etiqueta con **Control de acceso** marcado es distinta: solo un Administrador (o un Superadministrador) puede crearla, editar cualquiera de sus campos o eliminarla. Un Desarrollador ve las etiquetas de control de acceso existentes en modo de solo lectura: la casilla como un valor fijo, los demás campos como texto sin formato y sin botones **Guardar** ni **Eliminar**. Aun así, puede seguir creando y editando etiquetas normales como siempre. La lectura sigue abierta, como en todas las demás secciones.

## Adjuntar etiquetas a un registro {#attaching-tags-to-a-record}

El formulario de creación y la página de detalle de todo registro etiquetable incluyen un selector **Etiquetas**: la selección actual aparece como chips de color que se pueden quitar, encima de un botón **Seleccionar etiquetas…**, de modo que la altura del campo depende de la selección y no del tamaño del vocabulario.

1. Haz clic en **Seleccionar etiquetas…**. El cuadro de diálogo muestra todo el vocabulario como una cuadrícula adaptable de chips de color, cada uno de los cuales funciona como un conmutador. Un chip pulsado tiene un relleno más intenso *y* una marca de verificación delante, de modo que su estado nunca depende solo del color.
2. Acota la cuadrícula si lo necesitas. Hay dos filtros que se combinan: un cuadro de nombre y una fila con las ocho muestras de la paleta, de las que puedes pulsar tantas como quieras a la vez. Tenerlas todas sin pulsar equivale a no filtrar.
3. Confirma con **Seleccionar** o descarta el borrador con **Cancelar**. Una etiqueta que has seleccionado y que después ha quedado oculta por un filtro sigue seleccionada.

Adjuntar etiquetas requiere el rol de escritura del propio registro, con independencia de quién haya creado la etiqueta.

## Filtrar por etiqueta {#filtering-by-tag}

Toda lista etiquetable tiene una columna **Etiquetas** que muestra los chips de cada registro, y el menú del encabezado de esa columna ofrece una selección múltiple. La columna mantiene todas las filas con una sola línea de altura: muestra tantos chips como quepan en su anchura actual y cuenta los demás en un chip final `+N`. Haz clic en ese chip para abrir un cuadro de diálogo con todas las etiquetas del registro, cada una con su descripción al pasar el cursor por encima. Si ensanchas la columna, arrastrando su borde u ocultando otra columna, las etiquetas contadas vuelven a aparecer como chips. La selección es **conjuntiva** (el menú lo indica como «Filtrar (todos)»), por lo que un registro debe tener *todas* las etiquetas que elijas, y añadir una más acota el resultado. Se aplica a todo el conjunto de datos, no solo a la página que hay en pantalla.

Las etiquetas son un eje independiente de los demás filtros de columna, pero siguen la misma regla en cuanto a la visibilidad: ocultar la columna **Etiquetas** con el [selector de columnas](./admin-ui.md) borra el filtro de etiquetas, igual que ocultar cualquier otra columna borra su propio filtro.

## Etiquetas de control de acceso {#access-control-tags}

Una etiqueta con **Control de acceso** marcado restringe quién puede ver los registros a los que está adjunta. Su chip lleva un icono de candado allí donde aparece (en la columna **Vista previa** de la lista de etiquetas, en la columna **Etiquetas** de un registro y en el selector), y la lista de etiquetas incorpora una columna **Control de acceso** por la que se puede filtrar.

El acceso depende de tus [grupos de usuarios](./users-and-groups.md#user-groups): cada grupo tiene sus propias etiquetas, y las de todos tus grupos se suman.

| Un registro tiene… | Lo ves cuando… |
|---|---|
| Ninguna etiqueta de control de acceso (solo etiquetas normales, o ninguna) | Siempre: las etiquetas normales nunca restringen nada |
| Una o más etiquetas de control de acceso | Tus grupos, entre todos, tienen **todas** esas etiquetas |

Un registro que no puedes ver simplemente no existe para ti: no aparece en la lista y, si abres un enlace directo, se indica que no se ha encontrado. Un Administrador o un Superadministrador lo ve todo: el Administrador está exento de todas las etiquetas de control de acceso, y el Superadministrador, además, abarca toda la plataforma y no pertenece a ningún grupo, por lo que ninguna otra regla podría alcanzarlo.

Al etiquetar se aplica una protección: **no puedes adjuntar una etiqueta de control de acceso que tus grupos no tengan.** El guardado se rechaza con un error, porque el registro dejaría de ser visible para ti la próxima vez que cargaras la página. Pide primero a un administrador que te añada a un grupo que tenga esa etiqueta. Etiquetar un *grupo de usuarios* está exento: precisamente así es como un administrador concede el acceso.

La restricción se refiere a quién puede abrir, editar, ejecutar o eliminar un registro. Lo que un registro usa internamente no se ve afectado: un flujo de trabajo sigue ejecutándose con la skill de agente a partir de la cual se generó y con los secretos a los que hacen referencia sus servidores MCP, incluso para un solicitante que no podría abrir esa skill o ese secreto.

El diseño de flujos de trabajo es la excepción: asignar una herramienta a un paso cuenta como usar tú mismo el servidor MCP. Solo puedes vincular herramientas de servidores que **tú** podrías abrir, tanto si las eliges en el selector **Herramientas MCP** de una plantilla de tarea como si se lo pides al agente de diseño, que actúa en tu nombre. Un servidor con una etiqueta de control de acceso que tus grupos no tienen nunca aparece en la lista de herramientas del agente, y vincularlo se rechaza como si el servidor no existiera. Una herramienta que ya vinculó a un paso alguien que podía verla se mantiene cuando editas ese paso, y **Descartar cambios** restaura las vinculaciones publicadas tal como estaban.

## Etiquetas de ejecuciones y aprobaciones {#execution-and-approval-tags}

Una [ejecución](./workflow-executions.md) también muestra una columna y un campo **Etiquetas**, igual que la [aprobación](./approvals.md) a la que pertenece, pero en modo de solo lectura y fuera de los siete catálogos etiquetables anteriores. Cuando se inicia una ejecución, copia las etiquetas que tiene su flujo de trabajo en ese momento; volver a etiquetar el flujo de trabajo más tarde, o eliminarlo, nunca cambia lo que muestra una ejecución ya iniciada. En estas dos pantallas no hay selector **Etiquetas** y sus listas no tienen filtro de etiquetas: adjuntar y quitar etiquetas se hace siempre en el propio flujo de trabajo.

Una etiqueta de control de acceso copiada de este modo sigue restringiendo la ejecución y sus aprobaciones, exactamente igual que restringe el flujo de trabajo: si tus grupos ya no tienen una etiqueta que la ejecución copió, tanto la ejecución como todas sus aprobaciones desaparecen de tus listas y de tus enlaces directos, aunque hayas iniciado tú la ejecución o seas su aprobador designado. Lo mismo vale para todo lo que podrías hacer dentro de la ejecución: enviar un mensaje en su chat, abrir sus tareas y aprobar o rechazar una de sus aprobaciones fallan como si la ejecución no existiera. Solo están exentos un Administrador o un Superadministrador, como con cualquier etiqueta de control de acceso. La etiqueta tiene que estar adjunta al flujo de trabajo *antes* de que se ejecute; volver a etiquetarlo después nunca llega a las ejecuciones ya iniciadas, porque la copia se hace una sola vez, en el momento en que comienza la ejecución.

Una etiqueta de control de acceso copiada en una ejecución también decide a quién se puede [pedir aprobación](./approvals.md#human-approval): para dirigirse a una persona, uno de sus grupos debe tener todas esas etiquetas de la ejecución, y para dirigirse a un [grupo de usuarios](./users-and-groups.md#user-groups), debe tenerlas el propio grupo. De lo contrario, la solicitud se rechaza, porque esa persona o ese grupo nunca podría verla para decidir. Un Administrador está exento como destino individual, ya que también se salta estas etiquetas en todos los demás casos; un grupo de usuarios no tiene esa exención, aunque haya un Administrador entre sus miembros.

## Cambiar el nombre y eliminar {#renaming-and-deleting}

**Cambiar el nombre es seguro en cualquier momento.** Los registros hacen referencia a una etiqueta por su identidad, nunca por su nombre, de modo que todos los registros que la tienen adoptan el nuevo nombre sin necesidad de volver a sincronizar nada; esa es precisamente la razón por la que las etiquetas se registran de antemano en lugar de escribirse libremente en cada registro.

**Eliminar** una etiqueta funciona al revés: en lugar de impedirlo los registros que la tienen, la etiqueta se quita de todos ellos. La confirmación lo indica. Para eliminar una etiqueta con **Control de acceso** marcado se necesita un Administrador o un Superadministrador, igual que para editarla; eliminar una etiqueta normal sigue estando al alcance de un Desarrollador.
