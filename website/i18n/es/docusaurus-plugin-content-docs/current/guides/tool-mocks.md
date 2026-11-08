---
title: Mocks de herramientas
sidebar_position: 8
---

# Mocks de herramientas

Un mock de herramienta es un sustituto que permite probar de principio a fin la ejecución de un flujo de trabajo en **borrador** sin los efectos secundarios de sus herramientas. Una herramienta simulada no se llama: en su lugar se devuelve el resultado configurado en el mock, de modo que ninguna solicitud llega al servidor MCP, no se registra ninguna aprobación y no se envía ningún correo a nadie.

Abre **Mocks de herramientas** en la barra lateral de administración para gestionarlos.

![Diagrama de flujo que muestra cómo el agente llama a una herramienta, comprueba si está simulada en esta ejecución y, o bien llega al servidor MCP real, o bien recibe la siguiente respuesta del mock sin contactar con ningún servidor.](./img/tool-mocks-decision.svg#gh-light-mode-only)
![Diagrama de flujo que muestra cómo el agente llama a una herramienta, comprueba si está simulada en esta ejecución y, o bien llega al servidor MCP real, o bien recibe la siguiente respuesta del mock sin contactar con ningún servidor.](./img/tool-mocks-decision-dark.svg#gh-dark-mode-only)

## Cómo usar uno {#using-one}

1. Crea un mock para la herramienta que quieras sustituir.
2. Haz clic en **Ejecutar** en un flujo de trabajo en **borrador**, o en uno `modificado`, eligiendo **Ediciones sin publicar** en el cuadro de diálogo. En **Herramientas simuladas**, el cuadro de diálogo enumera los mocks que sustituyen a una herramienta usada por alguna de las tareas de este flujo de trabajo, junto con todos los mocks de herramientas integradas.
3. Marca los que deba usar esta ejecución e iníciala.

Un mock de una herramienta que no usa ninguna tarea de este flujo de trabajo queda fuera de la lista; vincula primero esa herramienta a una tarea. Los mocks solo se ofrecen en una [ejecución de prueba](./workflows.md#trying-the-edits-out): el cuadro de diálogo no ofrece ninguno al ejecutar un diseño publicado, y si se pide uno de todos modos, se rechaza. Al iniciar la ejecución se **copia** en ella lo que indica en ese momento cada mock elegido, de modo que editar o eliminar un mock después nunca cambia una ejecución ya en curso, ni puede convertir sin avisar una llamada simulada en una real.

La simulación se elige **por herramienta**, no por ejecución, porque un ensayo solo es útil si sigue siendo realista. Un flujo de trabajo que busca en un sistema y luego escribe en él puede simular únicamente la escritura: la lectura sigue llegando al servidor real, y el agente sigue razonando sobre datos reales.

## Qué contiene un mock {#what-a-mock-holds}

| Campo | Notas |
|---|---|
| **Nombre** / **Descripción** | Cómo lo reconoces en el cuadro de diálogo de ejecución. |
| **Destino** | O bien una herramienta de un [servidor MCP registrado](./mcp-servers.md) (elige **Seleccionar servidor MCP**, selecciona el servidor y luego elige su **Nombre de la herramienta** en la lista cargada desde ese servidor), o bien una herramienta **integrada** de A2Flow. |
| **Respuestas** | Una lista ordenada, indexada por el número de orden de la llamada. |

La única herramienta integrada que se puede simular por ahora es `request_approval`: aquella cuyos efectos secundarios, de otro modo, necesitan que una persona dé el visto bueno para que la ejecución pueda continuar.

### Qué devuelve la herramienta {#what-the-tool-returns}

Una vez elegida la herramienta, debajo se abre **Formato de salida**, que muestra la descripción de la propia herramienta y la forma que declara devolver. Úsalo como referencia para lo que escribas a continuación: un mock solo es útil si el flujo de trabajo puede leerlo como leería el resultado real.

No todas las herramientas indican lo que devuelven. Cuando una no lo hace, el panel lo señala y deja la forma a tu criterio.

### Respuestas {#responses}

La primera respuesta contesta a la primera llamada de la ejecución a esa herramienta, la segunda a la segunda, y así sucesivamente. Cuando la lista se agota, se repite la última respuesta, de modo que una sola respuesta se comporta como una constante. Eso es lo que permite que un mock exprese un *escenario* en lugar de un valor fijo: aprobar la primera solicitud, rechazar la segunda y ver cómo gestiona ambas el flujo de trabajo.

| Clase | Significado |
|---|---|
| Estructurado (objeto JSON) | Un objeto JSON que se coloca en el contenido estructurado del resultado; para una herramienta cuyo llamante lee campos del resultado |
| Texto | Una cadena que se coloca en el contenido textual del resultado |
| Error | Un mensaje que se devuelve como una llamada fallida, de modo que el agente ve que la herramienta informa de un error |

Cuando la herramienta declara un formato de salida, una respuesta **Estructurado (objeto JSON)** ofrece **Insertar desde el esquema**: rellena el cuadro con esa forma, incluidas las claves, para que edites los valores en lugar de transcribir la estructura. Sustituye lo que haya en el cuadro, y pregunta antes si ya has escrito algo en él.

## Etiquetas {#tags}

El formulario de creación y la página de detalle de un mock de herramienta incluyen un selector **Etiquetas**, y la lista tiene una columna **Etiquetas** por la que se puede filtrar. Las etiquetas son el mismo vocabulario de todo el tenant que comparten los secretos, los servidores MCP y los demás catálogos etiquetables; consulta [Etiquetas](./tags.md) para saber cómo adjuntarlas y filtrar por ellas.

## Lo que un mock no se salta {#what-a-mock-does-not-skip}

Un mock evita el efecto secundario, no las reglas. Una llamada simulada se sigue comprobando con las herramientas que la tarea actual de la ejecución puede usar y con cualquier [aprobación](./approvals.md) que esa tarea esté esperando, de modo que un flujo de trabajo que se rechazaría en producción también se rechaza en su ensayo. También se comprueba con las **entradas** que esa aprobación permitió, de modo que un ensayo detecta una llamada que el aprobador no habría autorizado en lugar de dejarla pasar sin más. Una solicitud de aprobación simulada sigue validando su destino y las llamadas que declara, de modo que un flujo de trabajo que nombra a un aprobador no apto, o que declara llamadas que no coinciden con las que harían sus pasos, falla en un ensayo exactamente igual que en una ejecución real.

## Ver qué hizo una llamada simulada {#seeing-what-a-mocked-call-did}

Las llamadas simuladas se inspeccionan en la transcripción del chat de la ejecución: su línea de herramienta se despliega para mostrar los argumentos y el resultado, con la insignia **Simulado**. A propósito, no aparece en la página [Invocaciones de herramientas](./workflow-executions.md#tool-invocations) de la ejecución: esa página registra las decisiones que tomó realmente el gateway MCP, y una llamada simulada nunca llega a él. La propia ejecución lleva la insignia **Simulado** en la [lista de ejecuciones](./workflow-executions.md).
