---
title: Gateway y proxy MCP
sidebar_position: 6
---

# Gateway y proxy MCP

El agente nunca habla directamente con un [servidor MCP](../guides/mcp-servers.md) registrado. Cada llamada pasa por dos elementos propios de A2Flow, que responden a dos preguntas distintas:

| | Gateway MCP | Proxy MCP |
|---|---|---|
| **Dónde se ejecuta** | Dentro del proceso del agente, junto a la base de datos | En un contenedor aparte, sin ninguno de los secretos del agente |
| **Qué resuelve** | *Si* una llamada puede producirse | *Dónde* se produce: inicia el servidor o se conecta a él |
| **Qué contiene** | La identidad, la cadena de políticas, los mocks de herramientas, la expansión de secretos y el registro de auditoría | Una llamada cada vez: la dirección o el comando del servidor, los valores expandidos, la herramienta y sus argumentos |

Quien decide es el gateway, y la mayor parte de esta página trata de él. El proxy es el sandbox al que se entregan esas decisiones; tiene su propia sección [más abajo](#the-sandbox).

## Qué decide el gateway {#what-the-gateway-decides}

![Diagrama de flujo de la cadena de políticas que decide una llamada a una herramienta: las llamadas denegadas se rechazan indicando lo que está permitido, las permitidas se responden desde un mock o pasan por la inyección de credenciales y el proxy MCP hasta el servidor MCP, y tanto un rechazo como una llamada real generan un registro de auditoría.](./img/mcp-gateway-and-proxy-policy-chain.svg#gh-light-mode-only)
![Diagrama de flujo de la cadena de políticas que decide una llamada a una herramienta: las llamadas denegadas se rechazan indicando lo que está permitido, las permitidas se responden desde un mock o pasan por la inyección de credenciales y el proxy MCP hasta el servidor MCP, y tanto un rechazo como una llamada real generan un registro de auditoría.](./img/mcp-gateway-and-proxy-policy-chain-dark.svg#gh-dark-mode-only)

| El gateway se encarga de | Qué hace |
|---|---|
| **Identidad** | Establece a qué tenant y a qué ejecución pertenece una llamada, a partir de la conversación por la que llegó |
| **Autorización** | Consulta una cadena ordenada de políticas, cualquiera de las cuales puede vetarla |
| **Simulación** | Responde desde un [mock de herramienta](#tool-mocks-and-dry-runs) cuando la ejecución tiene uno para esa herramienta |
| **Credenciales** | Expande las referencias a [secretos](./secrets.md) del servidor registrado en una conexión, solo en el momento de conectar |
| **Aislamiento** | Entrega la llamada permitida al [proxy MCP](#the-sandbox), que es quien ejecuta realmente el servidor |

## El proxy MCP: donde se ejecuta un servidor registrado {#the-sandbox}

Un servidor MCP que registras no es código de A2Flow. Uno local es un programa que A2Flow inicia en tu nombre; uno remoto es un servicio al que A2Flow se conecta. En ambos casos, lo que haga queda fuera del control de A2Flow una vez en marcha.

Por eso no se ejecuta donde están los secretos propios de A2Flow. El proxy es un sandbox: en un despliegue con Docker Compose es el **contenedor independiente `mcp-proxy`**, que no contiene nada de lo siguiente:

| Lo que no está en el proxy | Dónde se queda |
|---|---|
| La base de datos y todo lo registrado en ella | Con el agente |
| La clave con la que se cifran los [secretos](./secrets.md) | Con el agente |
| Las credenciales de un almacén de secretos externo | Con el agente |
| La clave de API del proveedor de LLM | Con el agente |
| Los repositorios de [skills de agente](../guides/agent-skills.md) | Con el agente |

Lo que recibe el proxy es una llamada cada vez: la dirección o el comando del único servidor al que se llega, los valores que ese servidor necesita, ya expandidos a partir de tus referencias a secretos, y la herramienta y sus argumentos. No hay nada más que encontrar.

![Diagrama de arquitectura que muestra el gateway MCP, que decide si una llamada se permite, si se simula y qué credenciales necesita, entregando exactamente una llamada autorizada a través de un límite de confianza al proxy MCP, que inicia el servidor MCP real o se conecta a él.](./img/mcp-gateway-and-proxy-trust-boundary.svg#gh-light-mode-only)
![Diagrama de arquitectura que muestra el gateway MCP, que decide si una llamada se permite, si se simula y qué credenciales necesita, entregando exactamente una llamada autorizada a través de un límite de confianza al proxy MCP, que inicia el servidor MCP real o se conecta a él.](./img/mcp-gateway-and-proxy-trust-boundary-dark.svg#gh-dark-mode-only)

**Los dos extremos se demuestran mutuamente quiénes son.** El canal entre ellos está cifrado y ninguno de los dos acepta a un interlocutor sin identificar: el proxy rechaza cualquier conexión de quien no tenga un certificado emitido por este despliegue. Además, cada llamada individual lleva el [certificado](#who-authorized-a-call) de la tarea que la hace, y el proxy vuelve a comprobarlo antes de llegar a nada: que se emitió aquí, que no ha caducado, que pertenece a quien llama y que cubre exactamente esta herramienta.

**Una llamada puede hacer una pregunta por el camino.** Un servidor MCP puede detenerse a mitad de una llamada para pedir una [confirmación](../guides/workflow-executions.md#mcp-server-confirmations) a la persona que está detrás de la ejecución. Quien sabe quién es esa persona es el gateway, así que el proxy le devuelve la pregunta por la propia conexión de la llamada, y la respuesta regresa por esa misma conexión hasta el servidor que espera. Nada de una llamada sobrevive a su conexión, de modo que el proxy puede ejecutarse en cualquier número de contenedores.

Esa segunda comprobación no responde a la misma pregunta que la primera. Ser A2Flow no significa estar autorizado para llamar a una herramienta concreta, y tener el certificado de una tarea no significa que la solicitud sea la que envió A2Flow. Ambas cosas deben cumplirse, de modo que una solicitud no puede conservar una autorización válida mientras apunta discretamente el proxy a otro programa.

Hay una llamada que no lleva certificado de tarea: una [ejecución de prueba](../guides/mcp-servers.md#testing-a-script) de un script desde el formulario del servidor MCP, que no tiene ninguna tarea detrás. El proxy solo la acepta para un script, nunca para un comando arbitrario ni para un servidor remoto, y cargar la lista de herramientas de un script ya ejecuta el script completo con la misma comprobación exclusiva de A2Flow, así que esto no deja pasar nada nuevo.

El proxy es una segunda línea, no quien decide. Si la tarea sigue en marcha, si la aprobación sigue vigente, si el certificado se retiró: nada de eso se puede responder allí, y todo se queda en el gateway.

## Cada arranque en su propio sandbox {#per-launch-sandbox}

El proxy mantiene los servidores registrados lejos de A2Flow. También los mantiene lejos **unos de otros**. Los servidores de todos los tenants se inician en el mismo proxy, y algunos son scripts que ha escrito el propio tenant; por eso cada servidor que inicia el proxy queda sellado en su propio sandbox, creado para esa única llamada y destruido cuando termina.

| Dentro del sandbox | Qué impide |
|---|---|
| El servidor solo ve sus propios procesos | Leer los valores secretos entregados a cualquier otro servidor que se esté ejecutando a la vez |
| El sistema y los programas propios de A2Flow son de solo lectura | Alterar lo que un servidor posterior, por ejemplo de otro tenant, ejecuta en su siguiente arranque |
| Su directorio personal, donde se guardan los paquetes descargados, pertenece solo a su tenant | Que un servidor use un paquete que otro tenant haya colocado ahí |
| Todo lo que hay dentro termina cuando termina la llamada | Que un proceso se quede después de la llamada para observar las siguientes |
| Las credenciales propias del proxy no están ahí en absoluto | Hacerse pasar por el proxy ante cualquiera |

Un servidor remoto, al que el proxy solo se conecta, no ejecuta nada en el proxy y, por tanto, no necesita sandbox.

El aislamiento se basa en [bubblewrap](https://github.com/containers/bubblewrap), la herramienta de sandbox de Linux que usa Flatpak. El proxy comprueba al arrancar que puede crear un sandbox y se niega a arrancar si no puede: nunca recurre a ejecutar un servidor sin sandbox. Consulta [Despliegue](../operations/deployment.md#process-layout) para saber qué exige esto del host.

## La cadena de políticas {#the-policy-chain}

| Orden | Política | Qué exige |
|---|---|---|
| 1 | **Vinculación a una tarea en curso** | El par `(server, tool)` debe estar vinculado a una tarea que esté `en curso` y asignada a la sesión que llama; una tarea en la que trabaje otra sesión de la ejecución no cuenta. Listar lo que ofrece un servidor no es una llamada, así que esta regla no se le aplica: el agente de diseño lista para decidir qué vincular, limitado a los servidores que el diseñador puede ver según las [etiquetas de control de acceso](../guides/tags.md), mientras que el listado propio de una ejecución no se limita por etiquetas |
| 2 | **Certificado de herramienta** | La llamada debe presentar el certificado de la tarea (consulta [Quién autorizó una llamada](#who-authorized-a-call)) y la concesión firmada de ese certificado debe cubrir la herramienta. No hay exención: una tarea que ninguna aprobación cubre presenta la concesión que tiene el iniciador de su ejecución |
| 3 | **Llamada aprobada** | Cuando lo que autoriza la tarea es la decisión de un aprobador, la llamada debe coincidir con las llamadas que incluyó esa decisión; consulta [Las llamadas que cubre una decisión](./approvals.md#the-calls-a-decision-covers). Una herramienta que la decisión incluyó con cualquier entrada supera esta regla lleve lo que lleve, porque la regla 2 ya la detuvo hasta que se concedió la decisión. Una tarea que se ejecuta con la concesión de su propio iniciador no tiene esa lista y aquí no se comprueba |

La cadena se detiene en el primer veto y se ordena de menor a mayor coste, de modo que una llamada que ya incumple la regla de vinculación nunca paga por una comprobación de firma. La última regla va al final también por otro motivo: es la única que necesita saber *qué* tarea llama, y la regla anterior es la que lo establece. Además, impide que quien llama sin ninguna autoridad averigüe lo que aceptó un aprobador. Añadir una regla significa añadir una política a la cadena, no editar el gateway, y eso es lo que permite que «qué se puede ejecutar» se lea como una única lista ordenada.

Los rechazos se redactan para quien llama, no para un registro: una llamada denegada regresa indicando las herramientas que *sí* están permitidas, para que el modelo pueda corregirse en lugar de adivinar.

## Quién autorizó una llamada {#who-authorized-a-call}

Cada llamada a una herramienta que hace una ejecución lleva un **certificado** que nombra a la persona con cuya autoridad se ejecuta. Una tarea recibe uno cuando se marca como **en curso**; de quién es la autoridad que lleva depende de si la cubre una [aprobación](./approvals.md).

| La tarea | Recibe su certificado | Con la autoridad de |
|---|---|---|
| Está cubierta por una aprobación, propia o solicitada en una tarea a la que sigue | Al iniciarse, y solo una vez concedida esa aprobación | El aprobador que la concedió |
| No está cubierta por ninguna | Cuando se marca como **en curso** | Quien inició la ejecución |

La segunda fila es el caso habitual: a nadie se le pidió valorar la tarea, así que la persona que ejecutó el flujo de trabajo autoriza las herramientas que vincula, y el registro de auditoría lo hace constar expresamente en lugar de dejar la llamada sin atribuir.

De aquí se derivan tres reglas, todas visibles para quien opera un flujo de trabajo:

- **Las herramientas quedan fijadas al iniciarse la tarea.** Un certificado cubre exactamente las herramientas vinculadas a la tarea en ese momento. Un flujo de trabajo que vincula una herramienta a una tarea solo después de que esta haya empezado verá esa herramienta rechazada; al agente de diseño se le indica que vincule primero, pero una tarea editada a mano aún puede equivocarse en esto. Las herramientas de una tarea cubierta por una aprobación no se pueden editar en absoluto.
- **Pedir una aprobación vuelve a cerrar la puerta.** Si se solicita una aprobación que cubre una tarea ya en marcha con la autoridad de alguien, esa autoridad se retira de inmediato; la tarea espera la decisión como cualquier otra.
- **Cada tarea cubierta recibe su propio certificado.** Una aprobación que cubre una cadena de tareas no las somete a todas al mismo reloj: cada una recibe el suyo al iniciarse.

## Qué se registra {#what-is-recorded}

| Se registra por cada llamada decidida | Deliberadamente no se registra |
|---|---|
| La herramienta, el servidor y si se permitió o se denegó | Los argumentos en sí: solo se conserva un resumen criptográfico de ellos |
| El motivo del rechazo, cuando se deniega; para una llamada fuera de lo aprobado, la entrada en cuestión y el límite que aceptó el aprobador | El valor real de la entrada rechazada |
| El certificado presentado y, por tanto, quién autorizó la llamada | |

Ese registro es la página Invocaciones de herramientas de la ejecución, y es lo que permite responder a posteriori a «quién autorizó esta llamada». Los propios certificados se enumeran en **Registros de auditoría → Certificados**, con una fila por concesión.

## Mocks de herramientas y ejecuciones de ensayo {#tool-mocks-and-dry-runs}

Un [mock de herramienta](../guides/tool-mocks.md) permite probar de principio a fin un flujo de trabajo en **borrador** sin los efectos secundarios de sus herramientas. Lo que importa aquí es *dónde* se sitúa la simulación.

![Diagrama de flujo que muestra que un mock de herramienta solo se consulta después de la misma cadena de políticas que afronta una llamada de producción: una llamada denegada se rechaza exactamente igual que en producción, y una permitida se responde con la siguiente respuesta de un mock o desde el servidor MCP real.](./img/mcp-gateway-and-proxy-tool-mocks.svg#gh-light-mode-only)
![Diagrama de flujo que muestra que un mock de herramienta solo se consulta después de la misma cadena de políticas que afronta una llamada de producción: una llamada denegada se rechaza exactamente igual que en producción, y una permitida se responde con la siguiente respuesta de un mock o desde el servidor MCP real.](./img/mcp-gateway-and-proxy-tool-mocks-dark.svg#gh-dark-mode-only)

La simulación se consulta **después** de la cadena de políticas, nunca antes. Por eso, una ejecución de ensayo reproduce la misma autorización que afronta una ejecución real: la herramienta debe seguir vinculada a una tarea en curso y la llamada debe seguir presentando el certificado de esa tarea. Lo único que omite un mock es la parte que tiene un efecto fuera de A2Flow: nunca se llega al proxy.

Conviene conocer dos consecuencias:

- **Las respuestas siguen el recuento de llamadas.** La primera respuesta contesta a la primera llamada de la ejecución a esa herramienta, la segunda a la segunda, y la última se repite cuando se acaba la lista. El contador pertenece a la ejecución, así que sobrevive a las muchas solicitudes (y a las posibles réplicas) que abarca una ejecución del agente.
- **Una llamada simulada no deja registro de auditoría.** Ese registro es para las llamadas que llegaron a un servidor real o que se detuvieron de camino a él; una fila para una llamada que de todos modos iba a responderse desde una instantánea induciría a error en ambos sentidos. Una llamada simulada se inspecciona en la transcripción del chat, con la insignia `Simulado`.
