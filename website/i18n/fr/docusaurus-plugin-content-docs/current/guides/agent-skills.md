---
title: Compétences d'agent
sidebar_position: 6
---

# Compétences d'agent

Une compétence d'agent, c'est ce qu'un agent sait faire, conservé dans un dépôt Git. A2Flow en tient un catalogue : chaque enregistrement désigne un dépôt, qu'A2Flow clone et dont il maintient le clone à jour.

Ouvrez **Compétences d'agent** dans la barre latérale d'administration pour gérer le catalogue.

![Machine à états d'une compétence d'agent : une fois enregistrée, elle est clonée en arrière-plan, puis devient prête ou en échec ; une récupération permet de réessayer depuis l'un ou l'autre état, et une compétence prête permet de générer un nouveau workflow.](./img/agent-skills-lifecycle.svg#gh-light-mode-only)
![Machine à états d'une compétence d'agent : une fois enregistrée, elle est clonée en arrière-plan, puis devient prête ou en échec ; une récupération permet de réessayer depuis l'un ou l'autre état, et une compétence prête permet de générer un nouveau workflow.](./img/agent-skills-lifecycle-dark.svg#gh-dark-mode-only)

Une compétence n'est utilisable qu'une fois qu'elle a publié une révision. D'ici là, générer ou exécuter un workflow à partir d'elle est refusé.

## Contenu d'un enregistrement de compétence {#what-a-skill-record-holds}

| Champ | Remarques |
|---|---|
| **Nom** | Le nom sous lequel la compétence apparaît partout ailleurs. |
| **URL du dépôt** | Le dépôt à cloner. |
| **Chemin du dépôt** | L'emplacement de la compétence dans le dépôt, quand elle ne se trouve pas à la racine. |
| **Référence** | Facultatif. Un nom de branche ou de tag auquel rattacher chaque clonage et chaque récupération. S'il reste vide, c'est la branche par défaut du dépôt qui est utilisée. |
| **Description** | Texte libre. |
| **Nom d'utilisateur d'authentification** / **Mot de passe d'authentification** | Pour un dépôt privé : voir ci-dessous. |
| **Étiquettes** | Les [étiquettes](./tags.md) qui servent à classer la compétence. |

## État et révision {#status-and-revision}

La liste et les pages de détail affichent deux informations d'état, qui n'ont pas le même sens :

| Colonne | Ce qu'elle indique |
|---|---|
| **État** | Le résultat du *dernier* clonage ou de la dernière récupération : `Clonage`, `prêt`, ou `échec` avec le motif. |
| **Révision** | La révision actuellement publiée. Une compétence n'est exécutable qu'une fois cette valeur définie. |

Les deux sont volontairement indépendantes : une récupération qui échoue n'efface **pas** la révision publiée, et une compétence qui fonctionnait continue donc de fonctionner avec sa révision. Seuls l'état et l'erreur changent.

## Récupérer {#pulling}

**Récupérer** clone à nouveau le dépôt à la **Référence** configurée, ou sur la branche par défaut si aucune n'est définie. C'est ainsi qu'une compétence intègre les changements en amont, et qu'un enregistrement ayant échoué est retenté après correction de l'URL ou des identifiants. Le déplacement de l'extrémité d'une branche ou d'un tag est pris en compte à la récupération suivante.

Un dépôt qui contient un **lien symbolique**, où que ce soit dans son arborescence, est refusé : le clonage ou la récupération échoue avec un motif qui nomme le lien, et aucune révision n'en est publiée. Remplacez le lien par une copie du fichier vers lequel il pointe.

Chaque révision publiée est conservée tant que quelque chose en a besoin, et une exécution de workflow reste rattachée à la révision avec laquelle elle a démarré : une récupération ne change donc jamais ce que suit une exécution en cours. L'emplacement du stockage et sa durée de conservation sont traités dans la [référence de configuration](../operations/configuration.md#agent-skill-store).

## Dépôts privés {#private-repositories}

Les identifiants ne se saisissent pas dans le formulaire de la compétence. Enregistrez-les une fois pour toutes sous forme de [secret](./secrets.md), puis faites pointer la compétence vers l'une de ses entrées :

1. Renseignez **Nom d'utilisateur d'authentification**. La valeur par défaut est `x-access-token`, qui convient à un jeton d'accès personnel GitHub ; indiquez un vrai nom de compte pour les hôtes qui l'exigent.
2. Choisissez le **secret** dans la première liste déroulante de **Mot de passe d'authentification**, puis, dans la seconde, une **Clé d'entrée** de ce secret. La valeur de cette entrée sert de mot de passe lors du clonage du dépôt.

Un **Mot de passe d'authentification** nécessite une **URL du dépôt** commençant par `https://`. Avec `http://`, l'enregistrement est rejeté, car le mot de passe traverserait le réseau sans chiffrement.

Les deux types de secret sont proposés. Pour un secret de type Vault, les clés d'entrée sont lues en direct depuis Vault, car elles ne sont pas stockées localement.

La référence est stockée sous la forme d'un nom et d'une clé, et résolue au moment du clonage. Supprimer ou renommer le secret par la suite n'échoue donc pas sur-le-champ : c'est la récupération suivante qui échoue, et le motif est consigné sur la compétence. La page de détail n'abandonne pas en silence une référence qui ne se résout plus : celle-ci reste sélectionnée, marquée `(introuvable)`, avec un avertissement. C'est à vous de décider de l'effacer.

## Générer un workflow à partir d'une compétence {#generating-a-workflow-from-a-skill}

La colonne Actions de chaque ligne propose **Générer un workflow**, et la page de détail d'une compétence offre la même action sous forme de bouton à icône dans son en-tête. Les deux ouvrent la même boîte de dialogue, et les deux restent désactivés tant que la compétence n'a pas publié de révision. Voir [Générer un workflow](./workflows.md#generating-a-workflow).

## Consulter SKILL.md {#viewing-skillmd}

L'en-tête de la page de détail d'une compétence comporte un bouton à icône **Voir SKILL.md**. Il ouvre une boîte de dialogue qui affiche le fichier d'instructions de la compétence, tel qu'il est écrit dans son dépôt. Comme **Générer un workflow**, il reste désactivé tant que la compétence n'a pas publié de révision, car le fichier n'existe qu'une fois le clonage réussi. Contrairement aux actions d'écriture ci-dessus, il reste accessible à un lecteur qui n'a pas le rôle Développeur.
