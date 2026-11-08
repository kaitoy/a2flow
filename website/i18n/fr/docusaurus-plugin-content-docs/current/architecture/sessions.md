---
title: Sessions
sidebar_position: 4
---

# Sessions

Une session est une discussion que partagent plusieurs parties : l'agent, la personne qui l'a ouverte et toute autre personne que le travail y amène. C'est aussi là que l'agent dessine des surfaces interactives : un échange peut donc prendre la forme d'un formulaire à remplir plutôt que d'un paragraphe auquel répondre en toutes lettres.

## Qui la partage {#who-shares-one}

| Session | Partagée par | Toute autre personne |
|---|---|---|
| **Session du workflow** | L'initiateur de l'exécution et l'approbateur désigné de l'une de ses [approbations](./approvals.md) | Un Administrateur du tenant la voit en lecture seule ; personne d'autre n'y a accès |
| **Session de conception** | Tous les Développeurs du tenant, ainsi que les Super administrateurs et le créateur du workflow | Aucun accès |

Une approbation adressée à un groupe fait entrer tous les membres qui possèdent le rôle Approbateur : la discussion suit ainsi la composition du groupe, cet accès ayant pour seul but de permettre la décision. Comme plusieurs personnes écrivent dans la même conversation, chaque message porte un **avatar d'expéditeur**, et chaque participant voit chaque réponse au fur et à mesure de sa rédaction, sans recharger la page.

## Déroulement d'un tour {#how-a-turn-runs}

![Diagramme de séquence d'un tour de discussion : le message de l'utilisateur va de l'interface au backend puis au modèle, la réponse diffusée du modèle et toute surface render_a2ui reviennent, et la surface remplie par l'utilisateur refait le même aller-retour.](./img/sessions-turn-flow.svg#gh-light-mode-only)
![Diagramme de séquence d'un tour de discussion : le message de l'utilisateur va de l'interface au backend puis au modèle, la réponse diffusée du modèle et toute surface render_a2ui reviennent, et la surface remplie par l'utilisateur refait le même aller-retour.](./img/sessions-turn-flow-dark.svg#gh-dark-mode-only)

Le backend relie le protocole AG-UI à l'agent : il traduit les événements dans les deux sens, maintient la conversation synchronisée et renvoie les événements au navigateur à mesure qu'ils arrivent, de sorte que le texte s'affiche progressivement et non d'un seul bloc à la fin. L'état de la conversation est conservé sous l'identifiant de la discussion : la rouvrir reprend donc là où elle s'était arrêtée.

Une session du workflow n'a besoin d'aucune discussion ouverte : chacun de ses tours est exécuté par A2Flow lui-même. Il s'agit du **lancement** de l'exécution, dès sa création ; du tour qui la **reprend** une fois une [approbation](../guides/approvals.md) décidée ; du tour qui la reprend lorsqu'est arrivé le moment qu'une tâche [devait attendre](../guides/workflows.md#how-the-agent-works-through-the-tasks) ; et du tour qui répond à ce qu'envoie un participant. La discussion ne fait que transmettre le message à A2Flow et afficher le tour en cours à tous ceux qui regardent, quel que soit le serveur sur lequel il s'exécute. (La session de conception fait exception : ses tours sont toujours exécutés depuis la discussion du Développeur qui a envoyé le message.)

## Surfaces interactives {#interactive-surfaces}

L'outil `render_a2ui` est attaché par l'interface ou, lors d'un tour exécuté par A2Flow lui-même, par le backend avec exactement la même définition ; il contient le schéma du catalogue de composants [A2UI](https://a2ui.org) que l'agent peut utiliser pour dessiner. Lorsque le modèle l'appelle, le backend n'exécute rien : il transmet l'appel, et c'est le navigateur qui dessine le résultat.

| Composant | Utilisation |
|---|---|
| `Text`, `Card`, `Row`, `Column` | Structure et texte |
| `TextField` | Saisie libre |
| Un sélecteur de choix | Sélection parmi des valeurs autorisées. Un sélecteur à choix unique comptant cinq options ou plus se replie en liste déroulante : l'agent peut ainsi lister tous les types d'instance EC2 ou toutes les régions sans noyer la conversation |
| `Button` | Envoi de la surface |

Un clic sur un bouton renvoie **tout le modèle de données** de la surface, c'est-à-dire toutes les valeurs saisies ou sélectionnées, et pas seulement le bouton actionné. C'est ce qui permet à l'agent de réagir à ce que l'utilisateur a réellement saisi, et à une discussion rechargée de réafficher une surface déjà traitée, remplie avec les valeurs de l'utilisateur et non avec celles proposées par défaut par l'agent.

### La question d'un serveur en cours d'appel {#a-servers-question-mid-call}

L'une des surfaces n'est pas du tout dessinée par l'agent. Un serveur MCP peut s'arrêter au milieu d'un appel d'outil pour poser une question à une personne (une *élicitation*), et l'appel reste ouvert pendant cette attente. Seul un outil que la conception du workflow marque comme posant des questions peut le faire, et une tâche qui en utilise un ne démarre pas tant que l'initiateur de l'exécution n'est pas dans la discussion : la session se met en pause à l'état **En attente de l'initiateur**, l'initiateur est notifié, et la tâche démarre au tour que lance son action **Reprendre**. A2Flow enregistre ensuite la question et l'ajoute au flux du tour en cours en tant qu'activité à part entière, si bien que tous les spectateurs la voient aussitôt. La réponse passe par une voie dédiée et non par la zone de saisie de la discussion, car la session est encore au milieu d'un tour : c'est l'appel d'outil en attente, et non un nouveau tour, qui la récupère. Voir [Confirmations d'un serveur MCP](../guides/workflow-executions.md#mcp-server-confirmations) pour ce que voit la personne.

## L'activité de l'agent dans la discussion {#agent-activity-in-the-chat}

Pour que vous puissiez voir ce que fait l'agent entre deux réponses, son travail intermédiaire s'affiche directement dans le flux de la discussion :

- **Indicateur d'activité** : lorsqu'une exécution est en cours mais que rien n'est encore affiché, une discrète pulsation apparaît en bas de la liste des messages.
- **Lignes d'appel d'outil** : chaque appel d'outil du backend (par exemple `list_workflow_tasks`, `update_workflow_task`) devient une ligne d'état compacte qui passe d'une icône de chargement (`en cours…`) à une coche (`terminé`). Les appels acheminés par la [passerelle MCP](./mcp-gateway-and-proxy.md) s'affichent sous le **vrai nom de l'outil MCP**, avec une étiquette `MCP`. Les outils clients `render_a2ui` et `render_approval`, l'outil qui écrit un fichier de session et celui qui propose des [réponses suggérées](../guides/workflow-executions.md#suggested-replies) conservent leur interface dédiée et n'apparaissent pas sous forme de lignes d'outil.
- **Détails de l'appel** : une ligne d'outil comportant des arguments ou un résultat **se déplie au clic** pour les afficher tous deux en JSON mis en forme, ce qui permet d'examiner ce que l'agent a réellement envoyé et reçu sans quitter la discussion. Une ligne à laquelle a répondu un [simulacre d'outil](./mcp-gateway-and-proxy.md#tool-mocks-and-dry-runs) porte un badge `Simulé`, et la discussion est le *seul* endroit où l'on peut l'examiner, puisqu'un appel simulé n'atteint jamais le proxy et ne laisse donc aucune trace d'audit.
- **Raisonnement** : lorsqu'un modèle capable de raisonner diffuse son raisonnement, celui-ci s'affiche dans un panneau discret « Réflexion ». Un modèle qui raisonne en interne sans émettre de résumés de ses réflexions ne produit aucun panneau.

À la reprise d'une session, les **appels d'outils MCP**, les **cartes de fichiers** et les **réponses suggérées** du dernier tour sont reconstitués à partir de l'historique ; les autres appels d'outils internes d'A2Flow et le raisonnement ne sont visibles qu'en direct. Une carte de fichier est reconstituée parce que le fichier survit à l'exécution qui l'a produit et que la discussion est le seul endroit où apparaît son lien de téléchargement ; les suggestions le sont parce que la question à laquelle elles répondent reste ouverte.

## Les fichiers d'une session {#files-in-a-session}

Une session du workflow contient des fichiers en plus des messages : ceux qu'un participant a joints depuis la zone de saisie de la discussion, et ceux que l'agent a écrits au cours de son travail. Une session de conception n'en a aucun.

Trois règles les définissent :

- **Portée.** Un fichier appartient à exactement une exécution. Rien ne peut désigner un fichier sans nommer l'exécution à laquelle il appartient : les fichiers d'une session sont donc inaccessibles depuis une autre.
- **Durée de vie.** Les fichiers vivent aussi longtemps que leur exécution et sont supprimés avec elle. Il n'y a ni nettoyage séparé, ni expiration.
- **Accès.** Les fichiers n'ont pas d'autorisation propre : pour en joindre, il faut pouvoir piloter l'exécution ; pour en télécharger, il faut pouvoir lire sa discussion. Ce sont les deux mêmes règles que celles de la discussion elle-même.

L'agent peut lire et ajouter des fichiers, mais jamais les remplacer ni les supprimer : une écriture sous un nom déjà pris est stockée sous une variante numérotée. Un fichier joint par un participant reste donc exactement tel qu'il l'a joint, quoi que fasse ensuite l'exécution.

Ce que l'agent sait des fichiers ne vient pas du navigateur. Le serveur lit la liste des fichiers de la session et l'injecte dans le contexte de l'exécution, à côté du prompt du workflow, de la même façon et pour la même raison : une liste fournie par le client serait une instruction fournie par le client.

Les fichiers sont stockés dans la base de données : ils héritent donc de sa durabilité et de sa sauvegarde, et ne nécessitent aucun volume partagé entre les réplicas. Les téléchargements sont toujours servis en pièce jointe avec un type de contenu générique : rien de ce qu'un participant ou l'agent a stocké ne peut donc être rendu par un navigateur.
