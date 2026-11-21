---
title: Panel
sidebar_position: 16
---

# Panel

El panel muestra cómo se están ejecutando ahora mismo los flujos de trabajo de tu tenant: qué está en curso, qué espera una aprobación, qué ha fallado y cuánto tardan las ejecuciones de principio a fin. Abre **Panel** en la parte superior de la barra lateral de administración.

Está pensado para dejarlo abierto: todas las cifras se vuelven a leer cada 15 segundos. Tiene dos vistas, y el navegador recuerda cuál elegiste. La vista estándar tiene el mismo aspecto que el resto de la aplicación y sigue tu tema claro u oscuro. La vista Control de misión está hecha para una pantalla de pared: permanece oscura sea cual sea el tema del resto de la aplicación, sus cifras brillan y siempre hay algo en movimiento.

Dos tipos de ejecución quedan fuera de todas las cifras: las ejecuciones de prueba iniciadas desde un flujo de trabajo que sigue siendo un borrador y las ejecuciones que una [etiqueta de control de acceso](./tags.md#access-control-tags) te oculta.

Para ver el panel con datos antes de que tu tenant haya ejecutado nada, carga los [datos de demostración](../getting-started/demo-data.md): incluyen unos noventa días de ejecuciones inventadas.

## La barra de herramientas {#the-toolbar}

| Control | Qué hace |
|---|---|
| **En vivo** | El punto indica que las cifras están al día. En la vista Control de misión late, y el anillo que lo rodea se vacía a medida que se acerca la siguiente lectura. Cambia a **Conexión perdida** cuando una lectura falla: las cifras en pantalla son entonces las últimas leídas, y el panel sigue intentándolo. |
| **7 días** / **30 días** / **90 días** | Fija el periodo que abarcan **Tiempo de entrega**, **Ejecuciones por flujo de trabajo** y **Requiere atención**. Los mosaicos y los demás paneles muestran siempre el presente. |
| **Actualizar** | Vuelve a leerlo todo ahora. |
| **Cambiar a la vista Control de misión** | Pasa a la vista Control de misión. **Cambiar a la vista estándar** vuelve a la anterior. Las dos vistas muestran las mismas cifras. |
| **Pantalla completa** | Llena la pantalla solo con el panel. Pulsa Esc, o **Salir de pantalla completa**, para volver. |

## Los mosaicos {#the-tiles}

Cada mosaico es un número, una línea de apoyo y un trazo de cómo se ha movido el número desde que abriste la página. En la vista Control de misión el número destella brevemente cada vez que cambia.

| Mosaico | El número | La línea de debajo | Su color cambia |
|---|---|---|---|
| **Ejecuciones activas** | Ejecuciones en curso, incluidas las programadas | Ejecuciones iniciadas en las últimas 24 horas | Nunca |
| **Aprobaciones pendientes** | Solicitudes de aprobación que esperan una decisión | Aprobaciones decididas hoy | A ámbar cuando alguna lleva más de 24 horas esperando |
| **Finalizadas hoy** | Ejecuciones que han finalizado hoy | La proporción que se completó sin ninguna tarea fallida | Nunca |
| **Ejecuciones fallidas, últimas 24 h** | Ejecuciones que terminaron con fallo en las últimas 24 horas | Tareas que fallaron en el mismo periodo | A rojo cuando es mayor que cero |
| **Cola de correo** | [Correos de notificación](./notifications.md#the-delivery-queue) aún sin enviar | Cuánto lleva esperando el más antiguo, o cuántos no se pudieron enviar | A ámbar cuando el más antiguo lleva más de cinco minutos esperando, a rojo cuando alguno ha fallado |

«Hoy» empieza a medianoche en la zona horaria del servidor: consulta [Ajustes del servidor](../operations/configuration.md#server-settings).

## Los paneles {#the-panels}

| Panel | Qué muestra | Cómo leerlo |
|---|---|---|
| **Tiempo de entrega** | El tiempo medio desde el inicio de una ejecución hasta su fin, para cada día en que finalizaron ejecuciones. La cifra de la esquina es la media de todo el periodo. | Pasa el puntero por el gráfico, o enfócalo y pulsa las teclas de flecha, para leer un día. Un día en que no finalizó nada no tiene punto. |
| **Aprobaciones acumuladas** | Todas las aprobaciones pendientes. El arco ámbar del anillo es la proporción que lleva más de 24 horas esperando. Debajo están las cinco esperas más largas. | Cambia entre **Aprobador** y **Flujo de trabajo** para ver a quién, o a qué flujo de trabajo, esperan las aprobaciones. Una barra se vuelve ámbar en cuanto una de sus aprobaciones lleva más de 24 horas esperando. |
| **Ejecuciones por flujo de trabajo** | Los ocho flujos de trabajo con más actividad del periodo, por ejecuciones iniciadas. Cada barra se divide en **completado**, **fallido** y **en ejecución**. | La cifra al final de una fila es su número de ejecuciones, junto al tiempo de entrega medio del flujo de trabajo. Pasa el puntero por un segmento para ver su recuento. |
| **Causas de fallo** | Las tareas que fallaron en las últimas 24 horas, según la causa registrada en cada una. | La leyenda nombra cada causa presente y su recuento. |
| **Requiere atención** | Las ejecuciones con una tarea fallida en el periodo, las más recientes primero, cada una con su causa. Solo se muestra a un Administrador. | Haz clic en una ejecución para abrirla, y desplaza la banda hacia los lados para ver el resto. En la vista Control de misión la banda se desplaza sola y se detiene mientras el puntero está sobre ella. |

## Quién lo ve {#who-sees-it}

**Panel** está en la barra lateral para Administrador, Desarrollador, Solicitante y Aprobador. Todos ven las mismas cifras del tenant; solo **Requiere atención** se reserva a un Administrador, porque cita nombres de tareas y causas de fallo de ejecuciones en las que quien mira puede no participar.

Para representar las mismas cifras en una herramienta de monitorización propia, consulta [Métricas de operaciones](../operations/metrics.md).
