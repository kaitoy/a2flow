---
title: Base de données
sidebar_position: 7
---

# Base de données

Toutes les données persistantes résident dans une seule base de données relationnelle, choisie par `DB_URL` dans `backend/.env` :

| Moteur | `DB_URL` | Remarques |
|---|---|---|
| SQLite (par défaut) | `sqlite:///a2flow.db` | Fichier local, sans configuration |
| PostgreSQL | `postgresql://user:password@host:5432/a2flow` | Utilisé par la pile Docker Compose |

Le suffixe du pilote asynchrone (`aiosqlite` / `asyncpg`) est ajouté automatiquement. Les changements de schéma sont suivis sous forme de migrations [Alembic](https://alembic.sqlalchemy.org/) versionnées et appliqués automatiquement au démarrage : c'est le redéploiement de l'application (un redémarrage de conteneur) qui lance les migrations en attente, si bien qu'aucune étape de migration distincte n'est nécessaire.

La base de données assure aussi la coordination d'un backend à plusieurs réplicas : une exécution d'agent détient un verrou consultatif PostgreSQL pendant toute la durée de son flux SSE, de sorte qu'une conversation n'est jamais pilotée par deux réplicas à la fois. Voir [Mise à l'échelle horizontale](../operations/scaling.md) pour ce que cela protège et la contrainte que cela impose sur le regroupement des connexions.

## Ce qu'elle contient {#what-it-holds}

| Table | Contenu |
|---|---|
| `users` | Les utilisateurs de l'application et les rôles qui leur sont accordés ; voir [Utilisateurs et groupes](../guides/users-and-groups.md) |
| `auth_sessions` | Les sessions de connexion côté serveur |
| `login_failures` | Les [échecs de connexion](../guides/users-and-groups.md#failed-sign-ins) récents, comptés pour verrouiller un compte en cas de tentatives répétées ; les lignes de plus d'un jour sont supprimées |
| `impersonation_events` | La piste d'audit des sessions d'[emprunt d'identité](../concepts/impersonation.md) |
| `agent_skills` | Les définitions de [compétences d'agent](../guides/agent-skills.md) et le dépôt d'où chacune est clonée |
| `mcp_servers` | Les [serveurs MCP](../guides/mcp-servers.md) enregistrés et la façon de les joindre |
| `knowledge_bases`, `knowledge_sources`, `knowledge_pages` | Les [bases de connaissances](../guides/knowledge-bases.md) : les documents importés et les URL enregistrées de chacune, et les pages rédigées à partir de ceux-ci |
| `secrets` | Les [ensembles d'identifiants](../guides/secrets.md) nommés, chiffrés localement ou référencés dans Vault |
| `workflows` | Les définitions de [workflows](../guides/workflows.md) et leur état dans leur cycle de vie |
| `workflow_task_templates` | La liste de tâches conçue à l'avance pour un workflow |
| `workflow_published_versions` | La conception figée au moment de la publication, d'après laquelle s'exécute un workflow à l'état `modifié` |
| `workflow_executions` | Une ligne par [exécution](../guides/workflow-executions.md), avec les métadonnées du workflow et de la compétence figées au lancement |
| `workflow_tasks` | Les tâches individuelles d'une exécution, copiées depuis les modèles |
| `workflow_task_tool_bindings` | Les outils MCP liés à une tâche |
| `message_meta` | Les informations par message des deux discussions partagées : qui a envoyé le message et quelle tâche était en cours |

La suppression d'un workflow s'étend à ses modèles, mais laisse intactes ses exécutions passées : une exécution est le compte rendu de ce qui s'est passé, et non une partie de la conception dont elle est issue.
