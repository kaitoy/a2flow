---
title: Référence de configuration
sidebar_position: 2
---

# Référence de configuration

Tous les paramètres ci-dessous sont des variables d'environnement. Le backend les lit dans `backend/.env` ([backend/.env.example](https://github.com/kaitoy/a2flow/blob/master/backend/.env.example) en est le modèle commenté) ; les deux variables du frontend sont lues dans l'environnement du processus du frontend lui-même. Les paramètres du modèle et des clés d'API ont leur propre page, [Configuration du LLM](../getting-started/llm-configuration.md).

## Paramètres du serveur {#server-settings}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `HOST` | `0.0.0.0` | Adresse sur laquelle le backend écoute |
| `PORT` | `8000` | Port sur lequel le backend écoute |
| `RELOAD` | `false` | Rechargement automatique d'uvicorn pour le développement local. Lue uniquement lorsque le backend est démarré avec `python -m backend.main` ; la commande de démarrage de l'image Docker n'en dépend en aucun cas |
| `TIMEZONE` | `UTC` | Nom IANA du fuseau horaire local du déploiement. Il détermine où commence un jour calendaire pour les [métriques d'exploitation](./metrics.md) (les compteurs « du jour » et les tranches quotidiennes de la tendance du délai d'exécution). C'est aussi le fuseau dans lequel l'agent de workflow interprète l'exigence horaire d'une tâche lorsqu'elle n'en nomme aucun. Un nom non reconnu se rabat sur `UTC` au lieu de faire échouer le démarrage : une faute de frappe fausse donc les heures locales sans arrêter l'application |

## Paramètres du frontend {#frontend-settings}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `BACKEND_BASE_URL` | `http://localhost:8000` | Destination vers laquelle le frontend transmet `/api/*` lorsqu'aucun proxy inverse ne l'achemine d'abord vers le backend (exécution sans conteneurs), et adresse à laquelle la page de documentation de l'API vérifie la session connectée. Lue une seule fois au démarrage du processus. Dans la pile Docker Compose, il s'agit de l'adresse du backend sur le réseau interne, et non d'une adresse publique |
| `APP_PORT` | `3000` | Docker Compose uniquement : le port de l'hôte sur lequel l'application est publiée, c'est-à-dire le port du service `ingress`, qui sert à la fois les écrans et l'API. La variable `CORS_ORIGINS` du backend le suit automatiquement |
| `OPENBAO_PORT` | `8200` | Docker Compose uniquement, avec `--profile openbao` : le port de l'hôte sur lequel l'interface d'OpenBao est publiée ; consultez [Essayer les secrets Vault avec OpenBao](../getting-started/docker-compose.md#openbao). A2Flow y accède dans tous les cas par le réseau interne |

## Base de données de l'application {#application-database}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `DB_URL` | `sqlite:///a2flow.db` | URL de la base de données. SQLite (relatif au répertoire de travail) et PostgreSQL sont pris en charge |
| `DB_POOL_SIZE` | `5` | PostgreSQL uniquement. Nombre de connexions que chacun des deux pools de connexions d'un processus backend garde ouvertes. Au moins `1`. Consultez [Pooling de connexions](./scaling.md#connection-pooling) pour savoir comment ce nombre se cumule entre les réplicas |
| `DB_MAX_OVERFLOW` | `10` | PostgreSQL uniquement. Connexions supplémentaires que chaque pool peut ouvrir au-delà de `DB_POOL_SIZE` sous charge, puis refermer une fois le pic passé. Au moins `0` |

Le suffixe du pilote asynchrone (`sqlite+aiosqlite` / `postgresql+asyncpg`) est ajouté automatiquement ; le schéma simple suffit donc :

```env
DB_URL=postgresql://user:password@localhost:5432/a2flow
```

Les changements de schéma sont suivis sous forme de migrations [Alembic](https://alembic.sqlalchemy.org/) versionnées et appliqués automatiquement au démarrage : redéployer l'application suffit donc à mettre le schéma à jour. Exécuter plusieurs réplicas du backend nécessite PostgreSQL ; consultez [Mise à l'échelle horizontale](./scaling.md). Le contenu de chaque table est décrit dans [Base de données](../architecture/database.md).

## Utilisateurs initiaux {#seeded-users}

Au démarrage, le backend crée un **utilisateur système** caché, ainsi que deux comptes réels, chacun créé uniquement au tout premier démarrage qui constate l'absence de l'enregistrement visé :

- Un utilisateur **`root`** initial détenant le rôle **Super administrateur** (consultez [Rôles et autorisations](../concepts/authorization.md)), à l'échelle de la plateforme (`tenantId: null`). Sa création est ignorée dès qu'il existe *au moins un* utilisateur réel (non système) ; elle n'a donc lieu qu'au tout premier démarrage.
- Un tenant **Default** (`slug: default`) et, à l'intérieur, un utilisateur **`admin`** initial détenant le rôle **Administrateur**. Le tenant (d'après son `slug`) et l'utilisateur (d'après son `username` dans ce tenant) sont vérifiés indépendamment : l'un peut donc être recréé sans dupliquer l'autre.

L'**utilisateur système** caché est propriétaire des enregistrements d'amorçage (il ne peut pas se connecter et n'apparaît pas dans la liste des utilisateurs).

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `ROOT_PASSWORD` | générée | Mot de passe de l'utilisateur `root` initial |
| `ADMIN_PASSWORD` | générée | Mot de passe de l'utilisateur `admin` initial du tenant Default |

Si l'une de ces variables n'est pas définie (ou est vide), un mot de passe aléatoire est généré à la place et consigné **une seule fois**, au niveau `WARNING`, à la création de l'utilisateur. Il ne peut plus être récupéré une fois cette ligne de journal disparue. Au-delà d'un simple essai en local, définissez explicitement les deux avant le premier démarrage, ou relevez aussitôt les mots de passe générés dans les journaux de démarrage et modifiez-les ensuite. Les noms d'utilisateur sont fixés à `root` et `admin`.

## Durée de vie des sessions {#session-lifetime}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `SESSION_IDLE_TIMEOUT_SECONDS` | `28800` (8 heures) | Délai d'inactivité glissant. Les requêtes authentifiées actualisent l'heure de dernière activité de la session, au plus une fois toutes les 5 minutes (ou selon un intervalle égal à la moitié de cette valeur, s'il est plus court) ; une session peut donc se terminer jusqu'à cette durée plus tôt. Une session inactive plus longtemps que ce délai est rejetée et supprimée |
| `SESSION_COOKIE_SECURE` | `false` | Marque les cookies de session et CSRF comme `Secure` (HTTPS uniquement). Définissez-la sur `true` pour tout déploiement derrière HTTPS |

Les cookies eux-mêmes sont des cookies de session (sans `Max-Age` ni `Expires`) ; ils sont donc aussi effacés à la fermeture du navigateur. Le navigateur atteint le backend sur la même origine que le frontend (`/api/*` y est acheminé selon le chemin, soit par le proxy inverse, soit par le frontend lui-même) : les cookies sont donc de première partie et `SameSite=Lax` s'applique sans difficulté.

## CORS {#cors}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Liste, séparée par des virgules, des origines autorisées à appeler l'API du backend |

Ajoutez chaque origine depuis laquelle le frontend est servi :

```env
CORS_ORIGINS=https://app.example.com,http://localhost:3000
```

`*` est rejeté au démarrage : `allow_credentials=True` est toujours activé, et l'associer à une origine générique n'est pas valide selon la spécification CORS.

## Magasin de compétences d'agent {#agent-skill-store}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `SKILLS_DIR` | `backend/.skills` | Racine du magasin dans lequel les dépôts de compétences d'agent sont clonés superficiellement. Sous `docker compose`, il s'agit de `/var/lib/a2flow/skills`, porté par le volume nommé `skills` |
| `SKILLS_PRUNE_GRACE_SECONDS` | `3600` | Durée pendant laquelle le répertoire d'une révision est conservé, qu'il soit référencé ou non. Une récupération supprime les révisions auxquelles aucune exécution n'est liée, et ce délai de grâce couvre l'intervalle entre le moment où une exécution lit la révision actuelle et celui où elle insère la ligne qui la nomme |
| `SKILLS_CLONE_TIMEOUT_SECONDS` | `120` | Limite la durée de chaque requête HTTP d'un clonage. Sans elle, un dépôt distant qui ne répond plus bloque le clonage indéfiniment et laisse la compétence à l'état `Clonage` |

Le magasin contient un répertoire immuable par révision, et une révision n'est plus jamais modifiée une fois publiée ; une récupération ne perturbe donc jamais un agent en train d'en charger une existante :

```
$SKILLS_DIR/<agent_skill_id>/<commit_sha>/
```

Il s'agit d'un **état durable, et non d'un cache** : une exécution reste liée à la révision avec laquelle elle a démarré. Effacer le répertoire empêche donc les exécutions existantes de charger leur compétence (HTTP 409 `SKILL_NOT_READY`) jusqu'à ce qu'un administrateur récupère à nouveau la compétence, et cette récupération rapporte le head actuel du dépôt, et non la révision figée. Sauvegardez-le ([Sauvegarde et restauration](./backup.md)) et donnez le même répertoire à chaque réplica du backend ([Mise à l'échelle horizontale](./scaling.md)).

## Bases de connaissances {#knowledge-bases}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `KNOWLEDGE_SOURCE_MAX_BYTES` | `20971520` (20 Mio) | Taille maximale d'un document importé dans une [base de connaissances](../guides/knowledge-bases.md) et d'une page web récupérée pour celle-ci. Un import plus volumineux est refusé dès qu'il dépasse cette limite |
| `KNOWLEDGE_INGEST_CHUNK_CHARS` | `40000` | Nombre de caractères d'une source que le LLM lit à la fois. Une source plus longue est lue par parties successives. Réduisez cette valeur pour un modèle à petite fenêtre de contexte |
| `KNOWLEDGE_FETCH_TIMEOUT_SECONDS` | `30` | Durée que peut prendre, par requête, la récupération d'une source de type page web |

Les sources et les pages sont stockées dans la base de données, comme les fichiers de session, et ne nécessitent donc aucun volume dédié. La lecture d'une source appelle le LLM configuré pour les agents ([Configuration du LLM](../getting-started/llm-configuration.md)), plusieurs fois pour un document volumineux.

## Fichiers de session {#session-files}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `SESSION_FILE_MAX_BYTES` | `20971520` (20 Mio) | Taille maximale d'un fichier joint à une [session du workflow](../guides/workflow-executions.md#files-in-the-session). Un import est refusé dès qu'il dépasse cette limite ; un corps plus volumineux n'est donc jamais conservé en entier |
| `SESSION_FILES_MAX_TOTAL_BYTES` | `209715200` (200 Mio) | Taille cumulée de tout ce que contient une session. Les fichiers ne sont supprimés qu'à la suppression de leur exécution ; c'est donc cette valeur qui borne une session de longue durée |

Les fichiers de session sont stockés dans la base de données et non sur le disque : ils ne nécessitent ni répertoire dédié, ni volume partagé entre réplicas, ni autre étape de sauvegarde que celle de la base de données ([Sauvegarde et restauration](./backup.md)). Relever ces limites augmente la part de la base de données qu'une exécution peut occuper, ainsi que la mémoire consommée par un seul import ou téléchargement, car les octets sont lus en entier.

## Gestion des secrets {#secret-management}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `SECRET_ENCRYPTION_KEY` | — | Clé Fernet utilisée pour chiffrer les [secrets](../guides/secrets.md) `local` avant leur stockage |
| `SECRET_KEY_FILE` | `.secret_key` | Chemin du fichier de clé sur le disque, à côté du fichier de base de données SQLite. Sous `docker compose`, il s'agit de `/var/lib/a2flow/secret-key/.secret_key`, porté par le volume nommé `secret-key` que partagent le backend et le worker d'e-mails |

La clé de chiffrement est déterminée à la première utilisation, dans cet ordre :

1. `SECRET_ENCRYPTION_KEY`, qui doit être une clé Fernet valide.
2. Le fichier de clé indiqué par `SECRET_KEY_FILE`.
3. À défaut, une clé est générée et enregistrée dans ce fichier, et un WARNING est consigné.

**Sauvegardez la clé.** Sa perte rend indéchiffrables tous les secrets locaux stockés, et cette même clé protège la clé de signature de la [CA d'approbation](../architecture/approvals.md).

Il n'existe aucune variable d'environnement pour HashiCorp Vault : le Vault propre à un tenant est défini par son administrateur dans [Paramètres du tenant](../guides/users-and-groups.md#tenant-vault), l'adresse du Vault global par un super administrateur dans [Paramètres système](../guides/system-settings.md#global-vault), et l'[identifiant de chaque tenant pour ce Vault](../guides/users-and-groups.md#global-vault-credential) sur la page du tenant. L'adresse du Vault propre à un tenant subit les mêmes contrôles SSRF que les autres URL fournies par les utilisateurs et doit donc être publique. L'adresse du Vault global en est exemptée, car seul un super administrateur peut la définir et un Vault se trouve généralement sur une adresse privée.

## Outils MCP et approbations {#mcp-tools-and-approvals}

Chaque appel d'outil MCP doit présenter un certificat X.509 de courte durée émis pour la tâche qui l'effectue, accordé lorsque l'[approbation](../guides/approvals.md#human-approval) de la tâche l'est, ou lorsque démarre une tâche pour laquelle aucune approbation n'a été demandée. La racine de signature est générée à la première utilisation et stockée chiffrée avec la même clé que les secrets locaux : il n'y a donc rien à configurer ici pour que la fonctionnalité marche.

| Variable | Valeur par défaut | Ce qu'elle borne |
|---|---|---|
| `MCP_TOOL_CERT_TTL_SECONDS` | `3600` | Durée de validité du certificat d'une tâche, c'est-à-dire la fenêtre pendant laquelle elle peut appeler ses outils |
| `MCP_TOOL_CERT_SIGNATURE_WINDOW_SECONDS` | `60` | Tolérance de décalage d'horloge pour la signature de preuve de possession qui accompagne chaque appel relayé |
| `MCP_CA_COMMON_NAME` / `MCP_CA_VALIDITY_DAYS` | `A2Flow MCP Approval CA` / `3650` | Sujet et durée de vie de la racine générée. Lues uniquement lors de la première génération de la racine ; les modifier ensuite n'a aucun effet sur une racine existante |
| `MCP_REGISTRY_URL` | `https://registry.modelcontextprotocol.io` | URL de base du registre dans lequel cherche la boîte de dialogue [Parcourir le registre](../guides/mcp-servers.md#registering-from-the-mcp-registry) |
| `MCP_ELICITATION_TIMEOUT_SECONDS` | `900` | Durée pendant laquelle un appel d'outil attend que l'initiateur de l'exécution réponde à la [confirmation](../guides/workflow-executions.md#mcp-server-confirmations) d'un serveur MCP avant que la question n'expire. L'initiateur vient de reprendre la tâche : cette limite ne concerne donc qu'une question laissée sans suite |
| `AGENT_TURN_TIMEOUT_SECONDS` | `3600` | Durée maximale d'un tour d'agent dans une exécution, attente comprise. Gardez-la bien au-dessus de `MCP_ELICITATION_TIMEOUT_SECONDS`, car un tour dont l'appel d'outil attend une personne reste en cours |

## Proxy MCP {#mcp-sandbox}

Un serveur MCP enregistré n'est pas du code d'A2Flow : il s'exécute donc [à un autre endroit](../architecture/mcp-gateway-and-proxy.md#the-sandbox) que l'agent et ses secrets. Le déploiement Docker Compose met tout cela en place ; un déploiement qui assemble lui-même ses conteneurs le configure ici.

Si ces variables ne sont pas définies, comme lors d'une simple exécution locale, l'agent atteint lui-même les serveurs MCP, dans son propre processus. C'est pratique pour le développement, mais ce n'est pas souhaitable dans un environnement où n'importe qui peut enregistrer un serveur.

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `MCP_PROXY_URL` | non définie | Emplacement du proxy. C'est sa définition qui fait sortir les serveurs MCP du processus de l'agent |
| `MCP_PROXY_SERVER_NAME` / `MCP_PROXY_PORT` | `mcp-proxy` / `8443` | Nom par lequel le proxy est atteint et port sur lequel il écoute. Le nom fait partie de son certificat : les deux extrémités doivent donc s'accorder |
| `MCP_PROXY_TLS_DIR` | un répertoire à côté de l'application | Emplacement où l'agent publie ce dont le proxy a besoin pour s'identifier. Le proxy lit le même répertoire, en lecture seule |
| `MCP_BACKEND_TLS_DIR` | un répertoire à côté de l'application | Emplacement où l'agent conserve sa *propre* clé. Volontairement distinct du répertoire ci-dessus : rien de ce qui s'exécute dans le proxy ne doit pouvoir la lire |
| `MCP_TRANSPORT_CERT_VALIDITY_DAYS` | `365` | Durée de vie de ces éléments. Ils sont réémis automatiquement lorsqu'il reste moins de 30 jours et ne demandent donc aucune attention |
| `MCP_SANDBOX_DIR` | non définie | Emplacement du répertoire personnel de chaque tenant pour les [lancements de serveurs en bac à sable](../architecture/mcp-gateway-and-proxy.md#per-launch-sandbox) : les paquets téléchargés par les serveurs d'un tenant y sont conservés, à raison d'un répertoire par tenant. Si elle est définie, chaque serveur démarré localement s'exécute dans son propre bac à sable ; le proxy refuse de démarrer sans elle. Elle n'est pas définie lors d'une simple exécution locale, où les serveurs démarrent sans bac à sable |

## E-mails de notification {#notification-email}

Ce sont les mêmes valeurs que celles modifiées dans l'interface d'administration sous [Paramètres système](../guides/system-settings.md). Elles peuvent être définies depuis l'environnement, de sorte qu'un déploiement puisse embarquer sa configuration de messagerie au lieu d'en faire une étape manuelle.

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `APP_BASE_URL` | — | URL de base à laquelle les utilisateurs accèdent à ce déploiement dans un navigateur, p. ex. `https://a2flow.example.com`. Elle sert à construire les liens directs des e-mails de notification envoyés ; sans elle, les messages partent sans lien de retour |
| `SMTP_ENABLED` | `false` | Interrupteur général de l'envoi d'e-mails. Doit valoir explicitement `true` ; il n'est jamais déduit de la définition des autres variables |
| `SMTP_HOST` / `SMTP_PORT` | — / `587` | Relais auquel remettre les messages. Un simple nom d'hôte interne convient ici : il est transmis au client SMTP et non récupéré comme une URL |
| `SMTP_SECURITY` | `starttls` | `none`, `starttls` ou `ssl` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | — | Identifiants SMTP AUTH. Le mot de passe n'est jamais stocké que sous forme chiffrée, n'est jamais journalisé et n'est renvoyé par aucune réponse d'API |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | — | Adresse de l'expéditeur, requise dès que l'envoi est activé, et nom d'affichage facultatif qui l'accompagne |

Contrairement à tout le reste de cette page, ces valeurs ne sont pas relues à chaque utilisation : elles sont écrites dans l'unique enregistrement de paramètres. Elles obéissent donc à leurs propres règles :

- **Elles sont réappliquées à chaque démarrage**, et pas seulement au premier : changer le mot de passe d'un relais revient donc à redéployer.
- **Seules les variables effectivement définies sont écrites** : en laisser une non définie préserve la valeur stockée, y compris ce qu'un administrateur a configuré manuellement dans l'interface.
- **Une valeur mal formée est consignée sous forme d'avertissement et entièrement ignorée.** Un port incorrect, une adresse non valide ou `SMTP_ENABLED=true` sans hôte laissent la configuration stockée intacte ; l'application démarre quand même.

Comme l'indicateur d'activation est distinct, l'hôte et les identifiants d'un relais peuvent être préparés lors d'un déploiement, et l'envoi activé lors d'un déploiement ultérieur.

## File d'envoi des e-mails {#outgoing-email-queue}

Voici les réglages de la file qui se vide vers le relais ; consultez [La file d'envoi](../guides/notifications.md#the-delivery-queue) pour son comportement. Aucun n'a besoin d'être défini pour un déploiement normal.

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `EMAIL_WORKER_IN_PROCESS` | `true` | Indique si le processus d'API exécute aussi le worker qui vide la file, de sorte que `uvicorn main:app` envoie à lui seul les e-mails. Définissez-la sur `false` lorsque vous exécutez un processus worker dédié ; consultez [Organisation des processus](./deployment.md#process-layout). Laisser les deux actifs est sans danger, mais sans intérêt : un verrou consultatif élit exactement un expéditeur dans tout le déploiement |
| `EMAIL_SEND_RATE_PER_SECOND` | `5.0` | Messages par seconde remis au relais ; le worker marque une pause de `1 / rate` avant chaque envoi. Réduisez cette valeur pour rester sous la limite d'un relais plus strict |
| `EMAIL_QUEUE_BATCH_SIZE` / `EMAIL_QUEUE_POLL_INTERVAL_SECONDS` | `20` / `5.0` | Nombre de messages pris en charge par une passe, et durée de sommeil du worker lorsque la file est vide. L'intervalle d'interrogation est le délai d'envoi minimal d'une notification produite pendant que le worker dort |
| `EMAIL_MAX_ATTEMPTS` | `9` | Nombre de tentatives d'envoi avant qu'un message ne devienne une lettre morte. Le délai entre tentatives passe par 15 s, 30 s, 1 min, 2 min et ainsi de suite, plafonné à une heure : la valeur par défaut permet donc de tenir environ une heure d'indisponibilité du relais. Un échec que le relais signale comme définitif est abandonné dès la première tentative, quelle que soit cette valeur |
| `EMAIL_SENT_RETENTION_DAYS` | `30` | Durée de conservation des messages envoyés avant que le worker ne les purge. Ils constituent un historique de ce qui est parti, et non un état de la file. Les lettres mortes ne sont jamais purgées |

## Agent {#agent}

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `EXECUTION_MAX_PARALLEL_SESSIONS` | `4` | Nombre maximal de sessions dans lesquelles une exécution travaille en même temps : sa session principale, plus les sessions de branche créées lorsque son graphe de tâches se ramifie. Une fois la limite atteinte, une tâche prête attend sa session au lieu d'en créer une autre. `1` désactive la création de sessions de branche. Au moins `1` |
| `ROLE_DESCRIPTION` | Une description générique d'assistant | Texte de rôle autour duquel est construit le prompt système de l'agent, avec les règles du workflow et le schéma d'interface |
| `SESSION_RUNNER_CONCURRENCY` | `4` | Nombre de tours qu'un réplica exécute en même temps pour le compte d'une exécution : lancements et reprises après la décision d'une approbation. Chacun est une conversation active avec le modèle : cette valeur borne donc les appels au modèle d'un réplica pour les exécutions que personne ne suit. Au moins `1` |
