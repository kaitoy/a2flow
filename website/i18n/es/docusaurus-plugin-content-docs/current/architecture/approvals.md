---
title: Barrera de aprobación
sidebar_position: 5
---

# Barrera de aprobación

Una [aprobación](../guides/approvals.md) hace dos cosas a la vez. Detiene una ejecución en un paso hasta que una persona decide, y convierte esa decisión en una concesión firmada que dice exactamente qué pueden hacer después los pasos que cubre.

![Diagrama de secuencia de una aprobación: el agente de ejecución solicita la aprobación, A2Flow notifica al aprobador mientras los pasos cubiertos siguen bloqueados, el aprobador decide y A2Flow concede un certificado a cada paso cubierto cuando se inicia y deja que la ejecución continúe.](./img/approvals-sequence.svg#gh-light-mode-only)
![Diagrama de secuencia de una aprobación: el agente de ejecución solicita la aprobación, A2Flow notifica al aprobador mientras los pasos cubiertos siguen bloqueados, el aprobador decide y A2Flow concede un certificado a cada paso cubierto cuando se inicia y deja que la ejecución continúe.](./img/approvals-sequence-dark.svg#gh-dark-mode-only)

## Qué significa «bloqueado» {#what-blocked-means}

La pausa no es el agente esperando educadamente.

| Mientras una aprobación está sin decidir | |
|---|---|
| Qué pueden llamar los pasos cubiertos | Ninguna de sus herramientas MCP vinculadas: la llamada se rechaza antes de llegar a un servidor |
| Quién lo hace cumplir | El [gateway](./mcp-gateway-and-proxy.md), como una regla que comprueba; no una frase en las instrucciones del agente |
| Qué activa la barrera | La *existencia* de una aprobación que cubre el paso. Una pendiente y una rechazada bloquean por igual, así que la barrera falla en modo cerrado |
| Qué no se ve afectado | Los pasos que ninguna aprobación cubre: siguen ejecutándose con la regla normal de vinculación de herramientas |

Por tanto, ni una inyección de prompt ni un error pueden sortear la barrera con palabras, porque no hay nada a lo que persuadir. Lo único que la abre es una decisión registrada en la aprobación.

## El certificado {#the-certificate}

A cada paso que cubre una aprobación se le concede, al iniciarse, un certificado de corta duración firmado por una autoridad de certificación que el despliegue genera por sí mismo en el primer uso.

El certificado no es lo que añade una aprobación: **todos** los pasos que llaman a una herramienta tienen uno. Lo que cambia una aprobación es de quién procede: a un paso que a nadie se le pidió aprobar se le concede uno con la autoridad de quien inició la ejecución, y una aprobación la sustituye por la del propio aprobador. Así, la pregunta que responde el registro nunca es «¿estaba autorizada esta llamada?», sino «¿quién la autorizó?».

| El certificado contiene | Por qué importa |
|---|---|
| A qué tenant, ejecución y paso corresponde, y de quién es la autoridad que lleva: la de un aprobador o la del iniciador de la ejecución | Un certificado emitido para una ejecución no sirve en otra, y un tipo de autoridad no puede sustituir al otro |
| **Las herramientas que el paso tenía vinculadas en el momento de iniciarse** | Los pasos de una ejecución y sus herramientas quedan fijados al ejecutar a partir del diseño publicado del flujo de trabajo, el certificado vuelve a congelarlos al emitirse, y las herramientas de un paso cubierto ya no se pueden editar en absoluto, de modo que ni el agente ni un cambio posterior pueden ampliar una concesión. Aprobar que un paso lea un archivo nunca se convierte en aprobar que lo elimine |

### Las llamadas que cubre una decisión {#the-calls-a-decision-covers}

El certificado responde a *qué herramienta*, nunca a *con qué se llama*, y las entradas suelen ser donde están las consecuencias. Por eso la solicitud lleva una segunda cosa que el certificado no lleva: las llamadas que autoriza, cada una de las cuales nombra una herramienta y limita los valores que pueden tomar sus entradas. Se registra al hacer la solicitud, se muestra al aprobador antes de que decida y nadie puede editarla después, ni siquiera el agente.

A partir de ahí, cada llamada que pasa por el proxy se somete a ella, además de al certificado:

| Qué se comprueba | Se rechaza cuando |
|---|---|
| La herramienta | La decisión no la incluye, aunque el certificado la conceda |
| Cada entrada proporcionada | La decisión no la nombra: es una entrada que el aprobador nunca vio |
| Cada entrada que nombra la decisión | Falta, salvo que la decisión la haya marcado como opcional |
| Cada valor | Queda fuera del límite que aceptó el aprobador |

Un paso en el que se unen dos ramas aprobadas debe cumplir **ambas** decisiones, por la misma razón por la que necesita las dos desde el principio: el aprobador más permisivo no habla por el otro. Cuando las dos discrepan sobre si una herramienta necesita que se aprueben sus entradas, decide la más estricta.

Una herramienta que el diseño del flujo de trabajo marcó como de solo lectura también se incluye, como **Cualquier entrada**, en lugar de omitirse. La decisión sigue siendo el relato completo de lo que autoriza, de modo que el aprobador puede ver qué herramientas quedaron sin límite, y la barrera tiene una sola lista que consultar en lugar de una segunda regla que vuelva a leer las herramientas del paso. Solo la ruta de solicitud escribe una entrada de este tipo; un agente que intente declararla por su cuenta es rechazado.

Un paso que se ejecuta con la propia autoridad del iniciador de la ejecución no se comprueba de esta forma: no hubo aprobador y, por tanto, nada de lo que apartarse. Lo que lo limita no cambia: sus propias herramientas y la concesión firmada del certificado.

### Los pasos que cubre una aprobación {#the-steps-an-approval-covers}

Una aprobación cubre **el paso que nombra y todos los pasos siguientes, hasta la próxima aprobación**. Así, un flujo de trabajo puede poner la solicitud en un paso propio y dejar que la decisión alcance el trabajo que viene después:

![Diagrama de flujo de una cadena de cinco pasos en la que la aprobación A cubre los tres primeros pasos y la aprobación B toma el relevo a partir del cuarto, lo que muestra que una aprobación cubre el paso que nombra y todo lo que sigue hasta la próxima aprobación.](./img/approvals-step-coverage.svg#gh-light-mode-only)
![Diagrama de flujo de una cadena de cinco pasos en la que la aprobación A cubre los tres primeros pasos y la aprobación B toma el relevo a partir del cuarto, lo que muestra que una aprobación cubre el paso que nombra y todo lo que sigue hasta la próxima aprobación.](./img/approvals-step-coverage-dark.svg#gh-dark-mode-only)

La aprobación A cubre *Pedir el visto bueno*, *Lanzar la instancia* y *Etiquetar la instancia*. La aprobación B toma el relevo a partir de *Volver a preguntar*. Una solicitud nunca cubre nada anterior a ella: una aprobación solo alcanza hacia adelante.

| Situación | Qué ocurre |
|---|---|
| El paso nombrado no usa herramientas | Es correcto y habitual. La decisión la llevan los pasos siguientes |
| Un paso está detrás de dos aprobaciones en ramas distintas | Deben concederse **ambas** para que pueda actuar. Que un aprobador despeje su propia rama no le permite hablar por la del otro |
| Se solicita una segunda aprobación en un paso ya cubierto por una anterior | La solicitud más cercana toma el relevo de inmediato, y la decisión anterior deja de autorizar ese paso |
| Un paso se devuelve para rehacerlo y se vuelve a enviar | La nueva solicitud sustituye a la decisión anterior como barrera de ese paso, de modo que un rechazo no puede dejar el paso atascado para siempre |

Cada llamada posterior a una herramienta desde un paso cubierto debe presentar su certificado, y el gateway comprueba todo lo siguiente antes de que la llamada vaya a ningún sitio:

- el certificado corresponde a esta ejecución y a este paso,
- lo emitió este despliegue y no se ha revocado,
- la aprobación que lo respalda sigue cubriendo el paso, y todas las que lo cubren siguen concedidas,
- quien llama puede demostrar que el certificado es suyo y no uno copiado,
- la herramienta a la que se llama está dentro del conjunto firmado.

Un certificado se revoca cuando su paso llega a un estado final. La seguridad no depende de ello (un paso terminado ya no se está ejecutando, así que sus llamadas ya se rechazan), pero hace que el registro diga *por qué* la concesión dejó de contar y ajusta la vida de un certificado al trabajo que autorizó. Como cada paso cubierto recibe su propio certificado al iniciarse, una cadena larga de pasos no tiene que terminar dentro de la vida útil de un solo certificado; esa vida útil máxima se puede ajustar en la [referencia de configuración](../operations/configuration.md#mcp-tools-and-approvals).

## Qué responde el registro {#what-the-record-answers}

Cada llamada decidida, permitida o rechazada, se registra junto con el certificado que presentó, de modo que «quién autorizó esto y con qué base» se puede responder mucho después de que la ejecución haya terminado. Los argumentos solo se conservan como resumen criptográfico; los valores en bruto nunca se guardan. La página Invocaciones de herramientas de la ejecución es donde se consulta ese registro.

Una llamada rechazada por apartarse de la decisión registra el motivo, con el nombre de la entrada en cuestión y el límite que aceptó el aprobador, pero nunca el valor que se pasó realmente. El motivo se guarda tal cual, en el mismo registro que conserva los argumentos solo como resumen, así que citar ahí el valor rechazado volvería a introducir exactamente lo que el resumen existe para dejar fuera.

**Alcance de la garantía.** El gateway se ejecuta dentro del proceso del backend, así que un certificado demuestra la posesión ante un verificador que comparte ese proceso; no es una defensa contra un atacante que ya controla el backend. Lo que sí ofrece es un único punto de aplicación que falla en modo cerrado, una concesión que no se puede ampliar a posteriori y un registro que se puede comprobar después.
