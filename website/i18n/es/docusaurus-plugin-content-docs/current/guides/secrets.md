---
title: Secretos
sidebar_position: 9
---

# Secretos

Un secreto es un **conjunto con nombre de entradas de clave y valor**, con la misma forma que usa el [motor KV de HashiCorp Vault](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2), en el que una ruta contiene un mapa de claves a valores. Las credenciales que van juntas, como un ID de clave de acceso de AWS y su clave de acceso secreta, se guardan en un solo secreto como dos entradas, y no en dos secretos separados.

Abre **Secretos** en la barra lateral de administración para gestionarlos. Cada registro tiene un **Nombre**, una **Descripción** opcional, sus [etiquetas](./tags.md) y un tipo.

## Dónde se usa un secreto {#where-a-secret-is-used}

![Diagrama de flujo que muestra cómo se hace referencia a una entrada de un secreto, ya sea en los encabezados y las variables de entorno de un servidor MCP, o como contraseña de autenticación del repositorio de una skill de agente.](./img/secrets-usage.svg#gh-light-mode-only)
![Diagrama de flujo que muestra cómo se hace referencia a una entrada de un secreto, ya sea en los encabezados y las variables de entorno de un servidor MCP, o como contraseña de autenticación del repositorio de una skill de agente.](./img/secrets-usage-dark.svg#gh-dark-mode-only)

- **[Servidores MCP](./mcp-servers.md)**: cualquier valor de encabezado o de variable de entorno puede incluir `${secret:name/key}`, que se expande al conectar.
- **[Skills de agente](./agent-skills.md)**: la **Contraseña de autenticación** de una skill es una referencia a una entrada, que se elige en listas desplegables en lugar de escribirse.

Una entrada concreta siempre se indica como **`name/key`**. La clave es obligatoria aunque el secreto contenga una sola entrada, porque un nombre solo identifica un mapa, no un valor; por eso, un `${secret:name}` sin clave no se resuelve, en lugar de pasarse como una cadena literal.

## Los dos tipos {#the-two-types}

| | **Local (cifrado)** | **HashiCorp Vault** |
|---|---|---|
| **Qué se almacena** | Las propias entradas, con cada valor cifrado | Solo una referencia a KV v2: **Montaje de Vault** y **Ruta de Vault** |
| **De dónde salen los valores** | Del almacén cifrado | Se leen directamente de Vault cada vez que se resuelven |
| **Qué muestra la página de detalle** | Todas las claves almacenadas, con el valor en blanco | El montaje y la ruta |
| **Cómo se edita una entrada** | Deja el valor en blanco para conservarlo, vuelve a escribirlo para sustituirlo o quita la fila para eliminar la entrada | En Vault |

Los valores **nunca se devuelven** en ninguno de los dos tipos, ni como texto sin cifrar ni como texto cifrado; por eso la página de detalle del tipo local muestra las claves con los valores en blanco. Lo único que se puede leer son las claves, de modo que un selector puede listarlas: en un secreto local proceden del mapa almacenado y en un secreto de Vault se leen de Vault en ese momento.

Un secreto de Vault se lee del Vault de **su propio tenant**, que el administrador del tenant conecta en [Configuración del tenant](./users-and-groups.md#tenant-vault). Un tenant que no tenga ninguno lee del [Vault global](./system-settings.md#global-vault) con una [credencial propia](./users-and-groups.md#global-vault-credential), cuyas políticas de Vault deciden qué puede leer. Sin ninguno de los dos, los secretos de tipo Vault no se pueden resolver. La clave con la que se cifran los secretos locales se configura una sola vez; consulta la [referencia de configuración](../operations/configuration.md#secret-management).

## Cambiar el nombre y eliminar {#renaming-and-deleting}

Los secretos se referencian **por nombre** y se resuelven en el momento de usarlos. Cambiar el nombre de un secreto al que algo sigue haciendo referencia, o eliminarlo, no falla al editar: el que falla es el siguiente uso, que indica el nombre del secreto que no ha encontrado. Una [skill de agente](./agent-skills.md) cuya referencia ha quedado obsoleta anota el motivo en su propio registro la próxima vez que se actualiza desde el repositorio.

Eso sí, al guardar una referencia se comprueba. Cuando guardas un servidor MCP cuyos encabezados o variables de entorno mencionan un secreto, usas **Ejecución de prueba** en un script o guardas la **Contraseña de autenticación** de una skill, el secreto debe existir y debes poder abrirlo. Un secreto que tienes oculto por una [etiqueta de control de acceso](./tags.md#access-control-tags) se rechaza exactamente igual que uno que no existe. Lo mismo ocurre cuando editas un registro que ya hace referencia a un secreto así, aunque solo cambies otro campo.
