---
title: Secrets
sidebar_position: 9
---

# Secrets

Un secret est un **ensemble nommé d'entrées clé/valeur** — la même forme que celle du [moteur KV de HashiCorp Vault](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2), où un chemin contient une table de clés et de valeurs. Les identifiants qui vont ensemble, comme un ID de clé d'accès AWS et sa clé d'accès secrète, résident dans un seul secret sous forme de deux entrées plutôt que dans deux secrets distincts.

Ouvrez **Secrets** dans la barre latérale d'administration pour les gérer. Chaque enregistrement comporte un **Nom**, une **Description** facultative, ses [étiquettes](./tags.md) et un type.

## Où un secret est utilisé {#where-a-secret-is-used}

![Organigramme montrant l'entrée d'un secret référencée soit dans les en-têtes et variables d'environnement d'un serveur MCP, soit comme mot de passe d'authentification du dépôt d'une compétence d'agent.](./img/secrets-usage.svg#gh-light-mode-only)
![Organigramme montrant l'entrée d'un secret référencée soit dans les en-têtes et variables d'environnement d'un serveur MCP, soit comme mot de passe d'authentification du dépôt d'une compétence d'agent.](./img/secrets-usage-dark.svg#gh-dark-mode-only)

- **[Serveurs MCP](./mcp-servers.md)** — toute valeur d'en-tête ou de variable d'environnement peut intégrer `${secret:name/key}`, développé à la connexion.
- **[Compétences d'agent](./agent-skills.md)** — le **Mot de passe d'authentification** d'une compétence est une référence à une entrée, choisie dans des listes déroulantes plutôt que saisie.

Une entrée se désigne toujours par **`name/key`**. La clé est requise même lorsque le secret ne contient qu'une seule entrée — un nom seul désigne une table, pas une valeur : un `${secret:name}` sans clé échoue donc à la résolution au lieu d'être transmis comme chaîne littérale.

## Les deux types {#the-two-types}

| | **Local (chiffré)** | **HashiCorp Vault** |
|---|---|---|
| **Ce qui est stocké** | Les entrées elles-mêmes, chaque valeur étant chiffrée | Uniquement une référence KV v2 — **Point de montage Vault** et **Chemin Vault** |
| **Provenance des valeurs** | Le stockage chiffré | Lues en direct depuis Vault à chaque résolution |
| **Ce qu'affiche la page de détail** | Toutes les clés stockées, avec une valeur vide | Le point de montage et le chemin |
| **Modification d'une entrée** | Laissez la valeur vide pour la conserver, saisissez-la de nouveau pour la remplacer, supprimez la ligne pour supprimer l'entrée | Dans Vault |

Les valeurs ne sont **jamais renvoyées**, quel que soit le type — ni en clair, ni sous forme chiffrée —, ce qui explique que la page de détail du type local affiche les clés avec des valeurs vides. Seules les clés sont lisibles, afin qu'un sélecteur puisse les lister : pour un secret local, elles proviennent de la table stockée ; pour un secret Vault, elles sont lues dans Vault à ce moment-là.

Un secret Vault est lu dans le Vault **de son propre tenant**, que l'administrateur du tenant connecte dans les [Paramètres du tenant](./users-and-groups.md#tenant-vault). Un tenant qui n'en a pas lit le [Vault global](./system-settings.md#global-vault) avec un [identifiant qui lui est propre](./users-and-groups.md#global-vault-credential), dont les stratégies Vault décident de ce qu'il peut lire. Sans l'un ni l'autre, les secrets de type Vault ne peuvent pas être résolus. La clé qui chiffre les secrets locaux se configure une fois pour toutes via la [référence de configuration](../operations/configuration.md#secret-management).

## Renommer et supprimer {#renaming-and-deleting}

Les secrets sont référencés **par leur nom** et résolus à la demande. Renommer ou supprimer un secret encore référencé n'échoue pas au moment de la modification : c'est l'utilisation suivante qui échoue, en nommant le secret introuvable. Une [compétence d'agent](./agent-skills.md) dont la référence est devenue obsolète consigne le motif dans son propre enregistrement à sa prochaine récupération.

Une référence est toutefois vérifiée lorsqu'elle est enregistrée. Lorsque vous enregistrez un serveur MCP dont les en-têtes ou l'environnement nomment un secret, que vous lancez une **Exécution de test** sur un script ou que vous enregistrez le **Mot de passe d'authentification** d'une compétence, le secret doit exister et vous devez pouvoir l'ouvrir. Un secret qu'une [étiquette de contrôle d'accès](./tags.md#access-control-tags) vous masque est rejeté exactement comme un secret manquant. Il en va de même lorsque vous modifiez un enregistrement qui référence déjà un tel secret, même si vous ne changez qu'un autre champ.
