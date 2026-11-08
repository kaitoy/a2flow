---
title: Journaux d'audit
sidebar_position: 12
---

# Journaux d'audit

Les Journaux d'audit rassemblent les quatre registres qu'A2Flow tient de ce qu'il a fait pour votre compte : les appels d'outils de ses agents, les sessions où une personne a agi en tant qu'une autre, l'autorité portée par chaque approbation accordée et les e-mails envoyés. Chacun fonctionne en ajout seul : rien dans cet écran ne modifie ni ne supprime un enregistrement, et c'est ce qui en fait une preuve.

Ouvrez **Journaux d'audit** dans la barre latérale d'administration. Quatre onglets surmontent le tableau :

| Onglet | Une ligne correspond à |
|---|---|
| **Appels d'outils** | Une décision de la passerelle MCP sur un appel d'outil |
| **Emprunts d'identité** | Une session où un administrateur a agi en tant qu'un autre utilisateur |
| **Certificats** | L'autorité derrière les appels d'outils de chaque tâche |
| **E-mails** | Un message de notification mis en file d'attente pour envoi |

Chaque liste se comporte comme tous les autres tableaux d'administration (tri, filtres, sélecteur de colonnes, pagination) : voir [Interface d'administration](./admin-ui.md#the-list-screen). Cliquer sur la première cellule d'une ligne ouvre une page de détail en lecture seule, qui affiche les longues valeurs tronquées dans le tableau.

## Qui peut y accéder {#who-sees-it}

La section n'est affichée que pour les rôles **Administrateur** et **Super administrateur**. Toutes les autres personnes obtiennent un écran d'accès refusé, et la section n'apparaît pas dans leur barre latérale.

C'est plus strict que la plupart des sections, dont la lecture reste ouverte à toute personne connectée. Ces listes couvrent toutes les exécutions, tous les comptes et tous les messages du tenant : l'accès au niveau des participants, qui vous permet de voir les enregistrements de *votre propre* exécution, ne suffit donc pas ici. Les vues plus restreintes restent à leur place : les appels d'outils d'une exécution figurent toujours sur sa page [Appels d'outils](./workflow-executions.md#tool-invocations), et le certificat d'une approbation sur l'[approbation](./approvals.md) elle-même. Seule cette liste montre toutefois aussi les certificats accordés aux tâches pour lesquelles personne n'a été sollicité.

Un Super administrateur voit le tenant choisi dans le sélecteur de tenant, et peut sélectionner **Tous les tenants** pour les parcourir tous à la fois. Dans ce mode, chaque liste gagne une colonne **Tenant**, placée le plus à gauche.

## Appels d'outils {#tool-invocations}

Les appels d'outils qui ont atteint la passerelle MCP, et ce qu'elle a décidé pour chacun : ceux marqués `autorisé` sont partis vers le serveur en amont, ceux marqués `refusé` ont été bloqués par une règle.

| Colonne | Remarques |
|---|---|
| **Outil** / **Serveur** | Ce qui a été appelé, et où |
| **Décision** | `autorisé` ou `refusé` |
| **Motif du refus** | La raison du refus d'un appel, dans les termes mêmes de la règle |
| **Exécution du workflow** | L'exécution à laquelle appartient l'appel, avec un lien vers elle |
| **Approbation** / **Certificat** | Le certificat présenté par l'appel, et l'approbation qui l'a accordé le cas échéant |
| **Empreinte des arguments** | Une empreinte de ce que l'appel demandait |

Les arguments eux-mêmes ne sont jamais stockés : seule l'est l'empreinte que couvre la signature présentée, ce qui permet de revérifier plus tard un appel enregistré sans conserver ce qu'il transportait. La page de détail montre l'empreinte complète, la signature et l'instant exact de la signature.

Les appels à un outil [simulé](./tool-mocks.md) n'apparaissent pas ici, quelle qu'en soit l'issue, car un appel simulé n'atteint aucun serveur. C'est dans la transcription de la discussion de l'exécution qu'on peut les examiner.

## Emprunts d'identité {#impersonations}

Une ligne par session où un administrateur a agi en tant qu'un autre utilisateur, du moment où il a commencé jusqu'à celui où il a cessé. Une ligne sans **Terminée le** correspond à une session encore ouverte, marquée **Actif**.

| Colonne | Remarques |
|---|---|
| **Auteur de l'emprunt d'identité** | Qui a agi, avec un lien vers son compte |
| **Utilisateur cible** | Le compte au nom duquel cette personne a agi, avec un lien vers lui |
| **État** | **Actif** tant que la session est ouverte, **Terminée** une fois qu'elle est close |
| **Commencée le** / **Terminée le** | Le début et la fin de la session |

Les lignes sont rattachées au tenant du compte **dont l'identité est empruntée**, et non à celui de la personne qui agit. C'est délibéré : un Super administrateur n'appartient à aucun tenant, si bien qu'un rattachement à la personne qui agit masquerait ses sessions à tous les tenants, alors que ce sont précisément celles qu'un administrateur a le plus besoin de voir. Voir [Emprunt d'identité](../concepts/impersonation.md).

## Certificats {#certificates}

Ce que chaque tâche a réellement été autorisée à appeler. Tout appel d'outil présente un certificat : cette liste est donc le registre complet de l'autorité sur les outils accordée puis consommée, y compris pour les tâches pour lesquelles personne n'a été sollicité.

Une tâche reçoit son certificat à l'un de deux moments, que la colonne **Autorité** indique :

| Autorité | Émis | Accordé par |
|---|---|---|
| **Approbateur** | lorsqu'une [approbation](./approvals.md) sur la tâche a été accordée | l'approbateur qui l'a accordée |
| **Initiateur de l'exécution** | lorsque la tâche a été marquée **en cours** sans qu'aucune approbation n'ait été demandée | la personne qui a lancé l'exécution |

| Colonne | Remarques |
|---|---|
| **Numéro de série** | Identifie le certificat ; c'est la valeur que la liste Appels d'outils affiche pour les appels qui l'ont présenté |
| **Autorité** | **Approbateur** ou **Initiateur de l'exécution** : l'origine de l'autorisation |
| **Accordé par** | La personne à qui elle est attribuée |
| **Approbation** | L'approbation pour laquelle il a été émis, avec un lien vers elle. Vide pour une autorisation de l'initiateur de l'exécution, qui ne repose sur aucune approbation |
| **État** | **En cours**, ou **Révoqué** une fois l'autorité consommée |
| **Outils autorisés** | Les outils qu'accorde ce certificat |
| **Pas avant** / **Pas après** | La période pendant laquelle il est valide |
| **Révoqué le** / **Motif de révocation** | Quand et pourquoi il a cessé de compter |

**Outils autorisés** est relu dans le certificat émis lui-même et non dans une copie séparée : ce que montre cet écran ne peut donc jamais différer de ce qui a réellement été autorisé, même si les liaisons des tâches de l'exécution ont été réécrites par la suite. Aucune clé n'est jamais affichée ni téléchargeable.

## E-mails {#emails}

Les messages de notification qu'A2Flow a mis en file d'attente pour envoi, et ce qu'il en est advenu.

| Colonne | Remarques |
|---|---|
| **À** / **Objet** | À qui le message était adressé, et à quel sujet |
| **État** | `en attente`, `envoi en cours`, `envoyé` ou `échec` |
| **Tentatives** | Le nombre de tentatives d'envoi effectuées |
| **Envoyé le** | Le moment où il est parti |
| **Dernière erreur** | La raison de l'échec de la dernière tentative |

Un message qui n'a pas pu être remis passe à `échec` et est **conservé** plutôt que supprimé : une notification jamais arrivée reste ainsi visible, avec son motif enregistré. Le corps du message est figé au moment où la notification est produite, et non composé à l'envoi : la page de détail l'affiche en entier, exactement tel qu'il a été remis.

Un Super administrateur peut supprimer une ligne `envoyé` ou `échec`, mais pas un Administrateur, et une ligne encore `en attente` ou `envoi en cours` est refusée à l'un comme à l'autre, car le processus d'envoi des e-mails est peut-être en train de la traiter. Voir [Notifications](./notifications.md) pour savoir comment ces messages sont mis en file d'attente, et [Paramètres système](./system-settings.md) pour le serveur de messagerie par lequel ils passent.
