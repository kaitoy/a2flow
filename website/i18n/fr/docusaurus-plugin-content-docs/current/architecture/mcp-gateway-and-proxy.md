---
title: Passerelle et proxy MCP
sidebar_position: 6
---

# Passerelle et proxy MCP

L'agent ne communique jamais directement avec un [serveur MCP](../guides/mcp-servers.md) enregistré. Chaque appel passe par deux composants propres à A2Flow, qui répondent à deux questions différentes :

| | Passerelle MCP | Proxy MCP |
|---|---|---|
| **Où il s'exécute** | Dans le processus de l'agent, à côté de la base de données | Dans un conteneur distinct, qui ne détient aucun des secrets de l'agent |
| **Ce qu'il tranche** | *Si* un appel peut avoir lieu | *Où* il a lieu : il démarre le serveur ou s'y connecte |
| **Ce qu'il détient** | L'identité, la chaîne de stratégies, les simulacres d'outils, le développement des secrets, l'enregistrement d'audit | Un appel à la fois : l'adresse ou la commande du serveur, les valeurs développées, l'outil et ses arguments |

C'est la passerelle qui décide, et le reste de cette page porte surtout sur elle. Le proxy est le bac à sable auquel ces décisions sont confiées ; il a sa propre section [plus bas](#the-sandbox).

## Ce que décide la passerelle {#what-the-gateway-decides}

![Organigramme de la chaîne de stratégies qui tranche un appel d'outil : les appels refusés sont rejetés avec l'indication de ce qui est autorisé, les appels autorisés reçoivent la réponse d'un simulacre ou passent par l'injection des identifiants et le proxy MCP pour atteindre le serveur MCP, et un refus comme un appel réel produisent un enregistrement d'audit.](./img/mcp-gateway-and-proxy-policy-chain.svg#gh-light-mode-only)
![Organigramme de la chaîne de stratégies qui tranche un appel d'outil : les appels refusés sont rejetés avec l'indication de ce qui est autorisé, les appels autorisés reçoivent la réponse d'un simulacre ou passent par l'injection des identifiants et le proxy MCP pour atteindre le serveur MCP, et un refus comme un appel réel produisent un enregistrement d'audit.](./img/mcp-gateway-and-proxy-policy-chain-dark.svg#gh-dark-mode-only)

| La passerelle gère | Ce qu'elle fait |
|---|---|
| **L'identité** | Établit à quel tenant et à quelle exécution appartient un appel, d'après la conversation par laquelle il est arrivé |
| **L'autorisation** | Consulte une chaîne ordonnée de stratégies, dont chacune peut opposer un veto |
| **La simulation** | Répond à partir d'un [simulacre d'outil](#tool-mocks-and-dry-runs) lorsque l'exécution en possède un pour cet outil |
| **Les identifiants** | Développe les références de [secrets](./secrets.md) du serveur enregistré pour établir une connexion, uniquement au moment de la connexion |
| **L'isolation** | Confie l'appel autorisé au [proxy MCP](#the-sandbox), qui exécute réellement le serveur |

## Le proxy MCP : là où s'exécute un serveur enregistré {#the-sandbox}

Un serveur MCP que vous enregistrez n'est pas du code d'A2Flow. Un serveur local est un programme qu'A2Flow démarre pour vous ; un serveur distant est un service auquel A2Flow se connecte. Dans les deux cas, ce qu'il fait une fois lancé échappe au contrôle d'A2Flow.

Il ne s'exécute donc pas là où se trouvent les secrets d'A2Flow. Le proxy est un bac à sable : dans un déploiement Docker Compose, il s'agit du **conteneur distinct `mcp-proxy`**, qui ne détient aucun des éléments suivants :

| Absent du proxy | Où il reste |
|---|---|
| La base de données et tout ce qui y est enregistré | Avec l'agent |
| La clé qui chiffre les [secrets](./secrets.md) | Avec l'agent |
| Les identifiants d'un stockage de secrets externe | Avec l'agent |
| La clé d'API du fournisseur de LLM | Avec l'agent |
| Les dépôts des [compétences d'agent](../guides/agent-skills.md) | Avec l'agent |

Le proxy reçoit un appel à la fois : l'adresse ou la commande du seul serveur à joindre, les valeurs dont ce serveur a besoin, déjà développées à partir de vos références de secrets, ainsi que l'outil et ses arguments. Il n'y a rien d'autre à y trouver.

![Schéma d'architecture montrant la passerelle MCP, qui décide si un appel est autorisé, simulé et de quels identifiants il a besoin, et qui remet exactement un appel autorisé à travers une frontière de confiance au proxy MCP, lequel démarre le vrai serveur MCP ou s'y connecte.](./img/mcp-gateway-and-proxy-trust-boundary.svg#gh-light-mode-only)
![Schéma d'architecture montrant la passerelle MCP, qui décide si un appel est autorisé, simulé et de quels identifiants il a besoin, et qui remet exactement un appel autorisé à travers une frontière de confiance au proxy MCP, lequel démarre le vrai serveur MCP ou s'y connecte.](./img/mcp-gateway-and-proxy-trust-boundary-dark.svg#gh-dark-mode-only)

**Les deux extrémités prouvent mutuellement leur identité.** Le canal qui les relie est chiffré, et aucune n'accepte un interlocuteur non identifié : le proxy refuse toute connexion provenant d'un élément qui ne détient pas de certificat émis par ce déploiement. Chaque appel porte en outre le [certificat](#who-authorized-a-call) de la tâche qui l'émet, et le proxy vérifie de nouveau ce certificat avant de contacter quoi que ce soit : il doit avoir été émis ici, ne pas avoir expiré, appartenir à l'appelant et couvrir précisément cet outil.

**Un appel peut poser une question en chemin.** Un serveur MCP peut s'arrêter au milieu d'un appel pour demander une [confirmation](../guides/workflow-executions.md#mcp-server-confirmations) à la personne à l'origine de l'exécution. C'est la passerelle qui sait de qui il s'agit : le proxy renvoie donc la question par la connexion même de l'appel, et la réponse remonte par cette même connexion jusqu'au serveur en attente. Rien de ce qui concerne un appel ne survit à sa connexion : le proxy peut donc tourner dans autant de conteneurs que nécessaire.

Cette seconde vérification ne répond pas à la même question que la première. Être A2Flow ne signifie pas être autorisé à appeler un outil donné, et détenir le certificat d'une tâche ne signifie pas que la requête est bien celle qu'A2Flow a envoyée. Les deux conditions doivent être réunies : une requête ne peut donc pas conserver une autorisation valide tout en dirigeant discrètement le proxy vers un autre programme.

Un seul appel ne porte aucun certificat de tâche : une [exécution de test](../guides/mcp-servers.md#testing-a-script) d'un script depuis le formulaire de serveur MCP, qui n'est rattachée à aucune tâche. Le proxy ne l'accepte que pour un script, jamais pour une commande arbitraire ou un serveur distant, et le chargement de la liste d'outils d'un script exécute déjà l'intégralité du script sous le même contrôle réservé à A2Flow : cela ne laisse donc rien passer de nouveau.

Le proxy est une seconde ligne de défense, et non le décideur. La tâche est-elle toujours en cours, l'approbation tient-elle encore, le certificat a-t-il été retiré ? Il ne peut répondre à aucune de ces questions, qui restent toutes du ressort de la passerelle.

## Chaque lancement dans son propre bac à sable {#per-launch-sandbox}

Le proxy tient les serveurs enregistrés à l'écart d'A2Flow. Il les tient aussi à l'écart **les uns des autres**. Les serveurs de tous les tenants démarrent dans le même proxy, et certains sont des scripts écrits par un tenant : chaque serveur que le proxy démarre est donc enfermé dans son propre bac à sable, créé pour cet appel et détruit à sa fin.

| Dans le bac à sable | Ce que cela exclut |
|---|---|
| Le serveur ne voit que ses propres processus | La lecture des valeurs secrètes transmises à tout autre serveur en cours d'exécution au même moment |
| Le système et les programmes d'A2Flow sont en lecture seule | La modification de ce qu'un serveur ultérieur, par exemple celui d'un autre tenant, exécutera à son prochain démarrage |
| Son répertoire personnel, où sont conservés les paquets téléchargés, appartient à son seul tenant | La récupération par un serveur d'un paquet déposé par un autre tenant |
| Tout ce qui s'y trouve prend fin avec l'appel | La persistance d'un processus après l'appel pour observer les appels suivants |
| Les identifiants du proxy n'y sont pas du tout | L'usurpation de l'identité du proxy auprès de qui que ce soit |

Un serveur distant, auquel le proxy se contente de se connecter, n'exécute rien dans le proxy et n'a donc pas besoin de bac à sable.

L'isolation repose sur [bubblewrap](https://github.com/containers/bubblewrap), l'outil de bac à sable Linux sur lequel s'appuie Flatpak. Le proxy vérifie au démarrage qu'il peut créer un bac à sable et refuse de démarrer dans le cas contraire : il ne se rabat jamais sur l'exécution d'un serveur hors bac à sable. Voir [Déploiement](../operations/deployment.md#process-layout) pour ce que cela exige de l'hôte.

## La chaîne de stratégies {#the-policy-chain}

| Ordre | Stratégie | Ce qu'elle exige |
|---|---|---|
| 1 | **Liaison d'outil en cours** | La paire `(serveur, outil)` doit être liée à une tâche à l'état `en cours` attribuée à la session appelante ; une tâche traitée par une autre session de l'exécution ne compte pas. Lister ce que propose un serveur n'est pas un appel, et cette règle ne s'y applique donc pas : l'agent de conception liste pour décider quoi lier, dans la limite des serveurs que le concepteur peut voir selon les [étiquettes de contrôle d'accès](../guides/tags.md), tandis que la liste établie par une exécution n'est pas restreinte par les étiquettes |
| 2 | **Certificat d'outil** | L'appel doit présenter le certificat de la tâche (voir [Qui a autorisé un appel](#who-authorized-a-call)), et l'autorisation signée de ce certificat doit couvrir l'outil. Il n'y a aucune exemption : une tâche qu'aucune approbation ne couvre présente l'autorisation détenue par l'initiateur de son exécution |
| 3 | **Appel approuvé** | Lorsque c'est la décision d'un approbateur qui autorise la tâche, l'appel doit correspondre aux appels listés par cette décision ; voir [Les appels que couvre une décision](./approvals.md#the-calls-a-decision-covers). Un outil que la décision a listé comme acceptant toute entrée passe cette règle quel que soit son contenu, ayant déjà été arrêté par la règle 2 jusqu'à l'octroi de la décision. Une tâche qui s'exécute avec l'autorisation de son initiateur n'a pas de telle liste et n'est pas vérifiée ici |

La chaîne s'arrête au premier veto et va de la vérification la moins coûteuse à la plus coûteuse : un appel qui échoue déjà à la règle de liaison ne paie jamais une vérification de signature. La dernière règle vient en dernier pour une seconde raison : elle seule a besoin de savoir *quelle* tâche appelle, et c'est la règle précédente qui l'établit. Cela évite aussi qu'un appelant dépourvu de toute autorité apprenne ce qu'un approbateur a accepté. Ajouter une règle consiste à ajouter une stratégie à la chaîne et non à modifier la passerelle, ce qui permet de lire « ce qui peut s'exécuter » comme une seule liste ordonnée.

Les refus sont rédigés pour l'appelant et non pour un journal : un appel refusé revient avec le nom des outils qui *sont* autorisés, afin que le modèle puisse se corriger au lieu de deviner.

## Qui a autorisé un appel {#who-authorized-a-call}

Chaque appel d'outil d'une exécution porte un **certificat** qui nomme la personne dont il engage l'autorité. Une tâche en reçoit un lorsqu'elle passe à l'état **en cours** ; l'autorité qu'il porte dépend de l'existence d'une [approbation](./approvals.md) qui la couvre.

| La tâche | Reçoit son certificat | Sous quelle autorité |
|---|---|---|
| Est couverte par une approbation, la sienne ou une approbation demandée sur une tâche qu'elle suit | À son démarrage, et seulement une fois cette approbation accordée | L'approbateur qui l'a accordée |
| N'est couverte par aucune | Lorsqu'elle passe à l'état **en cours** | La personne qui a lancé l'exécution |

La seconde ligne correspond au cas ordinaire : personne n'a été sollicité pour évaluer la tâche, c'est donc la personne qui a lancé le workflow qui autorise les outils qu'elle lie, et la piste d'audit le consigne explicitement au lieu de laisser l'appel sans attribution.

Il en découle trois règles, toutes visibles par quiconque exploite un workflow :

- **Les outils sont fixés au démarrage de la tâche.** Un certificat couvre exactement les outils liés à la tâche à ce moment-là. Un workflow qui ne lie un outil à une tâche qu'après son démarrage voit cet outil refusé ; l'agent de conception a pour consigne de lier d'abord, mais une tâche modifiée à la main peut encore comporter cette erreur. Les outils d'une tâche couverte par une approbation ne peuvent pas du tout être modifiés.
- **Demander une approbation referme la porte.** Si une approbation est demandée pour une tâche déjà en cours sous l'autorité de quelqu'un, cette autorité s'efface immédiatement ; la tâche attend la décision comme n'importe quelle autre.
- **Chaque tâche couverte reçoit son propre certificat.** Une approbation couvrant une chaîne de tâches ne les soumet pas toutes à la même échéance : chacune reçoit le sien à son démarrage.

## Ce qui est enregistré {#what-is-recorded}

| Enregistré pour chaque appel tranché | Délibérément non enregistré |
|---|---|
| L'outil, le serveur, et si l'appel a été autorisé ou refusé | Les arguments eux-mêmes : seule une empreinte en est conservée |
| Le motif du refus, le cas échéant ; pour un appel sortant de ce qui a été approuvé, l'entrée en cause et la limite acceptée par l'approbateur | La valeur réelle de l'entrée refusée |
| Le certificat présenté, et donc la personne qui a autorisé l'appel | |

Cet enregistrement correspond à la page Appels d'outils de l'exécution, et c'est lui qui permet de répondre après coup à la question « qui a autorisé cet appel ? ». Les certificats eux-mêmes sont listés sous **Journaux d'audit → Certificats**, à raison d'une ligne par autorisation.

## Simulacres d'outils et exécutions à blanc {#tool-mocks-and-dry-runs}

Un [simulacre d'outil](../guides/tool-mocks.md) permet de tester de bout en bout un workflow à l'état **brouillon** sans les effets de bord de ses outils. Ce qui compte ici, c'est l'*endroit* où se place la simulation.

![Organigramme montrant qu'un simulacre d'outil n'est consulté qu'après la même chaîne de stratégies qu'un appel en production : un appel refusé est rejeté exactement comme en production, et un appel autorisé reçoit la réponse suivante d'un simulacre ou celle du vrai serveur MCP.](./img/mcp-gateway-and-proxy-tool-mocks.svg#gh-light-mode-only)
![Organigramme montrant qu'un simulacre d'outil n'est consulté qu'après la même chaîne de stratégies qu'un appel en production : un appel refusé est rejeté exactement comme en production, et un appel autorisé reçoit la réponse suivante d'un simulacre ou celle du vrai serveur MCP.](./img/mcp-gateway-and-proxy-tool-mocks-dark.svg#gh-dark-mode-only)

Le simulacre est consulté **après** la chaîne de stratégies, jamais avant. Une exécution à blanc répète donc la même autorisation qu'une exécution réelle : l'outil doit toujours être lié à une tâche en cours, et l'appel doit toujours présenter le certificat de cette tâche. La seule chose que saute un simulacre est ce qui produit un effet hors d'A2Flow : le proxy n'est jamais contacté.

Deux conséquences méritent d'être connues :

- **Les réponses suivent le nombre d'appels.** La première réponse sert au premier appel de l'exécution à cet outil, la deuxième au deuxième, et la dernière se répète une fois la liste épuisée. Le compteur appartient à l'exécution : il survit donc aux nombreuses requêtes, et aux éventuels réplicas, qu'implique une même exécution d'agent.
- **Un appel simulé ne laisse aucune trace d'audit.** Cet enregistrement concerne les appels qui ont atteint un vrai serveur ou qui ont été arrêtés en chemin ; une ligne pour un appel qui devait de toute façon recevoir sa réponse d'un instantané induirait en erreur dans un sens comme dans l'autre. C'est dans la transcription de la discussion qu'on examine un appel simulé, signalé par le badge `Simulé`.
