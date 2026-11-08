---
title: Barrière d'approbation
sidebar_position: 5
---

# Barrière d'approbation

Une [approbation](../guides/approvals.md) fait deux choses à la fois. Elle arrête une exécution à une étape jusqu'à ce qu'une personne statue, et elle transforme cette décision en une autorisation signée qui indique exactement ce que les étapes couvertes pourront faire ensuite.

![Diagramme de séquence d'une approbation : l'agent d'exécution demande une approbation, A2Flow notifie l'approbateur tandis que les étapes couvertes restent bloquées, l'approbateur statue, puis A2Flow accorde un certificat à chaque étape couverte à son démarrage et laisse l'exécution se poursuivre.](./img/approvals-sequence.svg#gh-light-mode-only)
![Diagramme de séquence d'une approbation : l'agent d'exécution demande une approbation, A2Flow notifie l'approbateur tandis que les étapes couvertes restent bloquées, l'approbateur statue, puis A2Flow accorde un certificat à chaque étape couverte à son démarrage et laisse l'exécution se poursuivre.](./img/approvals-sequence-dark.svg#gh-dark-mode-only)

## Ce que signifie « bloqué » {#what-blocked-means}

Cette pause n'est pas une attente polie de la part de l'agent.

| Tant qu'une approbation n'est pas décidée | |
|---|---|
| Ce que peuvent appeler les étapes couvertes | Aucun de leurs outils MCP liés : l'appel est refusé avant d'atteindre un serveur |
| Qui l'impose | La [passerelle](./mcp-gateway-and-proxy.md), sous la forme d'une règle qu'elle vérifie, et non d'une phrase dans les instructions de l'agent |
| Ce qui déclenche la barrière | L'*existence* d'une approbation couvrant l'étape. Une approbation en attente et une approbation rejetée bloquent de la même façon : la barrière échoue donc en position fermée |
| Ce qui n'est pas affecté | Les étapes qu'aucune approbation ne couvre : elles continuent de s'exécuter selon la règle ordinaire de liaison des outils |

Une injection de prompt ou un bogue ne peuvent donc pas franchir la barrière par la persuasion, puisqu'il n'y a personne à convaincre. Seule une décision enregistrée sur l'approbation peut l'ouvrir.

## Le certificat {#the-certificate}

Chaque étape couverte par une approbation reçoit à son démarrage un certificat de courte durée, signé par une autorité de certification que le déploiement génère pour lui-même à la première utilisation.

Le certificat n'est pas ce qu'ajoute une approbation : **toute** étape qui appelle un outil en possède un. Ce que change une approbation, c'est sa provenance : une étape pour laquelle personne n'a été sollicité en reçoit un au titre de l'autorité de la personne qui a lancé l'exécution, et une approbation remplace cette autorité par celle de l'approbateur. La question à laquelle répond l'enregistrement n'est donc jamais « cet appel était-il autorisé ? », mais « par qui ? ».

| Le certificat contient | Pourquoi c'est important |
|---|---|
| Le tenant, l'exécution et l'étape qu'il représente, et l'autorité qu'il porte, celle d'un approbateur ou celle de l'initiateur de l'exécution | Un certificat émis pour une exécution est inutilisable dans une autre, et un type d'autorité ne peut pas se substituer à l'autre |
| **Les outils liés à l'étape au moment de son démarrage** | Les étapes d'une exécution et leurs outils sont fixés au lancement d'après la conception publiée du workflow, le certificat les fige de nouveau à son émission, et les outils d'une étape couverte ne peuvent plus du tout être modifiés : ni l'agent ni un changement ultérieur ne peuvent donc élargir une autorisation. Approuver une étape pour lire un fichier ne devient jamais l'autorisation d'en supprimer un |

### Les appels que couvre une décision {#the-calls-a-decision-covers}

Le certificat répond à la question *quel outil*, jamais à la question *appelé avec quoi*, or c'est généralement dans les entrées que résident les conséquences. La demande contient donc un second élément, absent du certificat : les appels qu'elle autorise, chacun nommant un outil et encadrant les valeurs que peuvent prendre ses entrées. Cet élément est enregistré au moment de la demande, présenté à l'approbateur avant sa décision, et personne ne peut plus le modifier ensuite, pas même l'agent.

Chaque appel transmis au proxy y est ensuite confronté, en plus du certificat :

| Élément vérifié | Refusé lorsque |
|---|---|
| L'outil | La décision ne le liste pas, même si le certificat l'accorde |
| Chaque entrée fournie | La décision ne la nomme pas : c'est une entrée que l'approbateur n'a jamais vue |
| Chaque entrée nommée par la décision | Elle est absente, sauf si la décision l'a marquée comme facultative |
| Chaque valeur | Elle sort des limites acceptées par l'approbateur |

Une étape où se rejoignent deux branches approuvées doit respecter **les deux** décisions, pour la raison même qui l'oblige à les obtenir toutes les deux : l'approbateur le plus permissif ne parle pas au nom de l'autre. Lorsque les deux divergent sur la nécessité de faire approuver les entrées d'un outil, c'est la décision la plus stricte qui l'emporte.

Un outil que la conception du workflow a marqué comme étant en lecture seule figure lui aussi dans la liste, avec la mention **Toute entrée**, au lieu d'en être absent. La décision reste ainsi le compte rendu complet de ce qu'elle autorise : l'approbateur voit quels outils n'ont pas de limites, et la barrière n'a qu'une seule liste à consulter, sans seconde règle qui relirait les outils de l'étape. Seul le circuit de demande peut écrire une telle entrée ; un agent qui tente d'en déclarer une lui-même est refusé.

Une étape qui s'exécute sous l'autorité de l'initiateur de l'exécution n'est pas vérifiée de cette façon : il n'y a pas eu d'approbateur, donc rien dont elle aurait pu s'écarter. Ce qui la limite reste inchangé : ses propres outils et l'autorisation signée du certificat.

### Les étapes que couvre une approbation {#the-steps-an-approval-covers}

Une approbation couvre **l'étape qu'elle nomme et toutes les étapes suivantes, jusqu'à la prochaine approbation**. Un workflow peut donc placer la demande dans une étape dédiée et laisser la décision s'appliquer au travail qui suit :

![Organigramme d'une chaîne de cinq étapes où l'approbation A couvre les trois premières étapes et l'approbation B prend le relais à partir de la quatrième, montrant qu'une approbation couvre l'étape qu'elle nomme et tout ce qui suit jusqu'à la prochaine approbation.](./img/approvals-step-coverage.svg#gh-light-mode-only)
![Organigramme d'une chaîne de cinq étapes où l'approbation A couvre les trois premières étapes et l'approbation B prend le relais à partir de la quatrième, montrant qu'une approbation couvre l'étape qu'elle nomme et tout ce qui suit jusqu'à la prochaine approbation.](./img/approvals-step-coverage-dark.svg#gh-dark-mode-only)

L'approbation A couvre *Demander le feu vert*, *Lancer l'instance* et *Étiqueter l'instance*. L'approbation B prend le relais à partir de *Redemander*. Rien de ce qui précède une demande n'est jamais couvert par elle : une approbation ne porte que vers l'avant.

| Situation | Ce qui se passe |
|---|---|
| L'étape nommée n'utilise elle-même aucun outil | C'est permis, et courant. La décision est portée par les étapes suivantes |
| Une étape se trouve après deux approbations sur des branches différentes | **Les deux** doivent être accordées avant qu'elle puisse agir. Un approbateur qui valide sa propre branche ne parle pas au nom de l'autre |
| Une seconde approbation est demandée sur une étape déjà couverte par une approbation antérieure | La demande la plus proche prend aussitôt le relais, et la décision antérieure cesse d'autoriser cette étape |
| Une étape est renvoyée pour reprise puis soumise de nouveau | La nouvelle demande remplace l'ancienne décision comme barrière de cette étape : un rejet ne peut donc pas laisser l'étape bloquée définitivement |

Chaque appel d'outil ultérieur d'une étape couverte doit présenter son certificat, et la passerelle vérifie tous les points suivants avant de laisser l'appel aller où que ce soit :

- le certificat représente bien cette exécution et cette étape ;
- il a été émis par ce déploiement et n'a pas été révoqué ;
- l'approbation qui le fonde couvre toujours l'étape, et toutes les approbations qui la couvrent restent accordées ;
- l'appelant peut prouver que le certificat lui appartient et qu'il ne l'a pas copié ;
- l'outil appelé fait partie de l'ensemble signé.

Un certificat est révoqué lorsque son étape atteint un état final. La sécurité n'en dépend pas, puisqu'une étape terminée ne s'exécute plus et que ses appels sont déjà refusés, mais cela permet à l'enregistrement d'indiquer *pourquoi* l'autorisation a cessé de valoir, et aligne la durée de vie d'un certificat sur le travail qu'il a autorisé. Comme chaque étape couverte reçoit son propre certificat à son démarrage, une longue chaîne d'étapes n'a pas à se terminer pendant la durée de vie d'un seul certificat ; cette durée de vie maximale se règle dans la [référence de configuration](../operations/configuration.md#mcp-tools-and-approvals).

## Ce à quoi répond l'enregistrement {#what-the-record-answers}

Chaque appel tranché, autorisé ou refusé, est enregistré avec le certificat qu'il a présenté : on peut ainsi répondre à la question « qui a autorisé cela, et sur quelle base ? » longtemps après la fin de l'exécution. Les arguments ne sont conservés que sous forme d'empreinte ; les valeurs brutes ne sont jamais stockées. Cet enregistrement se consulte sur la page Appels d'outils de l'exécution.

Un appel refusé parce qu'il s'écarte de la décision enregistre la raison du refus, en nommant l'entrée en cause et la limite acceptée par l'approbateur, mais jamais la valeur réellement transmise. Cette raison est stockée telle quelle, dans le même enregistrement qui ne conserve les arguments que sous forme d'empreinte : y citer la valeur refusée réintroduirait exactement ce que l'empreinte vise à exclure.

**Portée de la garantie.** La passerelle s'exécute dans le processus du backend : un certificat prouve donc la possession auprès d'un vérificateur partageant ce processus, et ne constitue pas une défense contre un attaquant qui contrôle déjà le backend. Il apporte en revanche un point d'application unique qui échoue en position fermée, une autorisation qu'on ne peut pas élargir après coup et un enregistrement vérifiable ensuite.
