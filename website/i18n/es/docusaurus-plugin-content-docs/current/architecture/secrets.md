---
title: Almacenamiento de secretos
sidebar_position: 8
---

# Almacenamiento de secretos

Un [secreto](../guides/secrets.md) es un conjunto con nombre de entradas de clave/valor, y cada referencia apunta exactamente a una entrada: `${secret:name/key}` en los encabezados o el entorno de un servidor MCP, un nombre y una clave en una skill de agente. Las referencias se guardan por nombre y **se resuelven solo cuando se usan**, de modo que nada que necesite una credencial la almacena nunca.

![Diagrama de flujo que muestra una referencia a un secreto que se bifurca según el tipo: local descifra el valor guardado, vault lo lee en vivo desde Vault, y ambos alimentan una conexión a un servidor MCP o la clonación de un repositorio de skill.](./img/secrets-resolution.svg#gh-light-mode-only)
![Diagrama de flujo que muestra una referencia a un secreto que se bifurca según el tipo: local descifra el valor guardado, vault lo lee en vivo desde Vault, y ambos alimentan una conexión a un servidor MCP o la clonación de un repositorio de skill.](./img/secrets-resolution-dark.svg#gh-dark-mode-only)

| | **Local** | **HashiCorp Vault** |
|---|---|---|
| Qué se guarda | Las propias entradas, con cada valor cifrado | Solo una referencia KV v2: un montaje y una ruta |
| De dónde salen los valores | Del almacén cifrado | De Vault, leídos en el momento de la resolución |
| Cómo se listan las claves | Desde el mapa guardado, sin descifrar nada | Se leen de Vault en ese momento |
| Qué puede leer un cliente | Solo las claves, nunca un valor, ni en claro ni cifrado | Solo las claves |

## Secretos locales {#local-secrets}

Los valores se cifran con una única clave que pertenece al despliegue. Las claves de las entradas se quedan en texto plano junto a ellos, lo que permite que un selector las liste sin descifrar nada, y ningún valor se devuelve nunca a un cliente en ninguna forma; por eso la página de detalle de un secreto local muestra sus claves con los valores en blanco.

La clave de cifrado se resuelve una vez por proceso: se toma del entorno si está definida ahí; si no, se lee de un archivo de clave; y, si tampoco existe, se genera en el primer uso y se escribe en ese archivo, con una advertencia en el registro.

**Haz una copia de seguridad de esa clave.** Si se pierde, ningún secreto local guardado puede descifrarse y, como la misma clave protege la clave de firma de la autoridad que emite los [certificados de herramientas](./approvals.md), tampoco pueden emitirse ni verificarse certificados, lo que detiene todas las llamadas a herramientas MCP. Ambas se describen en la [referencia de configuración](../operations/configuration.md#secret-management).

## Secretos de HashiCorp Vault {#hashicorp-vault-secrets}

En un secreto respaldado por Vault, A2Flow no guarda ningún valor, solo el montaje y la ruta de los que leerlos. Tanto los valores como la lista de claves se obtienen en vivo cada vez que se necesitan, así que rotar un valor en Vault surte efecto sin tocar A2Flow.

Un secreto siempre se lee a través del Vault del tenant al que pertenece. Ese es el Vault **propio** del tenant cuando su administrador ha conectado uno en [Configuración del tenant](../guides/users-and-groups.md#tenant-vault) y, si no, el [Vault global](../guides/system-settings.md#global-vault) que configuró un Superadministrador, en el que se inicia sesión con la [credencial propia](../guides/users-and-groups.md#global-vault-credential) del tenant. Ambos se autentican con un token estático o con credenciales de AppRole; un token de AppRole se reutiliza hasta que su concesión está a punto de caducar y entonces se renueva volviendo a iniciar sesión. En el Vault global cada tenant tiene su propia credencial, de modo que los tenants se mantienen separados por las políticas de Vault asociadas a esas credenciales. Sin ninguno de los dos, los secretos de tipo `vault` de un tenant no pueden resolverse en absoluto.

## Dónde ocurre la resolución {#where-resolution-happens}

| Consumidor | Se resuelve cuando |
|---|---|
| Los valores de encabezados y de entorno de un servidor MCP | El [gateway](./mcp-gateway-and-proxy.md) los expande para la conexión que el proxy MCP abre con ese servidor |
| La contraseña del repositorio de una skill de agente | El repositorio se clona o se actualiza |

Como la resolución es diferida, cambiar el nombre de un secreto al que algo sigue haciendo referencia, o eliminarlo, no falla al editar. Lo que falla es el siguiente uso, que indica el secreto que no encontró; el motivo subyacente se queda en el registro del servidor y no se le entrega a quien llama.
