---
title: Mise à l'échelle horizontale
sidebar_position: 3
---

# Mise à l'échelle horizontale

Le frontend ne possède aucun état propre et ne conserve rien entre les requêtes : il se met donc à l'échelle librement. Lorsque le proxy inverse achemine `/api/*` directement vers le backend, comme le décrit [Déploiement](./deployment.md), les flux de discussion ne passent même pas par lui. Tout ce qui suit concerne le backend.

## Ce qu'exige l'exécution de plusieurs réplicas {#what-running-more-than-one-replica-requires}

| Exigence | Pourquoi |
|---|---|
| **PostgreSQL** | SQLite n'admet qu'un seul rédacteur et un seul processus. Tous les réplicas partagent une même base de données, qui sert aussi à les coordonner |
| **Un `SKILLS_DIR` partagé** | Chaque réplica doit monter le même [magasin de compétences d'agent](./configuration.md#agent-skill-store) (ReadWriteMany). Une exécution reste liée à la révision de compétence avec laquelle elle a démarré, et n'importe quel réplica peut servir sa requête suivante |
| **Aucun proxy de pooling en mode transaction** | Consultez [Pooling de connexions](#connection-pooling) ci-dessous |
| **Un `MCP_PROXY_TLS_DIR` partagé** | Chaque réplica y écrit et y lit les éléments qui l'identifient auprès du [proxy MCP](../architecture/mcp-gateway-and-proxy.md#the-sandbox), et le proxy lit le même répertoire. Un réplica qui aurait le sien émettrait des éléments que le proxy n'a jamais vus |
| Sessions persistantes | Non nécessaires. Le verrou consultatif décrit plus bas remplit le rôle qu'on attendrait d'une affinité de routage |

Le proxy MCP suit sa propre logique de mise à l'échelle : il ne conserve rien entre les appels, hormis un cache de téléchargement, et ses réplicas n'ont donc besoin d'aucune coordination. Ils peuvent partager `MCP_SANDBOX_DIR` ou garder chacun le leur. Dimensionnez-le d'après le nombre d'appels d'outils simultanés, et non d'après le nombre de réplicas du backend.

## Un seul pilote par conversation {#one-driver-per-conversation}

Les écritures dans une conversation sont déjà sûres entre réplicas : le service de session pose un `SELECT ... FOR UPDATE` sur la ligne à laquelle il ajoute des données, pendant toute la transaction. Les ajouts sont donc sérialisés, et ni l'état de la conversation ni ses lignes d'événements ne peuvent être perdus.

Ce sont les lectures qui ont besoin d'aide. Le runtime de l'agent conserve une session en mémoire pendant toute la durée d'une invocation : les événements qu'un autre réplica ajoute pendant cet intervalle ne lui parviennent donc jamais, et le reste de l'exécution raisonne sur une conversation où ils manquent. Sérialiser les écritures ne peut pas y remédier ; seul le fait de limiter une session à un pilote à la fois le peut.

Chaque exécution d'agent (`POST /api/v1/workflow-executions/{id}/agent`, `POST /api/v1/workflows/{id}/agent`) prend donc un **verrou consultatif PostgreSQL de niveau session** et le conserve pendant tout le flux SSE :

![Diagramme de séquence de deux réplicas en concurrence pour exécuter la même session : le réplica 1 prend un verrou consultatif PostgreSQL et ouvre le flux pour le client A, tandis que la requête ultérieure du réplica 2 pour la même session est refusée avec une erreur 409 tant que le verrou est détenu, et le verrou n'est libéré que lorsque le flux du réplica 1 se termine.](./img/scaling-lock-race.svg#gh-light-mode-only)
![Diagramme de séquence de deux réplicas en concurrence pour exécuter la même session : le réplica 1 prend un verrou consultatif PostgreSQL et ouvre le flux pour le client A, tandis que la requête ultérieure du réplica 2 pour la même session est refusée avec une erreur 409 tant que le verrou est détenu, et le verrou n'est libéré que lorsque le flux du réplica 1 se termine.](./img/scaling-lock-race-dark.svg#gh-dark-mode-only)

Une seconde exécution simultanée de la même session est refusée avant l'envoi de tout en-tête SSE, au lieu de pouvoir diverger en silence. Des sessions différentes n'entrent jamais en concurrence, et le verrou est brièvement attendu avant tout abandon : un client qui interrompt un flux et réessaie aussitôt n'est donc pas rejeté pendant que l'exécution abandonnée se termine.

L'intervention humaine n'est pas affectée : un appel d'outil du frontend met fin à l'exécution et ferme le flux, ce qui libère le verrou, et l'approbation reprend sous la forme d'un *nouveau* tour, qui peut s'exécuter sur n'importe quel réplica.

Chaque réplica exécute aussi un **exécuteur de sessions** qui réalise les tours qu'aucun navigateur ne pilote : le lancement d'une exécution et sa reprise après une approbation. Il prend le même verrou sans attendre : une session déjà exécutée ailleurs est donc laissée à ce réplica, et il reprend un tour qu'un réplica arrêté a laissé inachevé. Le nombre de ces tours qu'un réplica exécute en même temps est défini par `SESSION_RUNNER_CONCURRENCY` (consultez la [référence de configuration](./configuration.md#agent)).

## Migrations de schéma pendant un déploiement {#schema-migrations-during-a-rollout}

Chaque réplica applique les migrations de schéma en attente à son démarrage et, sur une base de données vierge, crée aussi les comptes et les paramètres initiaux. Plusieurs réplicas déployés ensemble tenteraient tous de le faire en même temps ; ils passent donc chacun leur tour : le premier à démarrer effectue le travail, et les autres attendent qu'il ait terminé, jusqu'à dix minutes, avant de poursuivre sans rien avoir à faire. Un réplica qui attend encore passé ce délai s'arrête, et son orchestrateur le redémarre.

## Pooling de connexions {#connection-pooling}

Comme le verrou est de niveau session et non de niveau transaction, le déploiement ne doit placer aucun proxy de **pooling en mode transaction** (PgBouncer en mode `transaction` et la plupart des poolers PostgreSQL serverless) entre l'application et PostgreSQL. Le verrou ne survivrait pas d'une instruction à l'autre. Il en va de même pour les mises à jour en direct de la discussion : chaque processus backend garde une connexion ouverte pour être informé des tours écrits sur d'autres réplicas, de sorte qu'une discussion ouverte sur un réplica affiche en temps réel un tour exécuté sur un autre. Un pooling de niveau session ou une connexion directe est indispensable.

### Budget de connexions {#connection-budget}

Chaque processus backend ouvre des connexions à la base de données à partir de ces sources :

| Source | Connexions |
|---|---|
| Le pool qui sert les requêtes d'API | Jusqu'à `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` |
| Le pool de l'historique des conversations | Jusqu'à `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` |
| Chaque exécution d'agent en cours : une discussion ouverte dans un navigateur, ou un tour que le serveur exécute de lui-même (jusqu'à `SESSION_RUNNER_CONCURRENCY` en même temps) | 1 pendant la durée de l'exécution |
| L'expéditeur des e-mails de notification et les traitements d'arrière-plan tels que la récupération d'une compétence ou l'ingestion d'une base de connaissances | 1 chacun, le temps de leur fonctionnement |
| Les mises à jour en direct de la discussion provenant d'autres réplicas | 1, toujours ouverte |

Avec les valeurs par défaut, cela représente jusqu'à 30 connexions en pool par processus, plus une pour les mises à jour en direct de la discussion et une par exécution en cours. La valeur par défaut de `max_connections` de PostgreSQL est 100 : quatre ou cinq réplicas chargés peuvent donc l'atteindre. Avant d'ajouter des réplicas, augmentez `max_connections` sur le serveur, ou réduisez `DB_POOL_SIZE` et `DB_MAX_OVERFLOW` (consultez la [référence de configuration](./configuration.md#application-database)). Si cela ne suffit toujours pas, placez PgBouncer en mode **session** devant PostgreSQL.

## E-mails de notification {#notification-email}

Le worker d'envoi des e-mails ne demande aucune coordination de votre part : qu'il s'exécute dans les processus d'API ou dans un processus dédié, le verrou consultatif `email-queue` élit exactement un expéditeur dans tout le déploiement. Les réplicas n'envoient donc jamais en double et la limite de débit configurée reste exacte. Ajouter des réplicas du worker apporte du basculement, pas du débit ; consultez [Organisation des processus](./deployment.md#process-layout).
