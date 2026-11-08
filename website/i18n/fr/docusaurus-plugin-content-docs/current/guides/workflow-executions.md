---
title: Exécutions de workflows
sidebar_position: 4
---

# Exécutions de workflows

Une exécution est un déroulement d'un [workflow](./workflows.md). Elle conserve sa propre copie du nom, de la description, des tâches et des étiquettes du workflow : son historique reste ainsi fidèle à ce qui s'est réellement exécuté, même si le workflow d'origine est ensuite modifié ou supprimé.

Ouvrez **Exécutions de workflows** dans la barre latérale d'administration pour les parcourir. Contrairement aux autres sections, une exécution est un historique et non un enregistrement à modifier : il n'y a donc pas de formulaire de modification, et ses écrans servent soit à montrer l'exécution, soit à vous y faire participer. Sa colonne et son champ **Étiquettes** sont en lecture seule pour la même raison : voir [Étiquettes des exécutions de workflow et des approbations](./tags.md#execution-and-approval-tags).

| Écran | Comment y accéder | Contenu |
|---|---|---|
| Liste **Exécutions de workflows** | Barre latérale d'administration → Exécutions de workflows | Toutes les exécutions, avec leur état, et les actions de chaque ligne |
| **Session du workflow** | L'action Ouvrir la session du workflow d'une ligne | La discussion dans laquelle se déroule l'exécution : y participer, la suivre, y répondre |
| **Tâches du workflow** | Le lien vers les tâches d'une ligne | Les tâches de l'exécution et leurs états, en lecture seule, sous forme de Tableau ou de Graphe |
| **Appels d'outils** | L'en-tête de détail de l'exécution | Les appels d'outils MCP effectués par l'exécution et la décision prise pour chacun |

**Simulé** signale une exécution qui a simulé au moins un de ses outils avec un [simulacre d'outil](./tool-mocks.md).

Le [menu **Colonnes**](./admin-ui.md#choosing-columns) propose deux autres colonnes, masquées au départ. **Workflow** affiche le workflow parent de l'exécution sous son nom actuel, avec un lien vers lui : le nom propre à chaque ligne est un instantané figé au démarrage de l'exécution, et cette colonne permet donc de voir comment ce workflow s'appelle aujourd'hui. **Brouillon** affiche une coche pour une [exécution de test](./workflows.md#running-a-workflow), c'est-à-dire lancée depuis un workflow encore à l'état `brouillon`, ou depuis les [modifications non publiées](./workflows.md#trying-the-edits-out) d'un workflow à l'état `modifié`. Dans les deux cas, elle a mis à l'épreuve une conception que personne n'avait approuvée : elle est donc exclue des [métriques d'exploitation](../operations/metrics.md) ; la colonne sert de filtre Oui/Non pour les masquer.

La page de détail d'une exécution affiche sa **Version** : la version publiée du workflow dont elle a copié les tâches, par exemple `v3`, ou `—` pour une exécution de test, qui a exécuté une conception qu'aucune version n'a enregistrée. Voir [Historique des versions et retour en arrière](./workflows.md#version-history).

## État de l'exécution {#run-status}

![Diagramme d'états montrant une exécution qui démarre à l'état en cours d'exécution, passe à planifié tant qu'elle ne fait qu'attendre l'heure prévue, revient à en cours d'exécution à la reprise, puis se termine à l'état terminé une fois toutes les tâches achevées sans échec, ou à l'état échec une fois toutes les tâches achevées avec au moins un échec.](./img/workflow-executions-status.svg#gh-light-mode-only)
![Diagramme d'états montrant une exécution qui démarre à l'état en cours d'exécution, passe à planifié tant qu'elle ne fait qu'attendre l'heure prévue, revient à en cours d'exécution à la reprise, puis se termine à l'état terminé une fois toutes les tâches achevées sans échec, ou à l'état échec une fois toutes les tâches achevées avec au moins un échec.](./img/workflow-executions-status-dark.svg#gh-dark-mode-only)

Une exécution démarre à l'état `en cours d'exécution` et se clôt dès qu'elle compte au moins une tâche et que toutes ses tâches ont atteint un état final : `terminé`, `échec` ou `ignoré`. Une exécution dont les tâches comportent un échec se termine à l'état `échec`. L'heure de fin est enregistrée à ce moment et aucune modification ultérieure ne la déplace ; une exécution sans aucune tâche reste `en cours d'exécution`. Ce sont ces chiffres que comptent les [métriques d'exploitation](../operations/metrics.md).

Tant qu'une exécution inachevée n'a rien d'autre à faire qu'attendre l'heure prévue (une tâche a demandé à attendre, sa session affiche **Planifiée jusqu'à …** et toutes les autres sessions sont inactives ou terminées), l'exécution affiche `planifié` au lieu de `en cours d'exécution`. Elle revient à `en cours d'exécution` dès qu'une session reprend, que l'heure soit venue ou que quelqu'un lui ait envoyé un message. Les [métriques d'exploitation](../operations/metrics.md) comptent une exécution à l'état `planifié` comme active, au même titre qu'une exécution à l'état `en cours d'exécution`.

Lorsqu'une tâche échoue, toute tâche qui l'attend encore, directement ou plus loin dans la chaîne, passe à `ignoré`, car elle ne peut plus s'exécuter : c'est ce qui permet à l'exécution de se terminer au lieu de rester bloquée sur une tâche qui ne démarrera jamais. Les tâches des branches qui ne dépendent pas de la tâche en échec ne sont pas affectées : une exécution peut donc rester `en cours d'exécution` un moment après un échec, jusqu'à ce qu'elles se terminent à leur tour.

## L'écran de session du workflow {#the-workflow-session-screen}

La session du workflow est la discussion dans laquelle se déroule une exécution. Elle s'ouvre sur le message de lancement de l'exécution, avec l'agent déjà au travail : l'exécution démarre dès sa création, que quelqu'un ouvre cet écran ou non.

![Diagramme de flux montrant la disposition de l'écran de session du workflow : la chronologie des tâches et les messages regroupés par tâche sont côte à côte, et les messages mènent à la zone de saisie de la discussion.](./img/workflow-executions-layout.svg#gh-light-mode-only)
![Diagramme de flux montrant la disposition de l'écran de session du workflow : la chronologie des tâches et les messages regroupés par tâche sont côte à côte, et les messages mènent à la zone de saisie de la discussion.](./img/workflow-executions-layout-dark.svg#gh-dark-mode-only)

### Qui la partage {#who-shares-it}

La discussion d'une exécution est **partagée par ses participants** ; elle n'est pas réservée à la personne qui l'a lancée :

| Qui | Ce qu'il obtient |
|---|---|
| L'**initiateur** qui a lancé l'exécution | Toute la conversation et la zone de saisie de la discussion |
| Un **approbateur désigné** de l'une de ses [approbations](./approvals.md) | La même conversation et le même état : approuver reprend l'exécution d'origine au lieu d'en démarrer une nouvelle, vide. Son approbation est la seule chose sur laquelle il peut agir : un formulaire de saisie affiché par l'agent pour toute autre étape, ou une [confirmation demandée par un serveur MCP](#mcp-server-confirmations), est en lecture seule pour lui, avec la mention « En attente de la réponse de l'initiateur. » en dessous |
| Un **Administrateur** du tenant | Une visibilité en lecture seule |
| Toute autre personne | Aucun accès |

Lorsqu'une approbation est adressée à un **groupe**, chaque membre détenant le rôle Approbateur est participant : l'accès à la discussion suit donc la composition du groupe. Ajouter une personne à un groupe d'approbateurs lui ouvre toutes les exécutions pour lesquelles ce groupe a été sollicité, et l'en retirer les lui referme. C'est la conséquence directe de « n'importe quel membre peut trancher » : décider est ce que l'accès à la discussion doit rendre possible. Un membre qui ne détient pas le rôle Approbateur n'obtient rien de son appartenance au groupe.

### Avatars des expéditeurs {#sender-avatars}

Comme plusieurs personnes écrivent dans une même discussion (le demandeur, les approbateurs et l'agent), chaque message porte un **avatar d'expéditeur**. Le survoler révèle le nom de l'expéditeur ; le badge de l'agent révèle le nom du workflow. Un clic sur un bouton à l'intérieur d'une surface interactive affichée est attribué de la même façon : l'avatar de l'utilisateur qui a agi apparaît à côté de cette surface une fois le clic traité.

### La chronologie des tâches {#the-task-timeline}

Une **chronologie des tâches** repliable occupe le bord gauche : les tâches de l'exécution dans l'ordre, chacune avec un badge numéroté coloré selon son état, celle en cours étant mise en évidence. La discussion enveloppe chaque suite de messages consécutifs d'une même tâche dans un **groupe de tâche**, avec un filet gauche coloré selon l'état et un titre numéroté correspondant au badge de la chronologie : la limite de chaque tâche se repère ainsi d'un coup d'œil.

Les deux sont liés dans les deux sens :

- Faire défiler la discussion met en évidence, dans la chronologie, la tâche située en haut de la zone visible.
- Survoler une entrée de la chronologie ou un groupe de la discussion met en évidence son équivalent.
- Cliquer sur une entrée de la chronologie fait défiler la discussion jusqu'au groupe de cette tâche.

### Mises à jour en direct {#live-updates}

Chaque participant qui suit l'exécution voit chaque réponse au fil de son écriture, quel que soit l'auteur du message qui l'a déclenchée, ainsi que les tours qu'A2Flow lance de lui-même, comme le lancement, la reprise après une approbation et la reprise d'une session qui attendait l'heure prévue. L'affichage ne suit les nouveaux messages vers le bas que si vous êtes déjà près du bas.

Un message que vous envoyez attend l'agent : tant que celui-ci travaille encore sur un tour, le message est refusé et vous pouvez le renvoyer une fois la réponse terminée. Une session en attente d'approbation n'accepte aucun message, car c'est la décision d'approbation qui la fait avancer. Une question envoyée à ce moment-là va à une [consultation](#consultations).

La [session de conception](./workflows.md#adjusting-the-task-templates) est elle aussi une discussion partagée, avec les mêmes avatars. Elle est partagée par les Développeurs du tenant plutôt que par les participants d'une exécution, et elle s'actualise d'elle-même toutes les quelques secondes au lieu d'afficher les réponses des autres au fil de leur écriture.

### Sessions de branche {#branch-sessions}

Lorsque le graphe des tâches de l'exécution se ramifie, A2Flow peut répartir l'exécution sur plusieurs sessions pour que les branches avancent ensemble : voir [Branches parallèles](../architecture/workflow-execution.md#parallel-branches). Une rangée d'onglets apparaît alors sous le fil d'Ariane, un par session, chacun indiquant son état :

| Onglet | Ce que c'est |
|---|---|
| **Principale** | La session dans laquelle l'exécution a démarré. Elle traite les jonctions et les tâches qui suivent une branche terminée |
| **Branche 1**, **Branche 2**, … | Une session de branche, créée par bifurcation lorsqu'une branche est devenue prête alors que sa session était occupée |
| **Consultation 1**, … | Une [consultation](#consultations), ouverte par une question posée pendant qu'une session attendait une approbation |

| État | Signification |
|---|---|
| En file d'attente | Un tour est sur le point de démarrer |
| En cours d'exécution | L'agent travaille |
| En attente d'une saisie | Un formulaire de saisie attend une réponse |
| En attente d'approbation | Une approbation demandée par cette session n'a pas encore été décidée |
| En attente de l'initiateur | La tâche suivante [posera des questions à l'initiateur](#mcp-server-confirmations) pendant son exécution : elle attend donc qu'il la reprenne depuis la discussion |
| Planifiée jusqu'à … | Une tâche doit attendre l'heure prévue ; la session reprend d'elle-même à l'heure affichée. Un message qui lui est envoyé la fait reprendre plus tôt |
| Inactive | Rien à faire pour l'instant ; la session attend sa prochaine tâche |
| Terminée | La session a terminé son travail. Une branche terminée laisse un résumé à la session principale |
| Erreur | Le dernier tour a échoué |

Cliquez sur un onglet pour ouvrir la discussion de cette session ; l'affichage suit la session sélectionnée et l'URL la conserve : un lien vers la page ouvre donc le même onglet. Une exécution qui ne se ramifie jamais et n'a aucune consultation n'affiche aucun onglet.

### Consultations {#consultations}

Une session en attente d'approbation n'accepte aucun message, mais la demande peut tout de même soulever des questions, par exemple ce que coûtera l'instance ou pourquoi cette cible a été choisie. Pendant l'attente de la session, une note au-dessus de la zone de saisie de la discussion indique qu'une question est adressée à une consultation.

1. Saisissez la question dans la discussion de la session en attente et envoyez-la.
2. Un onglet **Consultation** s'ouvre avec votre question, et l'agent y répond. Il part de tout ce que la session en attente savait jusqu'à la demande d'approbation, et peut aussi lire les [bases de connaissances](./knowledge-bases.md) liées au workflow. Il ne peut pas utiliser les outils des serveurs MCP : une question qui exige d'examiner à nouveau le système cible doit donc attendre que l'exécution se poursuive.
3. Continuez à poser vos questions dans cet onglet. Toutes les personnes qui partagent la discussion peuvent y écrire : l'approbateur et la personne qui a lancé l'exécution peuvent donc aussi discuter de la demande entre eux. Chaque message indique qui l'a envoyé.
4. Statuez sur l'approbation comme d'habitude. La décision clôt la consultation : son onglet passe à **Terminée** et n'accepte plus de messages.

| Une consultation | |
|---|---|
| Peut | Répondre à partir du contexte de la demande, des bases de connaissances liées, des tâches et approbations de l'exécution et des fichiers de la session |
| Ne peut pas | Utiliser un outil de serveur MCP, modifier une tâche, demander une approbation, programmer une attente ou ajouter un fichier |
| Laisse derrière elle | Rien dans l'exécution. La session en attente ne voit jamais ce qui y a été dit ; la conversation reste lisible dans son onglet |

Une autre question posée avant que la même approbation soit décidée va dans la même consultation.

### Réponses suggérées {#suggested-replies}

Lorsque l'agent s'arrête pour vous attendre (il a posé une question, demande une valeur ou a besoin d'un feu vert), une rangée de **réponses suggérées** apparaît au-dessus de la zone de saisie de la discussion : quelques réponses courtes qu'il anticipe, comme `Oui, allez-y` ou `Ignorer cette étape`.

| | |
|---|---|
| **Cliquer sur l'une d'elles** | Place ce texte dans la zone de saisie. Rien n'est envoyé : modifiez-le ou envoyez-le tel quel |
| **Pendant que l'agent travaille** | La rangée est masquée ; elle revient avec la prochaine question de l'agent |
| **Après votre réponse** | La rangée disparaît, et la question suivante apporte ses propres suggestions |
| **Après un rechargement** | La même rangée est là, pour chaque participant autorisé à envoyer |

Les suggestions sont ce que l'agent suppose que vous écririez, et non un menu des seules réponses autorisées : une question à réponses fixes est posée à la place sous forme de choix dans le message. Cette rangée est propre à la session du workflow ; la session de conception n'en a pas.

### Confirmations d'un serveur MCP {#mcp-server-confirmations}

Certains serveurs MCP s'arrêtent au milieu d'un appel d'outil pour demander quelque chose à une personne avant de continuer : Azure MCP Server, par exemple, demande un consentement avant chaque opération sur un secret Key Vault. Un tel outil est marqué comme **interrogeant l'initiateur** dans la conception du workflow : indiquez à l'agent de conception quel outil de quelle tâche pose des questions, lors de la génération du workflow ou dans sa session de conception. Un outil non marqué n'est pas autorisé à poser des questions, et son appel échoue au lieu d'attendre.

Une tâche qui utilise un outil marqué attend l'initiateur de l'exécution avant de démarrer, pour qu'il soit présent lorsque les questions arrivent :

1. Lorsque l'exécution atteint la tâche, sa session affiche **En attente de l'initiateur**, et l'initiateur reçoit une [notification](./notifications.md) `demande de saisie`. Aucun délai ne court entre-temps.
2. L'initiateur ouvre la discussion de l'exécution. Au-dessus de la zone de saisie, une note nomme la tâche, avec un bouton **Reprendre**. Les autres voient seulement que l'exécution attend l'initiateur.
3. **Reprendre** envoie un message au nom de l'initiateur, et la tâche démarre. Saisir lui-même n'importe quel message produit le même effet.
4. Chaque question apparaît dans la discussion sous forme de carte intitulée « *serveur* demande une confirmation », qui nomme l'outil en attente, avec un petit formulaire en dessous.


| | |
|---|---|
| **Qui répond** | L'initiateur de l'exécution uniquement. Les approbateurs et les Administrateurs voient la question avec « En attente de la réponse de l'initiateur. » en dessous |
| **Accepter** | Envoie les valeurs du formulaire. Leur signification dépend du serveur : le formulaire d'Azure MCP Server propose un choix entre **Approve** et **Reject** |
| **Décliner** | Refuse de répondre |
| **Annuler** | Écarte la question sans choisir |
| **Pendant l'attente** | Le tour de l'agent est toujours en cours : la zone de saisie reste donc désactivée |
| **Si personne ne répond** | La question expire, au bout de 15 minutes sauf [indication contraire du déploiement](../operations/configuration.md#mcp-tools-and-approvals), et le serveur est informé qu'elle a été écartée |

La carte appartient au tour qui a posé la question. Une fois ce tour terminé, c'est la ligne de l'appel d'outil dans la discussion qui consigne le résultat.

### Fichiers de la session {#files-in-the-session}

Une session du workflow contient des fichiers aussi bien que des messages. Joignez-en un avec le bouton **trombone** à côté de la zone de saisie, ou déposez-le n'importe où sur celle-ci : chaque fichier apparaît sous forme de puce au-dessus de la zone, et le × d'une puce le retire. Rien n'est envoyé tant que vous n'envoyez pas le message : retirer une puce écarte donc simplement ce fichier, qui n'atteint jamais l'exécution.

Le message que vous envoyez nomme ce qui l'accompagne : la transcription montre donc toujours la pièce jointe après un rechargement. L'agent est informé des fichiers séparément, par le serveur, et il peut :

| Il peut | Il ne peut pas |
|---|---|
| Lister les fichiers de la session | Modifier un fichier joint par quelqu'un |
| En lire un, à condition qu'il soit au format texte | Supprimer un fichier |
| Ajouter un nouveau fichier de son cru | Accéder aux fichiers d'une autre exécution |

Un fichier écrit par l'agent apparaît dans la discussion sous forme de carte avec un bouton **Télécharger**. Comme l'agent ne fait jamais qu'ajouter, un fichier qu'il écrit sous un nom déjà présent dans la session est stocké sous une variante numérotée (`report (2).csv`) au lieu de remplacer l'existant : la carte nomme le fichier tel qu'il a réellement été stocké.

La lecture est limitée au texte. Une feuille de calcul, une image ou une archive est stockée et téléchargée intacte, mais l'agent ne peut pas la lire ; donnez-lui un export texte s'il a besoin de son contenu.

| | |
|---|---|
| **Qui peut joindre** | L'initiateur de l'exécution et ses approbateurs désignés, c'est-à-dire les personnes qui peuvent piloter l'exécution. Un Administrateur qui ne fait qu'observer ne peut pas joindre de fichier |
| **Qui peut télécharger** | Toute personne pouvant lire la discussion, Administrateurs compris |
| **Durée de conservation** | Celle de l'exécution. Supprimer l'exécution supprime ses fichiers |
| **Limites de taille** | Définies pour chaque déploiement : voir [Configuration](../operations/configuration.md#session-files) |

Une fois envoyés, les fichiers ne peuvent pas être retirés un par un : les fichiers d'une session disparaissent avec l'exécution.

## Tâches du workflow {#workflow-tasks}

Les tâches de l'exécution sont ici en lecture seule : les modèles se modifient sur le [workflow](./workflows.md#adjusting-the-task-templates), et ce sont l'agent d'exécution et le circuit d'approbation qui font avancer les états d'une exécution.

Chaque tâche porte un état (`en attente`, `en cours`, `terminé`, `échec` ou `ignoré`) et ses dépendances. Une bascule **Tableau / Graphe** permet de passer de la liste au graphe de dépendances, qui empile les tâches sur une seule colonne verticale dans l'ordre des dépendances, les prérequis au-dessus des tâches qui en dépendent, chacune se ramifiant vers la droite vers les serveurs MCP dont elle lie des outils, puis vers les outils eux-mêmes. Le graphe se déplace, se zoome et s'ajuste à la vue ; il ne permet pas de modifier.

## Appels d'outils {#tool-invocations}

Cette page liste les appels d'outils MCP effectués pendant l'exécution et ce que la [passerelle](../architecture/mcp-gateway-and-proxy.md) a décidé pour chacun : les appels `autorisé`, transmis en amont, et les appels `refusé`, rejetés par une règle, avec l'outil, le serveur, le motif du refus et le [certificat d'outil](./approvals.md#human-approval) présenté. Les arguments n'apparaissent que sous forme d'empreinte ; les valeurs brutes ne sont jamais stockées.

Les appels à un outil [simulé](./tool-mocks.md) en sont absents, quelle qu'en soit l'issue. La passerelle vérifie un appel simulé comme n'importe quel autre, mais un appel auquel une réponse stockée devait de toute façon répondre n'atteint aucun serveur : ni son autorisation ni son refus n'ont donc leur place dans ce registre. C'est dans la transcription de la discussion de l'exécution qu'on examine un appel simulé.

## Supprimer une exécution {#deleting-a-run}

L'action **Supprimer** d'une ligne retire l'exécution après une demande de confirmation : l'enregistrement, ses tâches et sa session du workflow disparaissent avec elle.
