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

Définissez `APP_PORT` dans `.env` pour publier l'application sur un autre port de l'hôte ; l'URL de base de l'application le suit automatiquement. Pour que l'application s'ouvre à une autre adresse — un nom d'hôte, par exemple —, définissez plutôt `APP_BASE_URL` dans `.env` avec cette adresse, comme `http://a2flow.internal:3000`. L'application reste publiée sur `APP_PORT` : si cette adresse comporte un port, alignez `APP_PORT` dessus.

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
| **keycloak** | Uniquement avec `--profile keycloak` — voir [Essayer l'authentification unique avec Keycloak](#keycloak) |

Seul l'ingress — ou Caddy à sa place, avec `compose.https.yml` — (et, avec leurs profils, l'interface d'OpenBao et Keycloak) est accessible depuis l'extérieur ; les autres conteneurs communiquent entre eux sur le réseau interne de Docker.

Le premier démarrage prend plus de temps que les suivants : les images sont construites, le schéma de la base de données est créé et le proxy MCP attend que le backend lui remette le certificat dont il a besoin avant d'accepter quoi que ce soit.

## Servir en HTTPS {#https}

Ajouter `compose.https.yml` place [Caddy](https://caddyserver.com/) devant l'ingress. Il devient le seul point d'entrée, sur les ports 80 et 443, obtient un certificat pour l'adresse de `APP_BASE_URL` et redirige le HTTP en clair vers HTTPS. Une adresse `https://` rend aussi les cookies de connexion sécurisés, et l'[authentification unique](../guides/single-sign-on.md) en dérive son **URI de redirection**.

```bash
echo APP_BASE_URL=https://a2flow.example.com >> .env
docker compose -f compose.yml -f compose.https.yml up --build
```

Ouvrez l'adresse que vous avez définie. Elle ne doit comporter aucun port : seuls 80 et 443 sont publiés, et Caddy refuse de démarrer sur une adresse qui en comporte un. La suite dépend du nom d'hôte :

| `APP_BASE_URL` | Certificat | Avant de commencer |
|---|---|---|
| Un nom d'hôte public, comme `https://a2flow.example.com` | Obtenu auprès de Let's Encrypt et renouvelé automatiquement | Faites pointer le DNS du nom vers cet hôte et rendez les ports 80 et 443 accessibles depuis Internet |
| Non défini (`https://localhost`) | Émis par une autorité de certification que Caddy crée pour lui-même | Rien, mais le navigateur affiche un avertissement de certificat tant que vous ne faites pas confiance à cette autorité (ci-dessous) |

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

## Essayer l'authentification unique avec Keycloak {#keycloak}

[Keycloak](https://www.keycloak.org/) est un fournisseur d'identité open source. La pile peut en démarrer un à côté d'A2Flow, déjà configuré pour lui, ce qui permet d'essayer l'[authentification unique](../guides/single-sign-on.md) sans votre propre IdP.

```bash
docker compose --profile keycloak up --build
```

Keycloak est publié à l'adresse [http://keycloak.localhost:8180](http://keycloak.localhost:8180), et sa console d'administration s'ouvre avec `admin` / `admin` (définissez `KEYCLOAK_ADMIN_PASSWORD` dans `.env` pour changer le mot de passe). Chrome, Edge et Firefox trouvent `keycloak.localhost` d'eux-mêmes ; dans un autre navigateur, ajoutez d'abord la ligne `127.0.0.1 keycloak.localhost` à votre fichier hosts. Keycloak ne conserve rien quand le conteneur est recréé : il repart de la configuration ci-dessous, et les modifications faites dans sa console sont perdues.

Il démarre avec ceci déjà en place :

| Élément | Valeur |
|---|---|
| Realm | `a2flow` |
| URL de l'émetteur | `http://keycloak.localhost:8180/realms/a2flow` |
| ID client | `a2flow` |
| Secret client | `a2flow-dev-secret` |
| URI de redirection | `http://localhost:3000` (ou votre `APP_BASE_URL`) et `https://localhost`, chacune suivie du chemin de retour d'A2Flow |
| Claim de groupes | `groups` |
| Utilisateurs | `alice` dans le groupe `a2flow-admins`, `bob` dans le groupe `a2flow-users`. Tous deux ont le mot de passe `password` |

### 1. Connecter A2Flow {#1-connect-a2flow}

1. Connectez-vous à A2Flow en tant que `admin` et ouvrez **Paramètres du tenant** dans la barre latérale d'administration.
2. Dans la section **Authentification unique**, renseignez **URL de l'émetteur**, **ID client** et **Secret client** avec les valeurs du tableau ci-dessus, cochez **Activer l'authentification unique** et enregistrez.
3. Ouvrez **Groupes d'utilisateurs**, ouvrez un groupe — ou créez-en un — qui porte les rôles voulus, saisissez `a2flow-admins` dans **Groupe IdP** et enregistrez.

### 2. Se connecter {#2-sign-in}

1. Déconnectez-vous. Sur l'écran de connexion, saisissez `default` dans **Tenant** et appuyez sur **Se connecter avec SSO**.
2. Sur la page de connexion de Keycloak, connectez-vous en tant que `alice` / `password`. Vous revenez dans A2Flow, connecté en tant qu'Alice, membre du groupe de l'étape 1.
3. Essayez aussi `bob` : son seul groupe, `a2flow-users`, n'est associé à aucun groupe d'utilisateurs, donc la connexion est refusée — jusqu'à ce que vous l'associiez à l'un d'eux.

Keycloak parle aussi SAML, mais A2Flow se connecte uniquement via OpenID Connect.
