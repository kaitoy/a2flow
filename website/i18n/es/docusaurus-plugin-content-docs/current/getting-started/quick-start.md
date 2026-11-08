---
title: Inicio rápido
sidebar_position: 1
---

# Inicio rápido

## 0. Cadena de herramientas ([mise](https://mise.jdx.dev/)) {#0-toolchain-mise}

Las versiones de Python, Node.js, pnpm y uv están fijadas en [mise.toml](https://github.com/kaitoy/a2flow/blob/master/mise.toml) y las instala mise, de modo que todas las máquinas usan la misma cadena de herramientas. Instala mise una sola vez:

| SO | Comando |
|---|---|
| Windows | `winget install jdx.mise` |
| macOS | `brew install mise` |
| Linux | Consulta la [documentación de instalación](https://mise.jdx.dev/installing-mise.html) |

Actívalo en tu shell (para bash/zsh/fish, consulta la [documentación de activación](https://mise.jdx.dev/installing-mise.html#shells); en Windows, añade `(&mise activate pwsh) | Out-String | Invoke-Expression` a tu `$PROFILE` de PowerShell) y, después, instala las herramientas desde la raíz del repositorio:

```bash
mise trust
mise install
```

En Windows, añade también el directorio de shims de mise (`%LOCALAPPDATA%\mise\shims`) a tu `PATH`, para que `uv`, `pnpm` y `python` se resuelvan incluso fuera de una shell activada.

¿No usas mise? Las versiones mínimas son Python 3.11+ y Node.js 20+, además de [uv](https://docs.astral.sh/uv/) y pnpm instalados a mano.

## 1. Backend {#1-backend}

El backend en sí solo necesita Python y uv; Node.js únicamente se usa para lanzar con `npx` los [servidores MCP](../guides/mcp-servers.md) stdio publicados como paquetes npm, y la imagen de `docker compose` ya lo incluye.

```bash
cd backend
uv sync
cp .env.example .env
sed -i.bak 's/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=YOUR_API_KEY/' .env && rm .env.bak
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
```

`.env.example` usa Google Gemini de forma predeterminada, así que sustituye `YOUR_API_KEY` por tu propia clave. Para usar otro modelo o proveedor, consulta [Configuración del LLM](./llm-configuration.md).

La API ya está disponible en `http://localhost:8000`.

## 2. Frontend {#2-frontend}

```bash
cd frontend
pnpm install
# Opcional: cp .env.local.example .env.local  (solo hace falta si el backend no está en :8000)
pnpm build
pnpm start
```

Abre [http://localhost:3000](http://localhost:3000). Para usar otro puerto, consulta [Changing the port](https://github.com/kaitoy/a2flow/blob/master/frontend/README.md#changing-the-port) en el README del frontend.
