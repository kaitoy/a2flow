---
title: Comprobaciones de estado
sidebar_position: 5
---

# Comprobaciones de estado

`GET /api/v1/health` es lo que un orquestador o balanceador de carga sondea para decidir si una instancia del backend debe recibir tráfico. No requiere autenticación y devuelve un objeto simple en lugar del sobre habitual `{meta, data, error}`:

| Condición | Estado | Cuerpo |
|---|---|---|
| La base de datos respondió a una consulta trivial | `200` | `{"status": "ok"}` |
| No respondió | `503` | `{"status": "unavailable"}` |

Eso es toda la comprobación. Informa de un fallo con un código de estado claro en lugar de una página de error, y está excluida del registro de acceso, así que sondearla cada pocos segundos no cuesta nada ni deja ruido.

**Úsala tanto para liveness como para readiness.** Un backend que no llega a su base de datos no puede servir nada útil, y una instancia nueva solo responde 200 cuando ha terminado de arrancar, que es también cuando se han aplicado sus [migraciones](../architecture/database.md). Condicionar la puesta en producción a este endpoint es lo que evita que un despliegue gradual envíe tráfico a una instancia cuyo trabajo de esquema sigue en curso.

Docker Compose ya lo hace ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)):

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:8000/api/v1/health || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

Da a la comprobación un periodo de gracia de arranque, dondequiera que la configures. El primer arranque aplica las migraciones y crea los [usuarios iniciales](./configuration.md#seeded-users), así que una instancia puede tardar legítimamente más en responder que en un reinicio normal.

El frontend no tiene ruta de estado propia. No guarda estado y solo depende del backend, así que basta con una simple solicitud HTTP a su raíz.

Para las cifras de un despliegue en marcha (acumulación de aprobaciones, volumen de ejecuciones, fallos, tiempo de entrega, profundidad de la cola de correo), consulta [Métricas de operaciones](./metrics.md).
