---
title: Serveurs MCP
sidebar_position: 7
---

# Serveurs MCP

Un serveur [MCP](https://modelcontextprotocol.io/) fournit des outils que l'agent peut appeler. Cette section en tient le registre : enregistrez-y un serveur, et ses outils pourront être liés aux modèles de tâches d'un workflow — voir [Outils MCP des tâches](./workflows.md#mcp-tools-for-tasks).

Ouvrez **Serveurs MCP** dans la barre latérale d'administration pour gérer le registre. Chaque enregistrement comporte un **Nom** unique, une **Description** facultative, ses [étiquettes](./tags.md) et un **Transport**, dont dépend le reste du formulaire.

## Transports {#transports}

| Transport | Champs | De quoi il s'agit |
|---|---|---|
| **Streamable HTTP** (par défaut) | **URL**, **En-têtes HTTP** | Un serveur distant. Les en-têtes accompagnent chaque requête — en général `Authorization: Bearer …`. Les serveurs uniquement SSE ne sont pas pris en charge. |
| **stdio** | **Commande**, **Arguments**, **Variables d'environnement** | Un serveur lancé comme processus enfant du backend, par exemple `npx` avec `["-y", "@modelcontextprotocol/server-everything"]`. `npx` et `uvx` sont tous deux disponibles. |
| **Script** | **Langue**, **Source**, **Paquets**, **Variables d'environnement** | Du code Python ou JavaScript que vous écrivez vous-même. Chacune de ses fonctions publiques devient un outil — voir [Écrire un script](#writing-a-script). |

Changer le transport d'un serveur existant efface les champs de l'ancien transport, et un enregistrement qui mélange les formes — une URL sur un serveur stdio, une commande sur un serveur distant, du code source sur l'un ou l'autre — est refusé.

⚠️ **Enregistrer un serveur stdio revient à exécuter la commande choisie dans le conteneur du backend**, sous l'utilisateur non privilégié du conteneur. Cette opération exige le même rôle Développeur que toute autre écriture sur un serveur MCP. Les arguments sont transmis au processus sous forme de liste, jamais via un shell, et le processus enfant n'hérite que d'un petit ensemble sûr de variables d'environnement, auxquelles s'ajoutent celles que vous configurez : les clés d'API et l'URL de base de données du backend lui restent invisibles.

## Écrire un script {#writing-a-script}

Un serveur de script transforme vos propres fonctions en outils sans publier de paquet. Choisissez **Script** comme **Transport**, sélectionnez une **Langue**, puis collez le code dans **Source**.

**Source** est un éditeur de code. Il colore le code selon la **Langue** sélectionnée, numérote les lignes et indente avec **Tab** — appuyez d'abord sur **Échap** pour passer au champ suivant avec **Tab**. Au fil de la saisie, il souligne les problèmes sur place ; survolez un soulignement pour lire ce qui ne va pas.

| Soulignement | Signification | Exemples |
|---|---|---|
| Rouge, ondulé | Erreur de syntaxe : le script ne peut pas s'exécuter | Une parenthèse non fermée, un mot-clé mal orthographié |
| Ambre, ondulé | Probablement une erreur | Aucune fonction ne deviendrait un outil ; une fonction Python sans docstring ou un paramètre sans annotation de type ; un import extérieur à la bibliothèque standard alors que **Paquets** est vide ; une fonction JavaScript sans `description` |
| Couleur d'accent, ondulé | Une remarque | Une fonction JavaScript sans `inputSchema` |

Les soulignements sont de simples conseils et n'empêchent jamais d'enregistrer ; la vérification à l'enregistrement est décrite plus bas.

| | Python | JavaScript |
|---|---|---|
| Fonctions qui deviennent des outils | Toute fonction définie au premier niveau dont le nom ne commence pas par `_`. Les fonctions importées ne sont pas exposées. | Toute fonction exportée (`export function`, `export async function`) dont le nom ne commence pas par `_`. L'export par défaut n'est pas exposé. |
| Nom de l'outil | Le nom de la fonction | Le nom de l'export |
| Description | La docstring | La propriété `description` de la fonction |
| Arguments | Lus dans les annotations de type : `str`, `int`, `float`, `bool`, `list`, `dict`, `Literal[...]` et `X \| None`. Un paramètre d'un autre type, ou sans type, accepte n'importe quelle valeur. | La propriété `inputSchema` de la fonction, un JSON Schema. Sans elle, l'outil accepte n'importe quels arguments. |
| Appel de l'outil | Arguments passés par nom | Un seul objet contenant les arguments |
| Ce que reçoit l'agent | La valeur de retour : une chaîne telle quelle, tout le reste en JSON | La valeur de retour : une chaîne telle quelle, tout le reste en JSON |

```python
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
```

```js
export function add({ a, b }) {
  return a + b;
}
add.description = "Add two numbers.";
add.inputSchema = {
  type: "object",
  properties: { a: { type: "number" }, b: { type: "number" } },
  required: ["a", "b"],
};
```

Quelques règles valent pour les deux langages :

- La bibliothèque standard est toujours disponible : les modules de Python, ou les modules `node:` intégrés à Node.js. Tout le reste doit être listé sous [Paquets](#adding-packages).
- Une erreur levée par une fonction parvient à l'agent sous la forme d'un appel d'outil en échec, avec son message.
- La sortie de `print()` ou de `console.log()` va dans le journal du serveur, pas vers l'agent.
- Les **Variables d'environnement** se lisent avec `os.environ["NAME"]` ou `process.env.NAME`, et peuvent utiliser les espaces réservés décrits dans [Garder les identifiants hors de l'enregistrement](#keeping-credentials-out-of-the-record).
- **Source** contient au maximum 30 000 caractères.
- Du code Python comportant une erreur de syntaxe est refusé à l'enregistrement, avec le numéro de ligne. Le JavaScript n'est pas vérifié à l'enregistrement : [testez-le](#testing-a-script) avant d'enregistrer pour repérer un script impossible à charger.
- Un script qui ne se charge pas — paquet impossible à installer, erreur de syntaxe ou erreur levée au premier niveau — démarre quand même. Chaque appel à l'un de ses outils échoue alors avec l'erreur qui l'a arrêté, et [la vérification de ses outils](#checking-a-servers-tools) indique que le serveur est inutilisable.

⚠️ Un script s'exécute au même endroit qu'un serveur stdio, avec les mêmes restrictions.

### Ajouter des paquets {#adding-packages}

Un script qui communique avec un autre service a généralement besoin de la bibliothèque cliente de ce service — `boto3` pour AWS, par exemple. Listez-les sous **Paquets**, un par ligne, et importez-les dans **Source** comme d'habitude.

| Langue | Format d'un paquet | Exemples |
|---|---|---|
| Python | Un nom issu de PyPI, éventuellement avec une version | `boto3`, `boto3==1.40.0`, `requests>=2.32` |
| JavaScript | Un nom issu du registre npm, éventuellement avec `@version` | `is-number`, `@aws-sdk/client-s3@3` |

```python
import boto3


def list_buckets() -> list[str]:
    """List the S3 buckets the configured credentials can see."""
    return [b["Name"] for b in boto3.client("s3").list_buckets()["Buckets"]]
```

- Les paquets sont installés la première fois que le script démarre avec cette liste, ce qui peut prendre un certain temps ; les démarrages suivants réutilisent la copie installée. Les scripts qui listent exactement les mêmes paquets partagent une seule copie.
- Un paquet impossible à installer — nom mal orthographié, version inexistante — empêche le script de se charger. [Charger les outils](#testing-a-script) affiche l'erreur de l'installateur.
- Un serveur compte au maximum 20 paquets, chacun d'au plus 200 caractères et commençant par une lettre, un chiffre ou `@`.
- L'installation exige que le registre de paquets soit joignable depuis l'endroit où s'exécutent les scripts. Pour installer depuis un index privé, définissez la variable propre à l'installateur sous **Variables d'environnement** : `UV_INDEX_URL` pour Python, `NPM_CONFIG_REGISTRY` pour JavaScript.

## Tester un script {#testing-a-script}

Le panneau **Exécution de test**, situé sous **Variables d'environnement**, exécute le script tel qu'il figure dans le formulaire, sans l'enregistrer. Servez-vous-en pour repérer un script qui ne se charge pas avant qu'un agent ne tente de l'utiliser.

1. Cliquez sur **Charger les outils**. Le script démarre avec les valeurs de **Source**, **Paquets** et **Variables d'environnement** présentes dans le formulaire.
2. Choisissez un outil dans **Outil**. **Arguments** se remplit avec tous les arguments que l'outil déclare, chacun à `null`.
3. Modifiez **Arguments** — un objet JSON — puis cliquez sur **Exécuter**.

| Ce que vous voyez | Signification |
|---|---|
| Une liste d'outils | Le script s'est chargé ; voici les outils qu'il exposera |
| Du texte rouge à la place de la liste d'outils | Le script n'a pas pu se charger. Le texte est l'erreur qui l'a arrêté |
| **Ce script n'expose aucun outil.** | Le script s'est chargé, mais aucune fonction ne deviendrait un outil |
| La sortie de l'outil dans **Sortie** | L'appel a réussi |
| Du texte rouge dans **Sortie** | L'outil a levé une erreur ; le texte est son message |
| **Les arguments doivent être un objet JSON.** ou **JSON non valide : …** | **Arguments** n'est pas un objet JSON ; rien n'a été exécuté |

Les espaces réservés de **Variables d'environnement** sont développés comme pour un serveur enregistré : une exécution de test atteint donc les mêmes services avec les mêmes identifiants. Une exécution de test est un véritable appel : ce que fait l'outil se produit réellement.

## Garder les identifiants hors de l'enregistrement {#keeping-credentials-out-of-the-record}

⚠️ Les valeurs littérales des en-têtes et des variables d'environnement sont stockées **en clair** et réaffichées sur la page de détail. Plutôt que de saisir directement un identifiant, référencez une entrée d'un [secret](./secrets.md) enregistré :

| Espace réservé | Où il fonctionne | Exemple |
|---|---|---|
| `${secret:name/key}` | Toute valeur d'en-tête ou de variable d'environnement | `Authorization: Bearer ${secret:github/token}`<br/>`AWS_ACCESS_KEY_ID: ${secret:aws-credentials/AWS_ACCESS_KEY_ID}` |
| `${gcp-token:name/key}` | Comme `${secret:…}`, pour une entrée contenant un JSON d'identifiants Google Cloud | `Authorization: Bearer ${gcp-token:gcp-credentials/GOOGLE_CREDENTIALS_JSON}` |
| `${env:NAME}` | Une entrée de **Arguments**, désignant l'une des variables d'environnement de ce serveur | `--token ${env:API_KEY}` |

Les espaces réservés ne sont développés qu'à la connexion : l'identifiant n'apparaît donc jamais dans l'enregistrement stocké.

`${env:NAME}` est développé après le `${secret:…}` de la variable d'environnement concernée, ce qui permet de réutiliser une valeur issue d'un secret comme option de ligne de commande — pour un lanceur qui l'attend en argument au lieu de la lire dans l'environnement du processus. `NAME` doit être une clé de **Variables d'environnement** ; une référence à une clé absente, y compris une référence restée après la suppression de cette clé, est refusée à l'enregistrement.

### Serveurs MCP Google Cloud {#google-cloud-mcp-servers}

Les serveurs MCP gérés par Google — celui de GKE, par exemple — n'acceptent pas les clés d'API. Chaque requête doit porter un jeton d'accès OAuth 2.0 associé à une identité Google Cloud, et comme un jeton ne vit qu'une heure, on ne peut pas non plus le coller dans un secret. `${gcp-token:name/key}` résout ce problème : au lieu de la valeur de l'entrée, il se développe en un **jeton d'accès récent généré à partir de celle-ci**, renouvelé automatiquement à son expiration. L'entrée contient le JSON d'identifiants, sous l'une des deux formes suivantes :

| Identifiant | Comment l'obtenir | Portée du jeton |
|---|---|---|
| Une **clé de compte de service** | Créez un compte de service, accordez-lui **MCP Tool User** ainsi que ce dont ses outils ont besoin, puis téléchargez une clé JSON | `cloud-platform` |
| Un **ID client et un secret OAuth** | Créez un client OAuth (application de bureau), téléchargez son JSON, puis exécutez une fois sur votre propre machine `gcloud auth application-default login --client-id-file=<ce JSON> --scopes=https://www.googleapis.com/auth/cloud-platform` et connectez-vous. Collez le contenu du fichier `application_default_credentials.json` obtenu | Ce à quoi vous avez consenti |

Dans les deux cas, collez le JSON complet comme une seule entrée d'un [secret](./secrets.md) et référencez-la depuis l'en-tête `Authorization` du serveur, comme dans l'exemple ci-dessus. Chaque appel d'outil s'exécute sous cette unique identité, quelle que soit la personne qui a lancé le workflow. Un identifiant mal formé, ou que Google n'accepte plus, fait échouer la connexion de la même manière qu'une référence `${secret:…}` orpheline.

## Enregistrer depuis le registre MCP {#registering-from-the-mcp-registry}

Le bouton **Parcourir le registre** de la page de liste ouvre une boîte de dialogue de recherche alimentée par le [registre MCP](https://registry.modelcontextprotocol.io/) officiel.

1. Recherchez par nom. Les résultats ne listent que les serveurs qu'A2Flow peut enregistrer : ceux dotés d'un point de terminaison Streamable HTTP et ceux publiés sous forme de paquet npm ou PyPI qu'il peut lancer via stdio.
2. Choisissez-en un. Le formulaire de création s'ouvre, prérempli avec les informations de connexion et les clés d'en-tête ou d'environnement requises par le serveur.
3. Renseignez les valeurs secrètes et enregistrez.

La correspondance entre un paquet et une commande de lancement est établie au mieux : vérifiez-la donc avant d'enregistrer. Le registre interrogé par A2Flow peut être remplacé via la [référence de configuration](../operations/configuration.md#mcp-tools-and-approvals).

## Vérifier les outils d'un serveur {#checking-a-servers-tools}

Les formulaires de modèle de tâche interrogent un serveur sur les outils qu'il propose — nom, description et schéma d'entrée — mais uniquement pour le serveur que vous avez choisi, jamais pour tout le registre à la fois. Un serveur impossible à joindre ou à lancer l'indique à la place de sa liste d'outils.

## Supprimer un serveur {#deleting-a-server}

Un serveur ne peut pas être supprimé tant qu'une tâche ou un modèle de tâche reste lié à l'un de ses outils. Retirez d'abord ces liaisons.
