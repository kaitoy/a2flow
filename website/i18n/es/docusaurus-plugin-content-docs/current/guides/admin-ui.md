---
title: Interfaz de administración
sidebar_position: 1
---

# Interfaz de administración

El área de administración es donde se crea, consulta y edita cada registro de A2Flow. Es un único marco, con una barra de aplicación en la parte superior y una barra lateral de secciones a la izquierda, y todas sus secciones funcionan igual: cuando aprendes a usar una lista, ya sabes usar las quince.

## Página de bienvenida {#welcome-page}

La página de bienvenida es la pantalla de entrada: llegas a ella después de iniciar sesión, al abrir la raíz del sitio y cada vez que haces clic en el logotipo de **A2Flow** en la barra de aplicación. Te recibe con tarjetas de acción rápida, una por cada sección de administración que tus roles permiten.

![Diagrama de flujo del modelo de navegación de la interfaz de administración: la página de bienvenida lleva a la lista de una sección, desde la que se abre un formulario de creación o, al hacer clic en un nombre, una página de detalle; la ruta de navegación de la página de detalle devuelve a la lista.](./img/admin-ui-navigation.svg#gh-light-mode-only)
![Diagrama de flujo del modelo de navegación de la interfaz de administración: la página de bienvenida lleva a la lista de una sección, desde la que se abre un formulario de creación o, al hacer clic en un nombre, una página de detalle; la ruta de navegación de la página de detalle devuelve a la lista.](./img/admin-ui-navigation-dark.svg#gh-dark-mode-only)

La ruta de navegación situada sobre cada título refleja ese recorrido (`Inicio › Flujos de trabajo › my-workflow`), y todos sus elementos, salvo el último, enlazan de vuelta a los niveles superiores.

## Las secciones {#the-sections}

| Sección | Qué contiene | Se muestra en la barra lateral a |
|---|---|---|
| **Tenants** | Organizaciones tenant | Superadministrador |
| **Usuarios** | Cuentas y sus roles | Administrador, Desarrollador |
| **Grupos de usuarios** | Conjuntos con nombre que conceden roles a varias cuentas a la vez | Administrador, Desarrollador |
| **Etiquetas** | Las etiquetas con las que se clasifican los registros | Administrador, Desarrollador |
| **Secretos** | Credenciales para herramientas y repositorios | Administrador, Desarrollador |
| **Skills de agente** | Capacidades de los agentes, clonadas desde repositorios Git | Desarrollador, Administrador |
| **Bases de conocimiento** | Wikis que el LLM escribe a partir de tus documentos para que los consulten los flujos de trabajo | Desarrollador, Administrador, Revisor |
| **Servidores MCP** | Servidores de herramientas a los que el agente puede llamar | Desarrollador, Administrador |
| **Mocks de herramientas** | Sustitutos que simulan herramientas en las ejecuciones de flujos de trabajo en borrador | Desarrollador, Administrador |
| **Flujos de trabajo** | Flujos de varios pasos y sus plantillas de tareas | Desarrollador, Solicitante, Administrador |
| **Ejecuciones de flujos de trabajo** | Las ejecuciones de los flujos de trabajo y su historial | Todos los que han iniciado sesión |
| **Aprobaciones** | Solicitudes de aprobación y sus decisiones | Todos los que han iniciado sesión |
| **Registros de auditoría** | Llamadas a herramientas, suplantaciones, autoridad concedida y correos enviados | Administrador, Superadministrador |
| **Configuración del tenant** | Cómo bloquean los inicios de sesión fallidos las cuentas de tu tenant, y el Vault propio de tu tenant: consulta [Inicios de sesión fallidos](./users-and-groups.md#failed-sign-ins) y [El Vault del tenant](./users-and-groups.md#tenant-vault) | Administrador |
| **Configuración del sistema** | El servidor de correo por el que se envían las notificaciones y la dirección del Vault global | Superadministrador |

Si una sección no aparece en tu barra lateral, es que tus roles no pueden escribir en ella. La lectura sigue abierta, así que un compañero aún puede enviarte un enlace directo a un registro de esa sección: consulta [Roles y autorización](../concepts/authorization.md).

[Registros de auditoría](./audit-logs.md) es la excepción: también restringe la lectura, y sin el rol de Administrador un enlace directo lleva a una pantalla de acceso denegado. La otra excepción son los registros con una [etiqueta de control de acceso](./tags.md#access-control-tags): a menos que tus grupos tengan esa etiqueta, el enlace indica que no se encontró el registro.

## La pantalla de lista {#the-list-screen}

Cada sección se abre con una tabla, y todas las tablas ofrecen los mismos controles:

| Control | Qué hace |
|---|---|
| **Menú del encabezado de columna** | Ordena y filtra por esa columna. Ambas operaciones se aplican a todos los datos, no solo a la página que ves en pantalla. |
| **Bordes de columna** | Arrástralos para cambiar el ancho. Los anchos duran lo que la sesión y no se guardan. |
| **Pasar el cursor sobre una celda** | Muestra el texto completo de lo que queda recortado por el ancho de la columna. |
| **▥ Columnas** | Abre el selector de columnas (ver más abajo). |
| **Actualizar** | Vuelve a cargar la lista. |
| **+ Añadir …** | Abre el formulario de creación. Está oculto si no tienes el rol de escritura. |
| **Columna Acciones** | Acciones por fila: **Eliminar** y las demás que ofrezca ese tipo de registro. Está oculta si no tienes el rol de escritura. |

Una columna con un conjunto fijo de valores (el estado de una tarea, el transporte de un servidor MCP, el color de una etiqueta) se ordena según el orden en que esos valores deben leerse, no alfabéticamente. Por eso, al ordenar las tareas por estado, aparecen `pendiente`, `en curso`, `completado`, `fallido` y `omitido`, el mismo orden del ciclo de vida que siguen los puntos de estado en todas las demás pantallas.

### Elegir columnas {#choosing-columns}

El botón **▥**, junto a **Actualizar**, enumera todas las columnas que la tabla puede mostrar:

- **Mostrar todo** / **Ocultar todo** cambia todas a la vez; **Restablecer valores predeterminados** vuelve al conjunto de fábrica.
- Algunas columnas empiezan ocultas para que las importantes tengan más ancho: el transporte de un servidor MCP, la referencia de un secreto, la referencia y la revisión de una skill de agente, o el correo y el indicador de verificación de un usuario.
- La columna identificadora y la columna **Acciones** siempre se muestran, así que no aparecen en la lista.
- El navegador recuerda tus elecciones para cada tabla, y se conservan al recargar la página. Solo se guardan tus diferencias respecto al valor predeterminado, de modo que una columna que se añada más adelante a la tabla seguirá apareciendo con el estado predeterminado previsto.
- Al ocultar una columna que está en uso para ordenar o filtrar, ese orden o filtro se elimina, para que las filas en pantalla nunca queden limitadas por un criterio que nada en la página puede mostrar.

El panel siempre cabe en la pantalla: se abre hacia arriba cuando no hay espacio debajo, desplaza su lista internamente sin perder de vista los botones de mostrar y ocultar todo, y se divide en dos columnas cuando una tabla tiene más de ocho columnas alternables. Así, incluso **Skills de agente**, con diecisiete columnas, sigue siendo accesible en la pantalla baja de un portátil.

## La pantalla de detalle {#the-detail-screen}

Al hacer clic en el nombre de un registro en la columna identificadora se abre su página de detalle. Esa página es la única pantalla del registro: sus atributos y todas las acciones que admite, como guardar cambios, eliminarlo y las demás que ofrezca su tipo, por ejemplo publicar un flujo de trabajo o actualizar el repositorio de una skill. Su título es el **nombre del propio registro**, no el de la operación.

Sin el rol de escritura, la misma página se muestra en modo de solo lectura: los campos aparecen como valores atenuados en lugar de cuadros de entrada, **Guardar** y **Eliminar** desaparecen, y **Cancelar** pasa a ser **Volver**.

Las [ejecuciones de flujos de trabajo](./workflow-executions.md) son la excepción a todo esto. Una ejecución es un historial, no un registro que se edita, así que su fila abre el chat de la ejecución o su lista de tareas de solo lectura en lugar de un formulario de edición.
