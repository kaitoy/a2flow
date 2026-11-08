---
title: Servidores MCP
sidebar_position: 7
---

# Servidores MCP

Un servidor [MCP](https://modelcontextprotocol.io/) proporciona herramientas que el agente puede llamar. Este es su catálogo: registra aquí un servidor y podrás vincular sus herramientas a las plantillas de tareas de un flujo de trabajo; consulta [Herramientas MCP para las tareas](./workflows.md#mcp-tools-for-tasks).

Abre **Servidores MCP** en la barra lateral de administración para gestionar el catálogo. Cada registro tiene un **Nombre** único, una **Descripción** opcional, sus [etiquetas](./tags.md) y un **Transporte** que determina el resto del formulario.

## Transportes {#transports}

| Transporte | Campos | Qué es |
|---|---|---|
| **Streamable HTTP** (predeterminado) | **URL**, **Encabezados HTTP** | Un servidor remoto. Los encabezados se envían con cada solicitud; lo habitual es `Authorization: Bearer …`. Los servidores que solo admiten SSE no son compatibles. |
| **stdio** | **Comando**, **Argumentos**, **Variables de entorno** | Un servidor que se inicia como proceso hijo del backend, por ejemplo `npx` con `["-y", "@modelcontextprotocol/server-everything"]`. Tanto `npx` como `uvx` están disponibles. |
| **Script** | **Idioma**, **Fuente**, **Paquetes**, **Variables de entorno** | Código Python o JavaScript que escribes tú. Cada una de sus funciones públicas se convierte en una herramienta; consulta [Escribir un script](#writing-a-script). |

Al cambiar el transporte de un servidor existente se borran los campos del transporte anterior, y se rechaza cualquier registro que mezcle formatos: una URL en un servidor stdio, un comando en uno remoto o código fuente en cualquiera de los dos.

⚠️ **Registrar un servidor stdio significa ejecutar el comando elegido dentro del contenedor del backend**, con el usuario sin privilegios del contenedor. Requiere el mismo rol de desarrollador que cualquier otra escritura en servidores MCP. Los argumentos se pasan al proceso como una lista, nunca a través de un shell, y el proceso hijo hereda únicamente un pequeño conjunto seguro de variables de entorno más las que configures: las claves de API y la URL de la base de datos del propio backend quedan fuera de su alcance.

## Escribir un script {#writing-a-script}

Un servidor de script convierte en herramientas las funciones que escribes, sin necesidad de publicar un paquete. Elige **Script** como **Transporte**, selecciona un **Idioma** y pega el código en **Fuente**.

**Fuente** es un editor de código. Colorea el código según el **Idioma** seleccionado, numera las líneas y aplica sangría con **Tab**; para pasar al campo siguiente con **Tab**, pulsa antes **Esc**. Mientras escribes, subraya los problemas en el propio texto; pasa el cursor sobre un subrayado para leer qué ocurre.

| Subrayado | Significado | Ejemplos |
|---|---|---|
| Rojo, ondulado | Error de sintaxis: el script no puede ejecutarse | Un corchete sin cerrar, una palabra clave mal escrita |
| Ámbar, ondulado | Probablemente un error | Ninguna función se convertiría en herramienta; una función de Python sin docstring o un parámetro sin anotación de tipo; una importación de fuera de la biblioteca estándar con **Paquetes** vacío; una función de JavaScript sin `description` |
| Color de acento, ondulado | Una nota | Una función de JavaScript sin `inputSchema` |

Los subrayados son consejos y nunca te impiden guardar; la comprobación al guardar se describe más abajo.

| | Python | JavaScript |
|---|---|---|
| Funciones que se convierten en herramientas | Todas las funciones definidas en el nivel superior cuyo nombre no empiece por `_`. Las funciones importadas no se exponen. | Todas las funciones exportadas (`export function`, `export async function`) cuyo nombre no empiece por `_`. La exportación predeterminada no se expone. |
| Nombre de la herramienta | El nombre de la función | El nombre de la exportación |
| Descripción | El docstring | La propiedad `description` de la función |
| Argumentos | Se leen de las anotaciones de tipo: `str`, `int`, `float`, `bool`, `list`, `dict`, `Literal[...]` y `X \| None`. Un parámetro con cualquier otro tipo, o sin ninguno, acepta cualquier valor. | La propiedad `inputSchema` de la función, un JSON Schema. Sin ella, la herramienta acepta cualquier argumento. |
| Cómo se llama a la herramienta | Argumentos por nombre | Un objeto que contiene los argumentos |
| Qué recibe el agente | El valor devuelto: una cadena tal cual; cualquier otra cosa, como JSON | El valor devuelto: una cadena tal cual; cualquier otra cosa, como JSON |

```python
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

```js
export function add({ a, b }) {
  return a + b;
}
add.description = "Add two numbers.";
add.inputSchema = {
  type: "object",
  properties: { a: { type: "number" }, b: { type: "number" } },
  required: ["a", "b"],
};
```

Algunas reglas se aplican a ambos lenguajes:

- La biblioteca estándar siempre está disponible: los módulos propios de Python o los módulos `node:` integrados de Node.js. Todo lo demás debe figurar en [Paquetes](#adding-packages).
- Un error lanzado por una función llega al agente como una llamada a herramienta fallida, junto con su mensaje.
- La salida de `print()` o `console.log()` va al registro del servidor, no al agente.
- Las **Variables de entorno** se leen como `os.environ["NAME"]` o `process.env.NAME`, y pueden usar los marcadores de posición descritos en [Mantener las credenciales fuera del registro](#keeping-credentials-out-of-the-record).
- **Fuente** admite un máximo de 30.000 caracteres.
- El código Python con un error de sintaxis se rechaza al guardar, con el número de línea. JavaScript no se comprueba al guardar: [pruébalo](#testing-a-script) antes de guardar para detectar un script que no se puede cargar.
- Un script que no consigue cargarse (por un paquete que no se instala, un error de sintaxis o un error lanzado en su nivel superior) se inicia igualmente. Todas las llamadas a sus herramientas fallan con el error que lo detuvo, y al [comprobar sus herramientas](#checking-a-servers-tools) el servidor aparece como inutilizable.

⚠️ Un script se ejecuta en el mismo lugar que un servidor stdio, con las mismas restricciones.

### Añadir paquetes {#adding-packages}

Un script que se comunica con otro servicio suele necesitar la biblioteca cliente de ese servicio: `boto3` para AWS, por ejemplo. Indica cada una en **Paquetes**, una por fila, e impórtala en **Fuente** como de costumbre.

| Idioma | Cómo escribir un paquete | Ejemplos |
|---|---|---|
| Python | Un nombre de PyPI, opcionalmente con una versión | `boto3`, `boto3==1.40.0`, `requests>=2.32` |
| JavaScript | Un nombre del registro de npm, opcionalmente con `@versión` | `is-number`, `@aws-sdk/client-s3@3` |

```python
import boto3


def list_buckets() -> list[str]:
    """List the S3 buckets the configured credentials can see."""
    return [b["Name"] for b in boto3.client("s3").list_buckets()["Buckets"]]
```

- Los paquetes se instalan la primera vez que el script se inicia con esa lista, lo que puede tardar un poco; los inicios posteriores reutilizan la copia instalada. Los scripts que indican exactamente los mismos paquetes comparten una misma copia.
- Un paquete que no se puede instalar (un nombre mal escrito, una versión que no existe) impide que el script se cargue. [Cargar herramientas](#testing-a-script) muestra el error del instalador.
- Un servidor admite un máximo de 20 paquetes, cada uno de hasta 200 caracteres y empezando por una letra, un dígito o `@`.
- Para instalar es necesario poder acceder al registro de paquetes desde donde se ejecutan los scripts. Para instalar desde un índice privado, define la variable propia del instalador en **Variables de entorno**: `UV_INDEX_URL` para Python, `NPM_CONFIG_REGISTRY` para JavaScript.

## Probar un script {#testing-a-script}

El panel **Ejecución de prueba**, situado bajo **Variables de entorno**, ejecuta el script tal como está en el formulario, sin guardarlo. Úsalo para detectar un script que no se carga antes de que un agente intente utilizarlo.

1. Haz clic en **Cargar herramientas**. El script se inicia con los valores de **Fuente**, **Paquetes** y **Variables de entorno** que haya en ese momento en el formulario.
2. Elige una herramienta en **Herramienta**. **Argumentos** se rellena con todos los argumentos que declara la herramienta, cada uno con el valor `null`.
3. Edita **Argumentos** (un objeto JSON) y haz clic en **Ejecutar**.

| Lo que ves | Significado |
|---|---|
| Una lista de herramientas | El script se ha cargado; estas son las herramientas que expondrá |
| Texto rojo en lugar de la lista de herramientas | El script no se ha podido cargar. El texto es el error que lo detuvo |
| **Este script no expone ninguna herramienta.** | El script se ha cargado, pero ninguna función se convertiría en herramienta |
| La salida de la herramienta en **Salida** | La llamada ha funcionado |
| Texto rojo en **Salida** | La herramienta ha lanzado un error; el texto es su mensaje |
| **Los argumentos deben ser un objeto JSON.** o **JSON no válido: …** | **Argumentos** no es un objeto JSON; no se ha ejecutado nada |

Los marcadores de posición de **Variables de entorno** se expanden igual que en un servidor guardado, de modo que una ejecución de prueba accede a los mismos servicios con las mismas credenciales. Una ejecución de prueba es una llamada real: lo que haga la herramienta, ocurre de verdad.

## Mantener las credenciales fuera del registro {#keeping-credentials-out-of-the-record}

⚠️ Los valores literales de encabezados y variables de entorno se almacenan **en texto sin cifrar** y se vuelven a mostrar en la página de detalle. En lugar de escribir una credencial directamente, haz referencia a una entrada de un [secreto](./secrets.md) registrado:

| Marcador de posición | Dónde funciona | Ejemplo |
|---|---|---|
| `${secret:name/key}` | Cualquier valor de encabezado o de variable de entorno | `Authorization: Bearer ${secret:github/token}`<br/>`AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}` |
| `${gcp-token:name/key}` | Igual que `${secret:…}`, para una entrada que contiene un JSON de credenciales de Google Cloud | `Authorization: Bearer ${gcp-token:gcp-credentials/GOOGLE_CREDENTIALS_JSON}` |
| `${env:NAME}` | Un elemento de **Argumentos**, que nombra una de las variables de entorno de este mismo servidor | `--token ${env:API_KEY}` |

Los marcadores de posición se expanden solo en el momento de conectar, por lo que la credencial nunca aparece en el registro almacenado.

`${env:NAME}` se expande después del propio `${secret:…}` de esa variable de entorno, lo que permite reutilizar un valor procedente de un secreto como opción de línea de comandos, para un lanzador que lo espera como argumento en lugar de leerlo del entorno del proceso. `NAME` debe ser una clave de **Variables de entorno**; se rechaza al guardar cualquier referencia a una clave que no exista, incluida la que queda huérfana al eliminar esa clave.

### Servidores MCP de Google Cloud {#google-cloud-mcp-servers}

Los servidores MCP administrados de Google, como el de GKE, no aceptan claves de API. Cada solicitud debe llevar un token de acceso OAuth 2.0 de una identidad de Google Cloud, y como un token solo dura una hora, tampoco se puede pegar en un secreto. `${gcp-token:name/key}` resuelve el problema: en lugar del valor de la entrada, se expande a un **token de acceso nuevo emitido a partir de él**, que se renueva automáticamente al caducar. La entrada contiene el JSON de credenciales, en uno de estos dos formatos:

| Credencial | Cómo obtenerla | Ámbito del token |
|---|---|---|
| Una **clave de cuenta de servicio** | Crea una cuenta de servicio, concédele **MCP Tool User** y lo que necesiten sus herramientas, y descarga una clave JSON | `cloud-platform` |
| Un **ID de cliente y secreto de OAuth** | Crea un cliente OAuth (aplicación de escritorio), descarga su JSON, ejecuta una vez en tu propio equipo `gcloud auth application-default login --client-id-file=<ese JSON> --scopes=https://www.googleapis.com/auth/cloud-platform` e inicia sesión. Pega el contenido del archivo `application_default_credentials.json` resultante | Lo que hayas autorizado |

En ambos casos, pega el JSON completo como una entrada de un [secreto](./secrets.md) y haz referencia a él desde el encabezado `Authorization` del servidor, como en el ejemplo anterior. Todas las llamadas a herramientas se ejecutan con esa única identidad, sea quien sea quien haya iniciado el flujo de trabajo. Una credencial mal formada, o que Google ya no acepte, hace fallar la conexión igual que una referencia `${secret:…}` rota.

## Registrar desde el registro de MCP {#registering-from-the-mcp-registry}

El botón **Explorar el registro** de la página de lista abre un cuadro de búsqueda respaldado por el [registro de MCP](https://registry.modelcontextprotocol.io/) oficial.

1. Busca por nombre. Los resultados incluyen solo los servidores que A2Flow puede registrar: los que tienen un endpoint Streamable HTTP y los publicados como paquete de npm o PyPI que puede iniciar por stdio.
2. Elige uno. Se abre el formulario de creación con los datos de conexión ya rellenados y con las claves de encabezado o de entorno que requiere el servidor.
3. Rellena los valores secretos y guarda.

La correspondencia entre un paquete y un comando de inicio se hace lo mejor posible, sin garantías, así que revísala antes de guardar. El registro en el que busca A2Flow se puede cambiar por otro; consulta la [referencia de configuración](../operations/configuration.md#mcp-tools-and-approvals).

## Comprobar las herramientas de un servidor {#checking-a-servers-tools}

Los formularios de plantilla de tarea consultan a un servidor las herramientas que anuncia (nombre, descripción y esquema de entrada), pero solo al servidor que hayas elegido, nunca a todo el catálogo a la vez. Un servidor al que no se puede acceder o que no se puede iniciar lo indica en lugar de mostrar su lista de herramientas.

## Eliminar un servidor {#deleting-a-server}

Un servidor no se puede eliminar mientras alguna tarea o plantilla de tarea siga vinculada a una de sus herramientas. Quita primero esas vinculaciones.
