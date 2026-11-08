---
title: Skills de agente
sidebar_position: 6
---

# Skills de agente

Una skill de agente es lo que un agente sabe hacer, guardado en un repositorio Git. A2Flow mantiene un catálogo de ellas: cada registro indica un repositorio, y A2Flow lo clona y mantiene el clon al día.

Abre **Skills de agente** en la barra lateral de administración para gestionar el catálogo.

![Diagrama de estados que muestra cómo una skill de agente se registra, se clona en segundo plano, pasa a estar lista o fallida, se actualiza para reintentarlo desde cualquiera de los dos estados y, una vez lista, genera un nuevo flujo de trabajo.](./img/agent-skills-lifecycle.svg#gh-light-mode-only)
![Diagrama de estados que muestra cómo una skill de agente se registra, se clona en segundo plano, pasa a estar lista o fallida, se actualiza para reintentarlo desde cualquiera de los dos estados y, una vez lista, genera un nuevo flujo de trabajo.](./img/agent-skills-lifecycle-dark.svg#gh-dark-mode-only)

Una skill solo se puede usar cuando ha publicado una revisión. Hasta entonces, se rechaza generar o ejecutar un flujo de trabajo con ella.

## Qué contiene el registro de una skill {#what-a-skill-record-holds}

| Campo | Notas |
|---|---|
| **Nombre** | El nombre con el que se identifica la skill en todas las demás pantallas. |
| **URL del repositorio** | El repositorio que se va a clonar. |
| **Ruta del repositorio** | Dónde está la skill dentro del repositorio, si no está en la raíz. |
| **Referencia** | Opcional. El nombre de la rama o etiqueta a la que se fijan todas las clonaciones y actualizaciones. Si se deja vacío, se usa la rama predeterminada del repositorio. |
| **Descripción** | Texto libre. |
| **Usuario de autenticación** / **Contraseña de autenticación** | Para un repositorio privado (ver más abajo). |
| **Etiquetas** | Las [etiquetas](./tags.md) con las que se clasifica la skill. |

## Estado y revisión {#status-and-revision}

Las páginas de lista y de detalle muestran dos datos de estado que significan cosas distintas:

| Columna | Qué indica |
|---|---|
| **Estado** | Cómo fue la *última* clonación o actualización: `Clonando`, `listo` o `fallido` con el motivo. |
| **Revisión** | La revisión publicada actualmente. Una skill solo se puede ejecutar cuando este campo tiene valor. |

Ambos son independientes a propósito: una actualización fallida **no** borra la revisión publicada, así que una skill que funcionaba sigue funcionando con la revisión que tenía. Solo cambian el estado y el error.

## Actualizar el repositorio {#pulling}

**Actualizar** vuelve a clonar el repositorio en la **Referencia** configurada o, si no hay ninguna, en la rama predeterminada. Así es como una skill incorpora los cambios del repositorio de origen y como se reintenta un registro fallido después de corregir la URL o las credenciales. Si el extremo de una rama avanza o una etiqueta pasa a apuntar a otro sitio, el cambio se incorpora la próxima vez que se actualice la skill.

Se rechaza cualquier repositorio que contenga un **enlace simbólico** en cualquier punto de su árbol: la clonación o actualización falla con un motivo que nombra el enlace, y no se publica ninguna revisión a partir de él. Sustituye el enlace por una copia del archivo al que apunta.

Cada revisión publicada se conserva mientras algo la siga necesitando, y una ejecución permanece fijada a la revisión con la que empezó, de modo que actualizar nunca cambia lo que sigue una ejecución en curso. La ubicación del almacén y su retención se describen en la [referencia de configuración](../operations/configuration.md#agent-skill-store).

## Repositorios privados {#private-repositories}

Las credenciales no se escriben en el formulario de la skill. Regístralas una vez como [secreto](./secrets.md) y luego haz que la skill apunte a una de sus entradas:

1. Define **Usuario de autenticación**. Su valor predeterminado es `x-access-token`, adecuado para un token de acceso personal de GitHub; indica un nombre de cuenta real en los hosts que lo requieran.
2. Elige el **secreto** en el primer desplegable de **Contraseña de autenticación** y, en el segundo, una **Clave de entrada** de ese secreto. El valor de esa entrada se usa como contraseña al clonar el repositorio.

Una **Contraseña de autenticación** requiere una **URL del repositorio** que empiece por `https://`. Con `http://` se rechaza el guardado, ya que la contraseña viajaría sin cifrar por la red.

Se ofrecen los dos tipos de secreto. En un secreto respaldado por Vault, las claves de entrada se leen de Vault en tiempo real, ya que no se guardan localmente.

La referencia se guarda como un nombre y una clave, y se resuelve al clonar. Por eso, eliminar o renombrar el secreto más adelante no falla en ese momento: hace que falle la siguiente actualización y registra el motivo en la skill. La página de detalle no descarta en silencio una referencia que ya no se puede resolver: sigue seleccionada, marcada con `(no encontrado)` y con una advertencia. Borrarla es decisión tuya.

## Generar un flujo de trabajo a partir de una skill {#generating-a-workflow-from-a-skill}

La columna **Acciones** de cada fila incluye **Generar flujo de trabajo**, y la página de detalle de una skill ofrece la misma acción como botón de icono en su encabezado. Ambos abren el mismo cuadro de diálogo, y ambos están deshabilitados hasta que la skill haya publicado una revisión. Consulta [Generar un flujo de trabajo](./workflows.md#generating-a-workflow).

## Ver SKILL.md {#viewing-skillmd}

El encabezado de la página de detalle de una skill incluye el botón de icono **Ver SKILL.md**. Abre un cuadro de diálogo que muestra el archivo de instrucciones de la skill tal como está escrito en su repositorio. Igual que **Generar flujo de trabajo**, está deshabilitado hasta que la skill haya publicado una revisión, porque el archivo solo existe cuando la clonación se completa correctamente. A diferencia de las acciones de escritura anteriores, sigue disponible para quien consulta la página sin el rol de desarrollador.
