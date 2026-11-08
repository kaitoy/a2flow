---
title: Notifications
sidebar_position: 11
---

# Notifications

Les workflows travaillent en arrière-plan : une exécution de conception se termine alors que vous êtes ailleurs, une approbation attend une personne qui n'a pas ouvert l'application. Les notifications acheminent ces événements jusqu'à la personne concernée.

Une **icône en forme de cloche** se trouve dans la barre d'outils supérieure, à la fois dans l'en-tête de la discussion et dans la barre latérale d'administration, avec un badge indiquant le nombre de notifications non lues.

![Organigramme montrant un événement de workflow acheminé vers l'utilisateur concerné, ou vers chaque membre éligible du groupe d'approbateurs, puis diffusé vers la cloche, la page Notifications et l'e-mail s'il est activé.](./img/notifications-routing.svg#gh-light-mode-only)
![Organigramme montrant un événement de workflow acheminé vers l'utilisateur concerné, ou vers chaque membre éligible du groupe d'approbateurs, puis diffusé vers la cloche, la page Notifications et l'e-mail s'il est activé.](./img/notifications-routing-dark.svg#gh-dark-mode-only)

## Les cinq événements {#the-five-events}

| Type | Déclenché lorsque | Destinataire |
|---|---|---|
| brouillon prêt | L'exécution de conception en arrière-plan de [Générer un workflow](./workflows.md#generating-a-workflow) s'est terminée et les modèles de tâches du brouillon sont prêts à être examinés. | La personne qui a lancé la génération |
| génération échouée | Cette même exécution de conception a échoué. Elle se déroule sans surveillance, sans aucun client connecté : c'est donc ainsi que vous l'apprenez. Le motif figure sur la page de détail du workflow et dans sa discussion de conception. | La personne qui a lancé la génération |
| demande d'approbation | L'agent demande une décision en cours d'exécution et attend. | L'[approbateur désigné](./approvals.md#human-approval) — une notification par membre éligible lorsque la destination est un groupe |
| exécution terminée | Toutes les tâches d'une exécution ont atteint un état final. Déclenché une seule fois par exécution. | La personne qui a lancé l'exécution |
| demande de saisie | Une tâche dont le serveur MCP demandera des [confirmations](./workflow-executions.md#mcp-server-confirmations) est sur le point de démarrer, et l'exécution attend que vous la repreniez depuis la discussion. | La personne qui a lancé l'exécution |

Cliquer sur une notification la marque comme lue et vous amène à ce qu'elle désigne : la discussion de l'exécution pour les événements liés à une exécution, la page de détail du workflow pour ceux liés à un workflow.

## Où apparaissent les notifications {#where-notifications-appear}

| | **La liste déroulante de la cloche** | **La [page Notifications](./notifications.md#notification-history-page)** |
|---|---|---|
| **Affiche** | Les non lues uniquement : ce qui demande encore votre attention | L'historique complet, éléments lus compris |
| **Accès** | La cloche de la barre d'outils | Le bouton de profil de la barre d'outils → **Notifications** |
| **Marquer comme lu** | Par ligne (✓), et **Tout marquer comme lu** dans l'en-tête du panneau tant qu'il reste des éléments non lus | Par ligne (✓) |
| **Supprimer** | Non proposé | Par ligne (✕), après confirmation |

Rien dans la liste déroulante ne supprime une notification ; la marquer comme lue ne fait que l'écarter. La liste s'actualise d'elle-même toutes les trente secondes : une nouvelle notification arrive donc sans recharger la page.

## Page d'historique des notifications {#notification-history-page}

La page Notifications présente toutes les notifications que vous avez reçues sous la forme d'un tableau triable et filtrable indiquant le titre, le type et la date de création. Filtrez la colonne **Lu** sur **Oui** ou **Non** pour n'afficher que les notifications lues ou non lues. C'est le seul endroit où une notification peut être définitivement supprimée.

Les notifications propres à A2Flow s'affichent dans [votre langue](./users-and-groups.md#language), tandis que le titre et la description d'une approbation restent tels que l'agent les a rédigés. Le tri et le filtrage par titre portent sur le texte anglais : hors de l'anglais, la colonne **Titre** ne propose donc ni l'un ni l'autre ; filtrez plutôt par **Type**.

Les notifications sont strictement individuelles : vous ne voyez que les vôtres, et chacune disparaît avec le compte, l'exécution ou le workflow auquel elle appartient.

## Envoi par e-mail {#email-delivery}

Dès qu'un super administrateur a configuré un serveur SMTP dans les [Paramètres système](./system-settings.md), les cinq mêmes événements sont **également envoyés par e-mail** au destinataire : une demande d'approbation n'a donc pas à attendre que quelqu'un ouvre l'application.

Le message reprend le titre de la notification comme objet, son corps comme texte, et comporte un lien vers ce qu'elle concerne : l'exécution ou le workflow. Ce lien est construit à partir de l'**URL de base de l'application** configurée ; si aucune n'est définie, le message est envoyé sans lien.

Les destinataires injoignables sont écartés avant tout contact avec le relais : l'utilisateur système interne, les comptes désactivés ou supprimés, les comptes dont l'adresse n'est pas vérifiée et tout compte sans adresse. Il n'existe pas de désinscription individuelle : l'envoi d'e-mails est activé ou désactivé pour toute la plateforme.

### La file d'envoi {#the-delivery-queue}

Rien n'est envoyé tant qu'une opération de workflow est en cours. La notification et son message entièrement composé sont écrits ensemble : un plantage ne peut donc jamais laisser une notification dont l'e-mail n'aurait pas été mis en file d'attente. Un worker vide ensuite cette file :

- **Cadencé.** Une limite de débit maintient le relais à un nombre fixe de messages par seconde, et tout un lot part sur une même connexion réutilisée.
- **Réessayé.** Un échec transitoire — le relais est hors service ou rejette les identifiants — programme une nouvelle tentative avec un délai croissant : 15 s, 30 s, 1 min, 2 min, puis un doublement jusqu'à une heure. Le budget par défaut permet de tenir pendant environ une heure d'indisponibilité.
- **Abandonné quand il n'y a plus d'espoir.** Un échec que le relais signale comme permanent, un destinataire inconnu par exemple, n'est pas réessayé du tout. Un message qui a épuisé ses tentatives, ou qui a échoué définitivement, reste dans la file à l'état `échec` avec sa dernière erreur : une lettre morte à examiner, et non une perte silencieuse. Les messages remis sont purgés au bout de 30 jours ; les lettres mortes sont conservées.

Un seul processus envoie à la fois, ce qui rend la limite de débit exacte et non approximative. Lancer plusieurs workers apporte une reprise sur panne, pas de débit supplémentaire. Un expéditeur qui s'arrête en plein lot ne consomme pas de tentative : le passage suivant récupère son travail.

Par défaut, le processus d'API fait lui-même office de worker. Sous Docker Compose, un service worker dédié prend le relais, ce qui tient l'envoi des e-mails à l'écart du processus qui traite les requêtes. Tous les réglages sont listés dans la [référence de configuration](../operations/configuration.md#outgoing-email-queue).

Les symptômes d'arriéré et de relais bloqué sont visibles sur le [point de terminaison des métriques](../operations/metrics.md).
