---
title: Flujos de trabajo
sidebar_position: 3
---

# Flujos de trabajo

Un flujo de trabajo es una unidad de trabajo reutilizable: una [skill de agente](./agent-skills.md) unida a una **lista de tareas prediseñada**, sus *plantillas de tareas*. Las plantillas quedan fijadas *antes* de cualquier ejecución, así que, al ejecutar un flujo de trabajo, el trabajo empieza de inmediato en lugar de rediseñar los mismos pasos cada vez.

Abre **Flujos de trabajo** en la barra lateral de administración para gestionarlos.

![Diagrama de flujo que muestra una skill de agente que genera un flujo de trabajo, que se refina en un borrador ajustado, se publica y se ejecuta como una ejecución del flujo de trabajo.](./img/workflows-lifecycle.svg#gh-light-mode-only)
![Diagrama de flujo que muestra una skill de agente que genera un flujo de trabajo, que se refina en un borrador ajustado, se publica y se ejecuta como una ejecución del flujo de trabajo.](./img/workflows-lifecycle-dark.svg#gh-dark-mode-only)

No hay forma de crear un flujo de trabajo vacío: un flujo de trabajo nace generándolo a partir de una skill.

## Estados {#statuses}

![Máquina de estados del estado detallado de un flujo de trabajo: generando lleva a borrador o a fallido, fallido se puede reescribir para volver a borrador, borrador se publica y pasa a publicado, publicado y modificado se alternan con nuevas ediciones y publicaciones, y cualquiera de los dos se puede desactivar para volver a borrador.](./img/workflows-status.svg#gh-light-mode-only)
![Máquina de estados del estado detallado de un flujo de trabajo: generando lleva a borrador o a fallido, fallido se puede reescribir para volver a borrador, borrador se publica y pasa a publicado, publicado y modificado se alternan con nuevas ediciones y publicaciones, y cualquiera de los dos se puede desactivar para volver a borrador.](./img/workflows-status-dark.svg#gh-dark-mode-only)

| Estado | Qué significa | Quién puede ejecutarlo |
|---|---|---|
| `generando` | La ejecución de diseño en segundo plano sigue escribiendo las plantillas de tareas. | Nadie |
| `borrador` | El diseño existe, pero nunca se ha publicado o se ha desactivado. | Desarrollador y Superadministrador, para probarlo antes de publicar |
| `fallido` | La ejecución de diseño terminó sin producir plantillas. El motivo se muestra en la página de detalle y en el chat de diseño. | Nadie |
| `publicado` | El diseño está congelado y se puede ejecutar. | Cualquiera con el rol Solicitante o superior |
| `modificado` | Se publicó una vez y después se editó. Las ejecuciones siguen usando la versión publicada. | Igual que `publicado` |

`modificado` es un estado que solo ven un **Desarrollador**, un **Revisor** o un **Superadministrador**. Para todos los demás, el flujo de trabajo figura como `publicado` y muestra el nombre, la descripción y las plantillas de tareas registrados en la última publicación: las ediciones sin publicar no les corresponde verlas, y el diseño que *sí* pueden ver es el que se usaría en su ejecución.

## Las pantallas {#the-screens}

| Pantalla | Cómo llegar | Qué puedes hacer |
|---|---|---|
| Lista de **Flujos de trabajo** | Barra lateral de administración → Flujos de trabajo | Consultar, filtrar por [etiqueta](./tags.md) y **Ejecutar** un flujo de trabajo |
| Detalle del flujo de trabajo | Haz clic en el nombre de un flujo de trabajo | Editar sus campos, **Descartar cambios**, **Abrir sesión de diseño** (Desarrollador); **Publicar**, **Desactivar** (Revisor) |
| **Plantillas de tareas** | El enlace Plantillas de tareas de la página de detalle del flujo de trabajo | Añadir, editar y reordenar los pasos a mano, como Tabla o Gráfico |
| Sesión de diseño | **Abrir sesión de diseño** en la página de detalle | Refinar los pasos hablando con el agente de diseño |

Cada registro de flujo de trabajo lleva un **Nombre**, las [etiquetas](./tags.md) con las que se clasifica, la **Skill de agente** que sigue, su estado, una **Descripción** y dos campos de prompt.

## Generar un flujo de trabajo {#generating-a-workflow}

**Generar flujo de trabajo** está disponible en dos lugares, y ambos abren el mismo diálogo sin salir de la página: la acción de fila de la lista de [Skills de agente](./agent-skills.md) y el botón de icono Generar flujo de trabajo del encabezado de la página de detalle de una skill. Los dos están deshabilitados hasta que la skill haya publicado una revisión.

1. Rellena el **Nombre del flujo de trabajo** (prellenado con el nombre de la skill) y el **Prompt** que describe el trabajo. Si quieres, elige [bases de conocimiento](./knowledge-bases.md) en **Bases de conocimiento**: se vinculan al nuevo flujo de trabajo de inmediato, de modo que el agente de diseño ya puede consultarlas. Como al generar se sale de la página, la página de detalle ofrece guardar antes los cambios sin guardar; si lo rechazas, la página queda intacta y no se genera nada.
2. El flujo de trabajo se registra de inmediato en estado `generando` y llegas a su página de detalle, que se actualiza sola mientras avanza el trabajo.
3. En segundo plano, el prompt se envía como primer mensaje de la **sesión de diseño** del flujo de trabajo. El agente de diseño sigue la skill, divide la solicitud en pasos y los registra como plantillas de tareas del flujo de trabajo: un grafo de dependencias en el que cada paso declara qué pasos deben terminar antes que él, además de las [herramientas MCP](./workflows.md#mcp-tools-for-tasks) que necesite.
4. Cuando la ejecución termina, la conversación de diseño se resume en **Prompt generado**, se escribe junto con ella una breve **Descripción** para quienes vayan a ejecutar el flujo de trabajo, el estado pasa a `borrador` y una [notificación](./notifications.md) te lleva de vuelta al flujo de trabajo mediante un enlace directo.

Si la ejecución falla, o termina sin registrar ni una sola plantilla, el flujo de trabajo queda en `fallido` con el motivo, y una notificación lo comunica. El chat de diseño sigue siendo utilizable: escribir las plantillas de tareas desde allí, o desde las páginas de administración de Plantillas de tareas, devuelve el flujo de trabajo a `borrador` y borra el fallo.

La solicitud que escribiste en el diálogo Generar flujo de trabajo no se guarda en el flujo de trabajo. Perdura como primer mensaje de la conversación de diseño, y el resumen generado conserva la intención.

## Descripción y prompt {#description-and-prompt}

Un flujo de trabajo lleva dos tipos de texto, y solo uno de ellos afecta a una ejecución.

| Campo | Qué es | Quién lo escribe | Quién puede editarlo | Quién puede verlo |
|---|---|---|---|---|
| **Descripción** | Una explicación sencilla de para qué sirve el flujo de trabajo. Ninguna ejecución la lee nunca. | La IA al generar el flujo de trabajo y, después, una persona | Cualquier Desarrollador | Todos los que pueden abrir el flujo de trabajo |
| **Prompt** | Una sustitución del prompt generado | Una persona, normalmente retocando a mano el resumen de la IA | Cualquier Desarrollador | Administrador, Desarrollador, Revisor |
| **Prompt generado** | El resumen de la conversación de diseño hecho por la IA | La IA | Solo Superadministrador | Administrador, Desarrollador, Revisor |

El prompt vigente se entrega al agente de ejecución como contexto en cada ejecución: **Prompt** prevalece si no está vacío; en caso contrario, se usa **Prompt generado**. Como la sustitución suele nacer como copia del resumen, el campo Prompt incluye la acción **Mostrar las diferencias con el prompt generado**, que abre una comparación palabra por palabra entre ambos. Lee los valores que hay en ese momento en el formulario, así que también compara las ediciones sin guardar.

La Descripción es lo que muestra la lista de flujos de trabajo y lo que muestra el diálogo **Ejecutar flujo de trabajo** debajo de su confirmación, para que quien inicia una ejecución pueda comprobar que ha elegido el correcto. Los campos de prompt están ocultos para todos los demás roles: en la página de detalle, en la columna opcional **Prompt** de la lista y en la página de detalle de una ejecución.

### Regenerar el prompt {#regenerating-the-prompt}

El resumen de la IA se queda obsoleto a medida que se ajustan las plantillas de tareas, así que **Prompt generado** incluye la acción **Generar a partir de la conversación de diseño**, que vuelve a resumir la conversación de diseño cuando lo pides y guarda el resultado al momento. Al publicar no se resume nada: decidir si se actualiza y cuándo es cosa tuya.

La misma acción se ofrece desde la entrada del chat de la sesión de diseño, en su menú «+», donde muestra una vista previa del cambio con el mismo diálogo de diferencias antes de guardar; resulta práctico para regenerar sin salir de la conversación. El menú está oculto mientras se siguen generando las plantillas de tareas.

Ambas son acciones de Desarrollador. Reescribir el resumen de un flujo de trabajo `publicado` lo pasa a `modificado`, porque una ejecución cuyo Prompt esté vacío recurre al resumen y, de otro modo, se desviaría de la versión publicada.

## Ajustar las plantillas de tareas {#adjusting-the-task-templates}

Las plantillas de tareas de un borrador se pueden refinar de dos maneras, combinándolas como quieras.

**Por chat.** **Abrir sesión de diseño** en la página de detalle del flujo de trabajo abre el chat de diseño: el mismo chat que el de una ejecución, con la lista de plantillas en el borde izquierdo, guiado por un agente de diseño que edita las plantillas directamente. El agente de diseño nunca ejecuta nada. La sesión la comparten todos los **Desarrolladores** del tenant, además de los Superadministradores y el creador del flujo de trabajo, de modo que un equipo puede refinar un diseño en conjunto, con el mismo comportamiento de chat compartido que una [sesión del flujo de trabajo](./workflow-executions.md#the-workflow-session-screen), incluidos los avatares de remitente de cada mensaje. Un **Revisor** puede abrir el mismo chat para leer su historial antes de decidir si publica, pero el cuadro de mensaje está oculto: revisar un diseño no incluye dirigirlo.

**A mano.** Las páginas de **Plantillas de tareas** ofrecen una vista de **Tabla** y otra de **Gráfico**, un formulario de creación y una página de detalle por plantilla con los selectores **Depende de** y **Herramientas MCP**. El Gráfico apila las plantillas en una sola columna vertical por orden de dependencia, y cada una se ramifica hacia la derecha en los servidores MCP de los que vincula herramientas y luego en las herramientas individuales.

Las plantillas reflejan estructuralmente las tareas de una ejecución (título, descripción, aristas de dependencia y vinculaciones de herramientas), pero **no llevan estado**: el ciclo de vida pertenece a una ejecución, no al diseño. Las dependencias deben apuntar a plantillas del mismo flujo de trabajo, y una arista que cerraría un ciclo se rechaza.

## Publicar {#publishing}

**Publicar**, en la página de detalle del flujo de trabajo, es lo que hace ejecutable un flujo de trabajo. Es una acción de **Revisor**: un Desarrollador crea y edita un flujo de trabajo, pero ya no lo publica, de modo que quien promociona un diseño no es quien lo escribió. Necesita al menos una plantilla y que no haya ninguna generación en curso.

Publicar **congela el diseño**: el nombre del flujo de trabajo, su descripción, su prompt vigente y su lista completa de plantillas, incluidas las aristas de dependencia y las vinculaciones de herramientas, se capturan como una nueva versión publicada: **v1**, **v2**, etc. Las versiones anteriores se conservan en el [historial de versiones](#version-history). Aquí no interviene ninguna IA; actualizar el resumen es una [acción aparte](./workflows.md#regenerating-the-prompt). Vuelve a ajustar y publicar tantas veces como quieras: las ejecuciones ya iniciadas no se ven afectadas, porque cada una tomó su propia copia de las tareas.

## Editar un flujo de trabajo publicado {#editing-a-published-workflow}

Editar un flujo de trabajo después de publicarlo no cambia en silencio lo que se ejecuta. Guardar el formulario de detalle, regenerar el prompt de la IA o añadir, editar o eliminar una plantilla de tarea, incluido cualquier cambio que haga el agente de diseño en el chat, pasa el flujo de trabajo a `modificado`.

| Mientras está `modificado` | |
|---|---|
| Qué usan las ejecuciones | La **última versión publicada** (su nombre, su prompt vigente y sus plantillas), no las ediciones, salvo que un Desarrollador las pida (consulta [Probar las ediciones](#trying-the-edits-out)) |
| Quién puede ejecutarlo | Las mismas personas que cuando está `publicado`; el botón Ejecutar no tiene ninguna restricción distinta |
| Quién ve las ediciones | Solo Desarrollador, Revisor y Superadministrador |
| **Publicar** (Revisor) | Lleva las ediciones a las ejecuciones futuras y a lo que ven todos los demás |
| **Descartar cambios** (Desarrollador) | Desecha las ediciones: las plantillas se reescriben a partir de la versión publicada, se restauran el nombre y la descripción, se vuelve a escribir el prompt de la versión publicada y el flujo de trabajo vuelve a `publicado` |

**Descartar cambios** es el icono de deshacer de la barra de estado de la página de detalle, junto a Publicar. Descartar en un flujo de trabajo sin cambios sin publicar no hace nada, salvo informar de ello.

A todos los que no tienen el rol Desarrollador ni Revisor se les sirve en cambio la versión publicada, en todo momento: el nombre y la descripción del flujo de trabajo en las páginas de lista y de detalle, sus pantallas de **Plantillas de tareas** e incluso lo que encuentra una búsqueda por nombre en la lista. Su estado figura como `publicado`, y una plantilla de tarea añadida después de la última publicación simplemente no existe para ellos. Así, un rediseño a medias nunca confunde a quienes solo necesitan ejecutar el flujo de trabajo, y lo que ven siempre coincide con lo que haría su ejecución.

## Historial de versiones y reversión {#version-history}

Todas las publicaciones se conservan. **Historial de versiones**, el icono de reloj del encabezado de la página de detalle del flujo de trabajo, las enumera de la más reciente a la más antigua, con el número, el nombre y la descripción de cada versión, y cuándo y quién la publicó. Solo pueden consultarlo un **Administrador**, un **Desarrollador**, un **Revisor** o un **Superadministrador**; un Solicitante o un Aprobador ni siquiera ve el icono de reloj.

Para volver a un diseño anterior (Desarrollador):

1. Abre **Historial de versiones** y haz clic en **Restaurar** en la versión que quieras.
2. Confirma. Las plantillas, el nombre, la descripción y el prompt de la versión reemplazan el diseño actual del flujo de trabajo, y vuelves al flujo de trabajo.
3. Comprueba el resultado. Restaurar **no** publica: las ejecuciones siguen usando la versión publicada actual hasta que un Revisor hace clic en **Publicar**, lo que registra el diseño restaurado como una nueva versión.

| Estado anterior | Estado tras restaurar |
|---|---|
| `publicado` o `modificado` | `modificado`, o `publicado` si restauraste la última versión, ya que entonces no queda nada sin publicar |
| `borrador` | `borrador` |

¿Has cambiado de opinión antes de publicar? **Descartar cambios** vuelve a poner la versión publicada actual. Una versión que vincula una herramienta de un servidor MCP eliminado después no se puede restaurar; la restauración se rechaza con un error.

### Notas internas {#internal-notes}

**Notas internas**, en la página de detalle del flujo de trabajo, es un lugar para dejar constancia de por qué has revertido o de cualquier otra cosa que deba saber el equipo que ejecuta el flujo de trabajo.

| | |
|---|---|
| Quién las ve | Administrador, Desarrollador y Revisor. Están ocultas para todos los demás. |
| Quién puede editarlas | Esos mismos tres roles. Escribe en el campo y haz clic en su icono de guardar. |
| Efecto en el flujo de trabajo | Ninguno. Guardar no cambia el estado, y las ejecuciones nunca leen las notas. |
| Versiones | No tienen versiones. Publicar, restaurar una versión y **Descartar cambios** dejan las notas como están. |

## Desactivar un flujo de trabajo {#deactivating-a-workflow}

**Desactivar**, el icono de apagado que aparece junto a Publicar mientras un flujo de trabajo está `publicado` o `modificado`, disponible para el mismo rol **Revisor** que Publicar, lo devuelve a `borrador`. Eso revoca el acceso de ejecución del rol Solicitante, la misma restricción con la que empieza un flujo de trabajo nunca publicado, mientras que un Desarrollador o un Superadministrador aún pueden ejecutarlo para hacer pruebas. Las plantillas de tareas, los dos campos de descripción y la instantánea publicada quedan exactamente como estaban, de modo que al volver a publicar se restablece directamente.

## Ejecutar un flujo de trabajo {#running-a-workflow}

Al hacer clic en **Ejecutar** en la lista de flujos de trabajo se crea una **ejecución**: un registro independiente que captura una instantánea del flujo de trabajo en ese momento.

![Diagrama de flujo que muestra el flujo de trabajo publicado y los mocks de herramientas elegidos copiados por valor en la instantánea de una nueva ejecución, que abre una sesión del flujo de trabajo.](./img/workflows-snapshot.svg#gh-light-mode-only)
![Diagrama de flujo que muestra el flujo de trabajo publicado y los mocks de herramientas elegidos copiados por valor en la instantánea de una nueva ejecución, que abre una sesión del flujo de trabajo.](./img/workflows-snapshot-dark.svg#gh-dark-mode-only)

En una **ejecución de prueba**, el diálogo Ejecutar enumera además, en **Herramientas simuladas**, los [mocks de herramientas](./tool-mocks.md) de las herramientas que usa alguna tarea del flujo de trabajo, más todos los mocks de herramientas integradas; al marcar uno se simula esa herramienta en esta ejecución, de modo que una prueba previa a la publicación se puede repetir sin los efectos secundarios de la herramienta. Una ejecución de prueba es la de un flujo de trabajo en `borrador` o la de las ediciones sin publicar de uno `modificado` (más abajo). En cualquier otro caso, el diálogo no ofrece mocks, y si se pide uno de todos modos, se rechaza: una ejecución que pareciera real y en silencio no hiciera nada sería peor que no ejecutar nada.

### Probar las ediciones {#trying-the-edits-out}

Mientras un flujo de trabajo está `modificado`, contiene dos diseños, así que el diálogo Ejecutar pregunta a un **Desarrollador** cuál ejecutar:

| Opción | Qué ejecuta | Cómo se registra |
|---|---|---|
| **Versión publicada** | El diseño capturado en la última publicación, el que reciben todos los demás | Una solicitud real |
| **Ediciones sin publicar** | El diseño tal como está ahora mismo en el editor | Una **ejecución de prueba**: puede simular herramientas y queda fuera de las [métricas de operaciones](../operations/metrics.md) |

La versión publicada viene preseleccionada, porque eso es lo que significa aquí una solicitud real. Elegir las ediciones es la manera de ensayar un rediseño de principio a fin antes de comprometerse con él, y es una acción de Desarrollador, ya que nadie más puede ver esas ediciones. La opción no aparece en un flujo de trabajo en `borrador` o `publicado`: solo hay un diseño que ejecutar.

Todo lo que la ejecución necesita se copia en ella al iniciarse, así que las ediciones posteriores nunca la alcanzan:

| Se copia en la ejecución | Se toma de |
|---|---|
| El nombre y el prompt vigente | La última versión publicada o, en un flujo de trabajo en `borrador` o cuando un Desarrollador eligió las ediciones sin publicar, el estado actual del editor |
| Las plantillas de tareas, como tareas `pendiente` con sus dependencias y vinculaciones de herramientas | El mismo diseño |
| La revisión de la skill de agente a la que queda fijada la ejecución | La revisión publicada de la skill |
| Los mocks de herramientas elegidos, por valor | Los mocks tal como están en ese momento |

Después llegas a la **sesión del flujo de trabajo**, el chat en el que transcurre la ejecución. Se abre con un mensaje inicial fijo y el agente empieza de inmediato: las tareas se aprobaron al publicar, así que no hay nada que confirmar antes. A partir de ahí, la ejecución se comporta como cualquier chat, incluidas las superficies interactivas renderizadas y los botones que contienen. La guía de [Ejecuciones de flujos de trabajo](./workflow-executions.md) explica esa pantalla.

### Cómo avanza el agente por las tareas {#how-the-agent-works-through-the-tasks}

El agente de ejecución enumera las tareas de la ejecución, elige la siguiente que se pueda ejecutar (una tarea `pendiente` cuyas dependencias se hayan completado todas), la marca como `en curso`, hace el trabajo según indica la skill y la marca como `completado`, `fallido` u `omitido`. Cuando todas las tareas han alcanzado un estado terminal, una [notificación](./notifications.md) avisa de que la ejecución ha terminado.

Puedes ver cómo se actualizan los estados en directo en la vista de solo lectura **Tareas del flujo de trabajo** de la ejecución, como Tabla o Gráfico. La lista de tareas de la ejecución es fija (es la que se congeló al publicar el flujo de trabajo), así que el agente solo hace pasar cada tarea por sus estados y nunca añade ni quita ninguna.

**Tareas que deben esperar hasta una hora concreta.** Escribe el requisito en la descripción de la tarea con palabras sencillas: «ejecutar después de las 9:00 de mañana», «no antes del día 1 del mes». Cuando el agente llega a esa tarea antes de la hora, la deja en `pendiente`, indica en el chat cuándo continuará la ejecución y se detiene. Su sesión muestra **Programada** hasta entonces y, a esa hora, A2Flow la reanuda por su cuenta, sin que nadie tenga que tener el chat abierto. Una hora escrita sin zona horaria se interpreta en la zona horaria local del despliegue. Las ramas que se trabajan en otras sesiones siguen avanzando mientras una espera, y un mensaje enviado a la sesión en espera la reanuda al instante.

## Herramientas MCP para las tareas {#mcp-tools-for-tasks}

Las tareas pueden usar herramientas de los servidores registrados en [Servidores MCP](./mcp-servers.md). Las herramientas se vinculan en tiempo de diseño y se hacen cumplir en tiempo de ejecución.

![Diagrama de flujo que muestra una vinculación de herramienta en tiempo de diseño copiada a la tarea al ejecutar y comprobada al llamar: si la herramienta está vinculada a una tarea en curso, la llamada pasa; de lo contrario, se rechaza indicando las herramientas permitidas.](./img/workflows-tool-binding.svg#gh-light-mode-only)
![Diagrama de flujo que muestra una vinculación de herramienta en tiempo de diseño copiada a la tarea al ejecutar y comprobada al llamar: si la herramienta está vinculada a una tarea en curso, la llamada pasa; de lo contrario, se rechaza indicando las herramientas permitidas.](./img/workflows-tool-binding-dark.svg#gh-dark-mode-only)

Durante el diseño, el agente puede enumerar las herramientas que ofrecen los servidores que puedes ver (un servidor que una [etiqueta de control de acceso](./tags.md) te oculta queda fuera) y asignar a cada paso las que necesite. Esas vinculaciones se guardan en la plantilla y se copian en las tareas de la ejecución cuando esta se inicia.

En tiempo de ejecución, cada llamada se comprueba antes de llegar a un servidor: el par (servidor, herramienta) debe estar vinculado a una tarea en curso en ese momento. Las llamadas a herramientas no vinculadas se rechazan con un mensaje que indica cuáles están permitidas, de modo que un agente compartido entre flujos de trabajo nunca puede recurrir a una herramienta que no se concedió a la tarea. Una tarea que además tenga adjunta una [aprobación](./approvals.md) también está sujeta a ella.

**Vincular herramientas a mano.** Los formularios de plantilla incluyen un selector de **Herramientas MCP** que funciona en dos pasos: elige un servidor en un diálogo paginado y luego añade una de sus herramientas desde un desplegable; cada herramienta añadida se convierte en un chip que se puede quitar. Solo se consulta el servidor elegido, así que abrir el formulario no contacta con todos los servidores registrados; uno al que no se puede llegar lo indica en lugar de su lista de herramientas, y una herramienta ya vinculada conserva su chip en cualquier caso. Las herramientas vinculadas aparecen como chips en la columna **Herramientas** de las listas de Plantillas de tareas y de Tareas del flujo de trabajo.

**Herramientas cuya entrada no necesita aprobación.** El chip de cada herramienta en **Herramientas seleccionadas** lleva un pequeño botón con un escudo junto a su botón de quitar. Al hacer clic, los valores con los que se llama a esa herramienta dejan de formar parte de lo que una [aprobación](./approvals.md) que cubra el paso pide aceptar a una persona; la propia aprobación sigue vigente y el paso sigue esperándola. El icono y el tono del botón cambian para mostrar el estado actual de la herramienta, y al pasar el cursor por encima se indica ese estado y lo que hará el clic.

Haz clic solo en una herramienta que **lea**: un listado, una búsqueda, una comprobación de estado. Esto existe por dos motivos, y ambos tienen que ver con el trabajo de solo lectura:

| | |
|---|---|
| No hay nada que sopesar | Nadie necesita aceptar los argumentos de una consulta que no cambia nada |
| Los valores aún no se pueden saber | Un paso puede buscar algo para decidir qué hacer a continuación, así que no puede decir de antemano qué va a pedir |

Déjalo en su estado predeterminado para cualquier cosa que escriba, elimine, gaste o envíe. El valor predeterminado es «necesita aprobación», así que una herramienta añadida sin tocarla más mantiene su entrada limitada. Una herramienta cambiada a «no necesita aprobación» aparece como **Cualquier entrada** en la aprobación que la ejecución pida más adelante, de modo que el aprobador ve qué herramientas quedaron sin limitar sin tener que deducirlo.

**Herramientas que preguntan al iniciador.** Algunas herramientas se detienen en mitad de la llamada para hacer una pregunta a la persona que ejecuta el flujo de trabajo; Azure MCP Server pide consentimiento antes de cada operación sobre un secreto. Indica al agente de diseño qué herramienta de qué tarea lo hace, en el prompt al generar el flujo de trabajo o en su sesión de diseño, y este la marca como que pregunta. Un paso con una herramienta así espera a que su iniciador lo reanude antes de empezar, de modo que esté en el chat para responder ([Confirmaciones de un servidor MCP](./workflow-executions.md#mcp-server-confirmations)). Una herramienta sin esta marca no puede preguntar. El formulario de administración no tiene ningún control para la marca; conserva lo que haya establecido el agente de diseño. En la cronología de tareas de una ejecución, el diálogo **Herramientas vinculadas** rotula esa herramienta como **Pregunta al iniciador durante la llamada**.

**Títulos de las tareas.** Ambas listas muestran todos los registros en lugar de paginar, lo que permite que la columna **Depende de** funcione como referencia cruzada: cada dependencia se nombra por su título, y al pasar el cursor por ese chip se resalta la fila a la que apunta. Al agente de diseño se le exigen títulos imperativos concisos, de 2 a 4 palabras y 50 caracteres, para que se lean bien como chips; uno más largo se rechaza con una nota que le indica que pase el detalle a la descripción. El límite obliga al agente, no a las personas: un título editado desde el formulario de administración puede llegar a 200 caracteres, y el que no cabe en su chip se recorta y se muestra al pasar el cursor.

## Bases de conocimiento {#knowledge-bases}

Elige bases de conocimiento en **Bases de conocimiento**, en la página de detalle del flujo de trabajo, y haz clic en **Guardar**: el agente de diseño y el agente de ejecución las consultarán mientras trabajan; consulta [Bases de conocimiento](./knowledge-bases.md#linking-a-knowledge-base-to-a-workflow). La elección no forma parte del diseño publicado, así que cambiarla nunca marca el flujo de trabajo como modificado.

## Eliminar un flujo de trabajo {#deleting-a-workflow}

Al eliminar un flujo de trabajo también se eliminan sus plantillas de tareas, su versión publicada y su sesión de diseño. Las [ejecuciones](./workflow-executions.md) existentes se conservan: cada una tiene su propia instantánea, de modo que el historial de una ejecución sigue pudiendo leerse después de que desaparezca el flujo de trabajo del que procede.
