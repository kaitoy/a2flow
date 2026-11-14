---
title: Déploiement
sidebar_position: 1
---

# Déploiement

Un déploiement se compose du frontend, du backend et d'une base de données relationnelle ; [Lancer avec Docker Compose](../getting-started/docker-compose.md) est le chemin le plus court pour obtenir les trois. La suite décrit ce qui change une fois que la pile se trouve derrière un proxy et contient des données à conserver.

![Schéma d'architecture montrant le navigateur qui atteint un proxy inverse, lequel achemine les requêtes d'API (/api/*) directement vers l'API du backend et les requêtes de pages vers le frontend, et l'API du backend, qui exécute aussi le worker d'e-mails, qui atteint l'état durable (base de données, magasin de compétences, clé secrète), les services externes (fournisseur de LLM, serveurs MCP) et un relais SMTP.](./img/deployment-topology.svg#gh-light-mode-only)
![Schéma d'architecture montrant le navigateur qui atteint un proxy inverse, lequel achemine les requêtes d'API (/api/*) directement vers l'API du backend et les requêtes de pages vers le frontend, et l'API du backend, qui exécute aussi le worker d'e-mails, qui atteint l'état durable (base de données, magasin de compétences, clé secrète), les services externes (fournisseur de LLM, serveurs MCP) et un relais SMTP.](./img/deployment-topology-dark.svg#gh-dark-mode-only)

Le navigateur dialogue avec une seule origine, et le proxy inverse l'achemine selon le chemin : `/api/*` et `/openapi.json` vers le backend, tout le reste vers le frontend. Les deux se trouvent sur le même domaine : les cookies d'authentification restent donc de première partie, et les flux de longue durée de chaque discussion ouverte vont directement au backend sans passer par le frontend. Le service `ingress` de `compose.yml` (Envoy) est un exemple fonctionnel de cet acheminement.

Sans cette route, le frontend transmet lui-même `/api/*` au backend : c'est ainsi que fonctionne une exécution sans conteneurs. Le comportement est le même, mais chaque discussion ouverte occupe alors aussi une connexion sur le frontend, qu'il faut donc également dimensionner selon le nombre de discussions simultanées. Toutes les variables citées ici sont décrites dans [Référence de configuration](./configuration.md).

## Proxy inverse et répartiteur de charge {#reverse-proxy-and-load-balancer}

**Les sessions persistantes et l'affinité de session ne sont pas nécessaires.** Consultez [Mise à l'échelle horizontale](./scaling.md) : c'est un verrou consultatif PostgreSQL, et non une affinité de routage, qui attache une conversation à un seul pilote à la fois, et uniquement pendant la durée d'un flux SSE.

Les routes SSE de l'agent (`POST /api/v1/workflow-executions/{id}/agent` et `POST /api/v1/workflows/{id}/agent`) nécessitent les réglages suivants sur le proxy inverse qui les achemine vers le backend :

| Réglage | Valeur requise | Pourquoi |
|---|---|---|
| Mise en tampon des réponses | Désactivée pour ces deux chemins | L'application envoie `X-Accel-Buffering: no`, que nginx respecte réponse par réponse même si la mise en tampon est activée globalement. Tout autre proxy doit la désactiver dans sa propre configuration |
| Compression | Jamais appliquée à `text/event-stream` | L'application ne compresse jamais ses réponses : toute compression vue par le client provient donc de cette couche |
| Délai de lecture / d'inactivité | Bien au-dessus de la plus longue exécution d'agent attendue | Une exécution d'agent n'a aucune limite de temps côté serveur : seul un délai de lecture du proxy peut donc mettre fin à un flux, et une valeur trop basse tronque silencieusement une longue réponse légitime. Dimensionnez-le d'après votre plus longue exécution, et non d'après une requête ordinaire |

Un déploiement progressif met fin de force à tout flux SSE encore ouvert 30 secondes après que le conteneur a reçu SIGTERM (`--timeout-graceful-shutdown 30`, défini dans le `CMD` du `Dockerfile` du backend). C'est sans danger : le verrou consultatif est libéré avec la connexion et le client reprend avec une nouvelle requête, exactement comme lorsqu'un flux est abandonné.

## Derrière HTTPS {#behind-https}

Un seul réglage décide de ce dont un déploiement derrière HTTPS a besoin : définissez `APP_BASE_URL` avec l'origine vue par le navigateur, comme `https://a2flow.example.com`. Le reste en découle :

| Quoi | Avec une `APP_BASE_URL` en `https://` | Sans `APP_BASE_URL` |
|---|---|---|
| Cookies de session et CSRF | Marqués `Secure` : le navigateur ne les envoie qu'en HTTPS | Sans `Secure` : le navigateur les envoie aussi en HTTP en clair |
| Origines autorisées à appeler l'API | Cette origine | Uniquement `http://localhost:3000` |
| E-mails de notification et authentification unique | Les e-mails renvoient vers l'application, et l'authentification unique est utilisable | Les e-mails partent sans lien, et l'authentification unique est indisponible |

`SESSION_COOKIE_SECURE` et `CORS_ORIGINS` peuvent toujours remplacer les deux premiers — voir la [Référence de configuration](./configuration.md#server-settings). La pile Docker Compose en donne un exemple fonctionnel : [Servir en HTTPS](../getting-started/docker-compose.md#https) place un proxy qui termine TLS devant le service `ingress` et transmet l'adresse au backend.

## Organisation des processus {#process-layout}

En plus de l'API, un déploiement exécute le [proxy MCP](../architecture/mcp-gateway-and-proxy.md#the-sandbox) : le processus qui démarre réellement les serveurs MCP enregistrés par un tenant ou s'y connecte. Cette séparation est tout l'intérêt du dispositif : c'est là que s'exécute le code tiers, si bien que ce processus n'a ni accès à la base de données, ni clé de chiffrement des secrets, ni clé d'API de LLM. `compose.yml` l'exécute dans le conteneur `mcp-proxy`, sur un réseau qu'il ne partage qu'avec l'API, de sorte qu'il ne peut pas du tout atteindre la base de données. Un déploiement qui assemble ses propres conteneurs doit de même tenir le proxy à l'écart du réseau de la base de données, et le configurer sous [Proxy MCP](./configuration.md#mcp-sandbox).

Deux points à ne pas manquer :

- **L'API doit démarrer la première.** C'est elle qui émet les éléments par lesquels les deux extrémités s'identifient mutuellement : le proxy n'accepte donc rien tant qu'ils n'ont pas été écrits. Subordonnez le démarrage du proxy au contrôle d'intégrité de l'API, comme le fait `compose.yml`.
- **Ils ont besoin d'un répertoire partagé.** `MCP_PROXY_TLS_DIR` doit désigner le même stockage des deux côtés, accessible en écriture à l'API et en lecture seule au proxy. Rien de durable n'y est conservé : son contenu est réécrit dès qu'il manque ou approche de son expiration.
- **Le proxy doit pouvoir créer des bacs à sable.** Il démarre chaque serveur dans [son propre bac à sable](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox) et vérifie au démarrage qu'il en est capable ; sinon, il s'arrête sur une erreur au lieu d'exécuter des serveurs sans bac à sable. Dans un conteneur, cela demande trois options de sécurité, que `compose.yml` accorde au service `mcp-proxy` et à lui seul : `seccomp=unconfined`, `apparmor=unconfined` et `systempaths=unconfined`. Sur un hôte Ubuntu 24.04 ou ultérieur, les espaces de noms utilisateur non privilégiés doivent aussi être autorisés : `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`.

Il est possible de se passer du proxy : laissez `MCP_PROXY_URL` non définie et l'API atteint elle-même les serveurs MCP, comme lors d'une exécution de développement local. Un serveur enregistré s'exécute alors à côté des identifiants du déploiement : ce n'est donc pas un choix à faire dans un environnement où n'importe qui peut en enregistrer un.

Le backend est également livré avec deux points d'entrée sur la même base de données. Celui que vous exécutez détermine d'où partent les e-mails de notification :

| Organisation | Comment | Quand l'utiliser |
|---|---|---|
| API seule | Par défaut : `EMAIL_WORKER_IN_PROCESS` vaut `true`, donc `uvicorn main:app` vide aussi la file d'e-mails | Un déploiement à processus unique, ou assez modeste pour qu'un relais bloqué sur le chemin des requêtes reste acceptable |
| API + worker | Exécutez `python -m worker` à côté de l'API et définissez `EMAIL_WORKER_IN_PROCESS=false` sur celle-ci | Toute situation où un relais bloqué ne doit rien coûter à ce qui sert les requêtes. C'est ce que fait `compose.yml` |

Deux remarques sur le processus worker :

- **Il n'effectue ni migration ni amorçage.** Le démarrage de l'API s'occupe des deux : le worker doit donc démarrer une fois l'API opérationnelle. `compose.yml` subordonne son démarrage au contrôle d'intégrité de l'API.
- **Plusieurs réplicas apportent du basculement, pas du débit.** Ils se disputent le verrou consultatif `email-queue` et tous sauf un restent inactifs par conception, ce qui maintient le débit d'envoi exact.

## Contrôles d'intégrité {#health-checks}

Dirigez votre orchestrateur ou votre répartiteur de charge vers `GET /api/v1/health`. Consultez [Contrôles d'intégrité](./health.md).

## L'état à conserver {#state-that-has-to-persist}

Trois éléments survivent à un conteneur et doivent résider sur un stockage durable pour qu'un déploiement redémarre intact :

| Élément | Emplacement | Conséquence de sa perte |
|---|---|---|
| **La base de données** | La base désignée par `DB_URL` | Tout est perdu : chaque enregistrement s'y trouve. Consultez [Base de données](../architecture/database.md) |
| **Le magasin de compétences d'agent** | `SKILLS_DIR` | Les exécutions ne peuvent plus charger la révision de compétence à laquelle elles sont liées (HTTP 409 `SKILL_NOT_READY`). Il s'agit d'un état durable, et non d'un cache ; consultez [Magasin de compétences d'agent](./configuration.md#agent-skill-store) |
| **La clé de chiffrement des secrets** | `SECRET_ENCRYPTION_KEY`, ou le fichier indiqué par `SECRET_KEY_FILE` | Tous les secrets locaux stockés deviennent indéchiffrables, et l'autorité de certification ne peut plus émettre ni vérifier les certificats dont chaque appel d'outil MCP a besoin. Consultez [Gestion des secrets](./configuration.md#secret-management) |

La sauvegarde et la restauration de chacun de ces éléments sont décrites dans [Sauvegarde et restauration](./backup.md).
