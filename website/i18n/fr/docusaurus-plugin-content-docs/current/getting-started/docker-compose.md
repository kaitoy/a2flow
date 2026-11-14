---
title: Lancer avec Docker Compose
sidebar_position: 2
---

# Lancer avec Docker Compose

Vous pouvez aussi construire et démarrer l'ensemble de la pile avec Docker Compose ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)) :

```bash
echo GOOGLE_API_KEY=your_google_api_key_here > .env
docker compose up --build
```

Ouvrez [http://localhost:3000](http://localhost:3000). Les données de la base sont conservées dans le volume `pgdata` d'un redémarrage à l'autre.

Définissez `APP_PORT` dans `.env` pour publier l'application sur un autre port de l'hôte ; le paramètre `CORS_ORIGINS` du backend s'y aligne automatiquement.

## Ce qui démarre {#what-comes-up}

| Conteneur | Rôle |
|---|---|
| **db** | PostgreSQL 17. Tout ce qu'A2Flow enregistre se trouve ici |
| **backend** | L'agent et l'API |
| **worker** | Envoie les [e-mails de notification](../guides/notifications.md#the-delivery-queue) mis en file d'attente par le backend |
| **mcp-proxy** | Exécute les [serveurs MCP](../guides/mcp-servers.md) que vous enregistrez — voir [pourquoi il est séparé](../architecture/mcp-gateway-and-proxy.md#the-sandbox) |
| **ingress** | Le point d'entrée auquel s'adresse votre navigateur. Il transmet les requêtes des écrans au frontend et les requêtes d'API directement au backend |
| **frontend** | Les écrans que vous utilisez |
| **caddy** | Uniquement avec `compose.https.yml` — voir [Servir en HTTPS](#https) |
| **openbao** | Uniquement avec `--profile openbao` — voir [Essayer les secrets Vault avec OpenBao](#openbao) |

Seul l'ingress — ou Caddy à sa place, avec `compose.https.yml` — (et, avec le profil, l'interface d'OpenBao) est accessible depuis l'extérieur ; les autres conteneurs communiquent entre eux sur le réseau interne de Docker.

Le premier démarrage prend plus de temps que les suivants : les images sont construites, le schéma de la base de données est créé et le proxy MCP attend que le backend lui remette le certificat dont il a besoin avant d'accepter quoi que ce soit.

## Servir en HTTPS {#https}

Ajouter `compose.https.yml` place [Caddy](https://caddyserver.com/) devant l'ingress. Il devient le seul point d'entrée, sur les ports 80 et 443, obtient un certificat et redirige le HTTP en clair vers HTTPS. Le backend passe en même temps aux réglages HTTPS : cookies sécurisés, origine HTTPS, et **URL de base de l'application** dans les [Paramètres système](../guides/system-settings.md), à partir de laquelle l'[authentification unique](../guides/single-sign-on.md) construit son **URI de redirection**.

```bash
echo APP_DOMAIN=a2flow.example.com >> .env
docker compose -f compose.yml -f compose.https.yml up --build
```

Ouvrez `https://` suivi de votre `APP_DOMAIN`. La suite dépend de ce nom :

| `APP_DOMAIN` | Certificat | Avant de commencer |
|---|---|---|
| Un nom d'hôte public | Obtenu auprès de Let's Encrypt et renouvelé automatiquement | Faites pointer le DNS du nom vers cet hôte et rendez les ports 80 et 443 accessibles depuis Internet |
| Non défini (`localhost`) | Émis par une autorité de certification que Caddy crée pour lui-même | Rien, mais le navigateur affiche un avertissement de certificat tant que vous ne faites pas confiance à cette autorité (ci-dessous) |

Pour que le navigateur fasse confiance à `https://localhost`, copiez le certificat racine de l'autorité et ajoutez-le aux certificats racines de confiance de votre système d'exploitation ou de votre navigateur :

```bash
docker compose -f compose.yml -f compose.https.yml cp caddy:/data/caddy/pki/authorities/local/root.crt .
```

Les certificats et l'autorité locale sont conservés dans le volume `caddy-data`. Gardez-le : le supprimer fait émettre de nouveaux certificats, et un certificat racine auquel vous faisiez déjà confiance ne correspond plus.

## Essayer les secrets Vault avec OpenBao {#openbao}

[OpenBao](https://openbao.org/) est un fork open source de Vault auquel A2Flow se connecte exactement comme à HashiCorp Vault. La pile peut en démarrer une instance à côté d'A2Flow, ce qui permet d'essayer les [secrets de type Vault](../guides/secrets.md) sans disposer de votre propre Vault.

```bash
docker compose --profile openbao up --build
```

OpenBao conserve ses données dans le même PostgreSQL qu'A2Flow, elles survivent donc aux redémarrages, et il se descelle tout seul à chaque démarrage. La clé qui sert au descellement se trouve dans le volume `openbao-unseal` : sauvegardez-la avec `pgdata`, car les données sont illisibles sans elle. Cette configuration sert à essayer l'intégration, pas à la production.

### 1. Initialiser OpenBao (premier démarrage uniquement) {#1-initialize-openbao-first-start-only}

```bash
docker compose exec openbao bao operator init -recovery-shares=1 -recovery-threshold=1
```

Notez le **Initial Root Token** affiché : il n'apparaît qu'une seule fois.

### 2. Créer un AppRole pour A2Flow {#2-create-an-approle-for-a2flow}

L'interface ne permet pas de créer un rôle AppRole : cette étape se fait donc en ligne de commande. Remplacez `<root-token>` par le jeton obtenu à l'étape 1 :

```bash
docker compose exec -e BAO_TOKEN=<root-token> openbao sh -c '
  bao secrets enable -path=secret kv-v2
  bao auth enable approle
  printf "path \"secret/data/a2flow/*\" { capabilities = [\"read\"] }" | bao policy write a2flow -
  bao write auth/approle/role/a2flow token_policies=a2flow token_ttl=1h
  bao read -field=role_id auth/approle/role/a2flow/role-id; echo
  bao write -f -field=secret_id auth/approle/role/a2flow/secret-id; echo'
```

Les deux dernières lignes affichent le **role id** et le **secret id**. La stratégie n'autorise A2Flow à lire que les chemins situés sous `a2flow/`.

### 3. Créer un secret dans l'interface d'OpenBao {#3-create-a-secret-in-the-openbao-ui}

1. Ouvrez [http://localhost:8200/ui](http://localhost:8200/ui) et connectez-vous avec la méthode **Token** et le jeton racine. OpenBao ne conserve pas une connexion par jeton racine au rechargement de la page : déplacez-vous donc en cliquant plutôt qu'en saisissant des URL.
2. Ouvrez le moteur **secret/** et choisissez **Create secret**.
3. Saisissez `a2flow/demo` comme chemin, ajoutez les entrées `username` et `password`, puis enregistrez.

### 4. Connecter A2Flow {#4-connect-a2flow}

1. Connectez-vous à A2Flow en tant que `root`. Dans **Paramètres système**, définissez **Adresse du Vault global** sur `http://openbao:8200` et enregistrez.
2. Ouvrez **Tenants**, puis **Default**. Cochez **Connexion au Vault global**, choisissez **AppRole** comme **Méthode d'authentification Vault**, saisissez le role id et le secret id obtenus à l'étape 2, puis enregistrez.
3. Connectez-vous en tant qu'`admin`. Dans **Secrets**, créez un secret de type **HashiCorp Vault** avec `secret` pour **Point de montage Vault** et `a2flow/demo` pour **Chemin Vault**.

Référencez-le comme n'importe quel autre secret, par exemple sous la forme `${secret:<name>/password}` dans une variable d'environnement d'un [serveur MCP](../guides/mcp-servers.md). Partout où vous sélectionnez le secret, ses clés `username` et `password` sont listées : elles sont lues dans OpenBao à ce moment-là, ce qui montre que la connexion fonctionne.

Définissez `OPENBAO_PORT` dans `.env` pour publier l'interface d'OpenBao sur un port de l'hôte autre que 8200. A2Flow lui-même y accède toujours à l'adresse `http://openbao:8200` sur le réseau interne.
