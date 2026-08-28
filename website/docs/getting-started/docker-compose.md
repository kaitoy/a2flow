---
title: Run with Docker Compose
sidebar_position: 2
---

# Run with Docker Compose

Alternatively, the whole stack — PostgreSQL 17, the backend, the [outgoing-email worker](../guides/notifications.md#the-delivery-queue), and the frontend — can be built and started with Docker Compose ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)):

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). Database data persists in the `pgdata` volume across restarts.

Set `FRONTEND_PORT` in `.env` to publish the frontend on a different host port (the container still listens on 3000 internally); the backend's `CORS_ORIGINS` follows it automatically.
