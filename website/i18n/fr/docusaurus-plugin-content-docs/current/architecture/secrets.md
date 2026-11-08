---
title: Stockage des secrets
sidebar_position: 8
---

# Stockage des secrets

Un [secret](../guides/secrets.md) est un ensemble nommé d'entrées clé/valeur, et chaque référence désigne exactement une entrée : `${secret:name/key}` dans les en-têtes ou l'environnement d'un serveur MCP, un nom et une clé pour une compétence d'agent. Les références sont conservées par nom et **résolues uniquement au moment de leur utilisation** : rien de ce qui a besoin d'un identifiant n'en stocke jamais.

![Organigramme montrant une référence de secret qui se divise selon le type : local déchiffre la valeur stockée, vault la lit en direct depuis Vault, et les deux alimentent une connexion à un serveur MCP ou le clonage d'un dépôt de compétence.](./img/secrets-resolution.svg#gh-light-mode-only)
![Organigramme montrant une référence de secret qui se divise selon le type : local déchiffre la valeur stockée, vault la lit en direct depuis Vault, et les deux alimentent une connexion à un serveur MCP ou le clonage d'un dépôt de compétence.](./img/secrets-resolution-dark.svg#gh-dark-mode-only)

| | **Local** | **HashiCorp Vault** |
|---|---|---|
| Ce qui est stocké | Les entrées elles-mêmes, chaque valeur étant chiffrée | Uniquement une référence KV v2 : un point de montage et un chemin |
| D'où viennent les valeurs | Du stockage chiffré | De Vault, lues au moment de la résolution |
| Comment les clés sont listées | D'après la table stockée, sans rien déchiffrer | Lues dans Vault à ce moment-là |
| Ce qu'un client peut relire | Les clés uniquement, jamais une valeur, ni en clair ni chiffrée | Les clés uniquement |

## Secrets locaux {#local-secrets}

Les valeurs sont chiffrées avec une clé unique propre au déploiement. Les clés des entrées restent en clair à côté d'elles, ce qui permet à un sélecteur de les lister sans rien déchiffrer. Aucune valeur n'est jamais renvoyée à un client, sous quelque forme que ce soit : c'est pourquoi la page de détail d'un secret local affiche ses clés avec des valeurs vides.

La clé de chiffrement est résolue une fois par processus : elle est prise dans l'environnement si elle y est définie, sinon lue dans un fichier de clé, sinon générée à la première utilisation et écrite dans ce fichier, avec un avertissement dans le journal.

**Sauvegardez cette clé.** Sa perte rend indéchiffrables tous les secrets locaux stockés. Et comme cette même clé protège la clé de signature de l'autorité qui émet les [certificats d'outils](./approvals.md), sa perte empêche aussi d'émettre ou de vérifier des certificats, ce qui bloque tous les appels d'outils MCP. Ces deux éléments figurent dans la [référence de configuration](../operations/configuration.md#secret-management).

## Secrets HashiCorp Vault {#hashicorp-vault-secrets}

Pour un secret reposant sur Vault, A2Flow ne stocke aucune valeur, seulement le point de montage et le chemin où les lire. Les valeurs comme la liste des clés sont récupérées en direct à chaque besoin : la rotation d'une valeur dans Vault prend donc effet sans toucher à A2Flow.

Un secret est toujours lu par le Vault du tenant auquel il appartient. Il s'agit du Vault **propre** au tenant lorsque son administrateur en a connecté un dans les [Paramètres du tenant](../guides/users-and-groups.md#tenant-vault), et sinon du [Vault global](../guides/system-settings.md#global-vault) configuré par un Super administrateur, auquel le tenant se connecte avec [son propre identifiant](../guides/users-and-groups.md#global-vault-credential). L'un comme l'autre s'authentifie avec un jeton statique ou avec des identifiants AppRole ; un jeton AppRole est réutilisé jusqu'à ce que son bail soit presque expiré, puis renouvelé par une nouvelle connexion. Sur le Vault global, chaque tenant possède son propre identifiant : les tenants sont donc séparés par les stratégies Vault attachées à ces identifiants. Sans l'un ni l'autre, les secrets de type `vault` d'un tenant ne peuvent pas être résolus du tout.

## Où a lieu la résolution {#where-resolution-happens}

| Consommateur | Résolu lorsque |
|---|---|
| Les valeurs d'en-tête et d'environnement d'un serveur MCP | La [passerelle](./mcp-gateway-and-proxy.md) les développe pour la connexion que le proxy MCP ouvre vers ce serveur |
| Le mot de passe du dépôt d'une compétence d'agent | Le dépôt est cloné ou récupéré |

La résolution étant différée, renommer ou supprimer un secret encore référencé n'échoue pas au moment de la modification. C'est l'utilisation suivante qui échoue, en nommant le secret introuvable ; la raison sous-jacente reste dans le journal du serveur et n'est pas transmise à l'appelant.
