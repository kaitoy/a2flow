---
title: Configuración del sistema
sidebar_position: 13
---

# Configuración del sistema

En Configuración del sistema se definen el servidor de correo por el que sale el [correo de notificación](./notifications.md#email-delivery) y el HashiCorp Vault global. Hay exactamente un registro de configuración para todo el despliegue, que se crea en el primer inicio con la entrega de correo **desactivada**, de modo que en una instalación nueva las notificaciones se quedan dentro de la aplicación hasta que un operador la active.

Abre **Configuración del sistema** en la barra lateral de administración. Igual que [Tenants](./users-and-groups.md#tenants), esta sección está reservada al **Superadministrador**: la configuración afecta a toda la plataforma y no a un tenant, así que no hay ninguna excepción para los administradores de tenant, e incluso su lectura se rechaza para cualquier otra persona.

## La configuración {#the-settings}

| Campo | Para qué sirve |
|---|---|
| **URL base de la aplicación** | A dónde apuntan los enlaces del correo de notificación, por ejemplo `https://a2flow.example.com`. Si se deja vacía, los mensajes se envían sin enlace. |
| **Enviar notificaciones por correo electrónico** | El interruptor general. Mientras está desactivado, las notificaciones se quedan dentro de la aplicación y no se envía nada. |
| **Host SMTP** / **Puerto SMTP** | El relé al que se entregan los mensajes. |
| **Seguridad** | **STARTTLS** (predeterminado), **SSL/TLS** (TLS implícito) o **Ninguno**. |
| **Usuario SMTP** / **Contraseña SMTP** | Credenciales de SMTP AUTH. Deja vacío el usuario si el relé no las necesita. |
| **Dirección del remitente** / **Nombre del remitente** | La dirección del remitente y el nombre opcional que se muestra junto a ella. |

Si intentas activar la entrega sin un host o sin una dirección de remitente, se rechaza, de modo que el formulario no se puede guardar en un estado que más adelante fallaría sin avisar.

Todos estos campos también se pueden definir desde el entorno, de modo que un despliegue puede incluir su configuración de correo en lugar de dejarla como un paso manual; consulta [Correo de notificación](../operations/configuration.md#notification-email). Esas variables se vuelven a aplicar en cada inicio, por lo que un valor definido así sobrescribe lo que se haya escrito aquí.

La contraseña es de **solo escritura**, el mismo tratamiento que reciben los [secretos](./secrets.md) y las contraseñas de usuario: nunca se vuelve a mostrar. Cuando hay una almacenada, el campo aparece en blanco con el texto de ejemplo «Guardado: déjalo vacío para conservarlo», y si guardas con el campo vacío se conserva la contraseña almacenada en lugar de borrarse.

## El Vault global {#global-vault}

El Vault global es el HashiCorp Vault (solo KV v2) del que leen sus [secretos de tipo Vault](./secrets.md) todos los tenants **que no tienen Vault propio**. El administrador de un tenant puede conectar en su lugar el Vault propio del tenant en [Configuración del tenant](./users-and-groups.md#tenant-vault), y ese siempre tiene prioridad.

| Campo | Para qué sirve |
|---|---|
| **Dirección de Vault global** | La dirección del Vault, que empieza por `http://` o `https://`. A diferencia del Vault propio de un tenant, puede estar en una red privada. Déjala vacía y guarda para desconectar el Vault global. |

Aquí solo se define la dirección. No hay ninguna credencial compartida: cada tenant inicia sesión con **su propia credencial**, que un Superadministrador registra en la página del tenant (consulta [La credencial del Vault global](./users-and-groups.md#global-vault-credential)). Un tenant sin credencial no puede leer el Vault global de ninguna manera.

Los tenants se mantienen separados **por el propio Vault**: un secreto se lee del **Montaje de Vault** y la **Ruta de Vault** que indica, y las políticas asociadas a la credencial del tenant deciden si esa lectura está permitida. Emite para cada tenant una credencial cuya política abarque solo los datos de ese tenant; por ejemplo, un AppRole por tenant con una política como esta para el tenant `acme`:

```hcl
path "secret/data/tenants/acme/*" {
  capabilities = ["read"]
}
```

## Comprobar la configuración {#checking-the-configuration}

**Enviar correo de prueba** entrega un mensaje de prueba fijo con la configuración *guardada*, de modo que un error de configuración se detecta de inmediato y no la próxima vez que un flujo de trabajo genere una notificación.

1. Guarda primero la configuración: la prueba usa lo que está almacenado, no lo que hay en pantalla.
2. Haz clic en **Enviar correo de prueba**.
3. Revisa tu propia bandeja de entrada. El destinatario es siempre la dirección del superadministrador que ha iniciado sesión y no se puede cambiar por otra.

Un fallo del relé se muestra como un error en la página; el motivo subyacente queda registrado en el servidor.
