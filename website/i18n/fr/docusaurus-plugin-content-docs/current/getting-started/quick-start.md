---
title: Démarrage rapide
sidebar_position: 1
---

# Démarrage rapide

## 0. Chaîne d'outils ([mise](https://mise.jdx.dev/)) {#0-toolchain-mise}

Les versions de Python, Node.js, pnpm et uv sont fixées dans [mise.toml](https://github.com/kaitoy/a2flow/blob/master/mise.toml) et installées par mise, de sorte que toutes les machines utilisent la même chaîne d'outils. Installez mise une seule fois :

| Système | Commande |
|---|---|
| Windows | `winget install jdx.mise` |
| macOS | `brew install mise` |
| Linux | Consultez la [documentation d'installation](https://mise.jdx.dev/installing-mise.html) |

Activez-le dans votre shell (consultez la [documentation d'activation](https://mise.jdx.dev/installing-mise.html#shells) pour bash/zsh/fish ; sous Windows, ajoutez `(&mise activate pwsh) | Out-String | Invoke-Expression` à votre `$PROFILE` PowerShell), puis installez les outils depuis la racine du dépôt :

```bash
mise trust
mise install
```

Sous Windows, ajoutez aussi le répertoire des shims de mise (`%LOCALAPPDATA%\mise\shims`) à votre `PATH`, afin que `uv` / `pnpm` / `python` soient trouvés même en dehors d'un shell activé.

Vous n'utilisez pas mise ? Les versions minimales sont Python 3.11+ et Node.js 20+, avec [uv](https://docs.astral.sh/uv/) et pnpm installés à la main.

## 1. Backend {#1-backend}

Le backend lui-même n'a besoin que de Python et d'uv ; Node.js sert uniquement à lancer les [serveurs MCP](../guides/mcp-servers.md) stdio publiés sous forme de paquets npm (`npx`), et l'image `docker compose` l'embarque.

```bash
cd backend
uv sync
cp .env.example .env
sed -i.bak 's/^GOOGLE_API_KEY=.*/GOOGLE_API_KEY=YOUR_API_KEY/' .env && rm .env.bak
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
```

Par défaut, `.env.example` utilise Google Gemini : remplacez donc `YOUR_API_KEY` par votre propre clé. Pour utiliser un autre modèle ou un autre fournisseur, consultez [Configuration du LLM](./llm-configuration.md).

L'API est maintenant accessible à l'adresse `http://localhost:8000`.

## 2. Frontend {#2-frontend}

```bash
cd frontend
pnpm install
# Facultatif : cp .env.local.example .env.local  (nécessaire uniquement si le backend n'est pas sur :8000)
pnpm build
pnpm start
```

Ouvrez [http://localhost:3000](http://localhost:3000). Pour utiliser un autre port, consultez [Changing the port](https://github.com/kaitoy/a2flow/blob/master/frontend/README.md#changing-the-port) dans le README du frontend.
