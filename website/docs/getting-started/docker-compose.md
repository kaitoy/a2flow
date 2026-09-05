---
title: Run with Docker Compose
sidebar_position: 2
---

# Run with Docker Compose

Alternatively, the whole stack can be built and started with Docker Compose ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)):

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). Database data persists in the `pgdata` volume across restarts.

Set `FRONTEND_PORT` in `.env` to publish the frontend on a different host port (the container still listens on 3000 internally); the backend's `CORS_ORIGINS` follows it automatically.

## What comes up

| Container | What it does |
|---|---|
| **db** | PostgreSQL 17. Everything A2Flow records lives here |
| **backend** | The agent and the API |
| **worker** | Sends the [notification email](../guides/notifications.md#the-delivery-queue) the backend queues |
| **mcp-proxy** | Runs the [MCP servers](../guides/mcp-servers.md) you register — see [why it is separate](../architecture/mcp-proxy.md#the-sandbox) |
| **frontend** | The screens you use |

Only the frontend is reachable from outside; the rest talk to each other on Docker's internal network.

The first start takes longer than later ones: the images are built, the database schema is created, and the MCP proxy waits for the backend to hand it the certificate it needs before it will accept anything.
