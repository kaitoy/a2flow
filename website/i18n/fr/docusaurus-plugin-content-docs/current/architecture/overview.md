---
title: Fonctionnement
sidebar_position: 1
---

# Fonctionnement

A2Flow transforme une [compétence d'agent](../guides/agent-skills.md) en un workflow dont les étapes sont arrêtées avant toute exécution, puis exécute ce workflow dans une discussion que partagent l'agent et les personnes concernées. Chaque étape transmet à la suivante une copie figée de ce qui précède : une exécution reste ainsi fidèle à ce qui a été publié, même lorsque la conception évolue par la suite.

![Organigramme montrant une compétence d'agent dont est généré un workflow, lancé sous forme d'exécution dans une session du workflow, dont les tâches demandent une approbation humaine ou appellent un outil MCP via la passerelle MCP pour atteindre un serveur MCP.](./img/overview-lifecycle.svg#gh-light-mode-only)
![Organigramme montrant une compétence d'agent dont est généré un workflow, lancé sous forme d'exécution dans une session du workflow, dont les tâches demandent une approbation humaine ou appellent un outil MCP via la passerelle MCP pour atteindre un serveur MCP.](./img/overview-lifecycle-dark.svg#gh-dark-mode-only)

| Étape | Ce qui se passe | Pour en savoir plus |
|---|---|---|
| **Concevoir** | Une compétence devient un workflow : une exécution de conception par l'IA décompose la demande en étapes et lie les outils nécessaires à chacune. | [Concevoir un workflow](./workflow-design.md) |
| **Exécuter** | L'exécution d'un workflow copie la conception publiée dans une nouvelle exécution et ouvre sa discussion. | [Exécuter un workflow](./workflow-execution.md) |
| **Échanger** | L'agent et plusieurs personnes partagent cette discussion, et l'agent peut y dessiner des surfaces interactives au lieu de se contenter d'écrire du texte. | [Sessions](./sessions.md) |
| **Approuver** | Une tâche qui nécessite une décision humaine ne peut pas agir tant que quelqu'un n'a pas statué, et cette décision est signée dans un certificat. Toutes les autres tâches en portent un aussi, au titre de l'autorité de la personne qui a lancé l'exécution. | [Barrière d'approbation](./approvals.md) |
| **Agir** | Chaque appel d'outil est tranché par une chaîne de stratégies avant de quitter A2Flow, puis consigné une fois la décision prise. | [Passerelle et proxy MCP](./mcp-gateway-and-proxy.md) |

Derrière tout cela se trouvent deux espaces de stockage : la [base de données](./database.md), où résident tous les enregistrements, et le [stockage des secrets](./secrets.md), d'où sont résolus les identifiants.

## Les deux discussions {#the-two-chats}

A2Flow propose exactement deux types de discussion. Ils reposent sur le même mécanisme, appliqué à des agents différents, et ce qui les distingue est ce que chaque agent a le droit de faire.

| Discussion | Pilotée par | Ce qu'elle peut faire |
|---|---|---|
| **Session de conception** | L'agent de conception, qui suit la compétence | Écrit et réorganise les modèles de tâches du workflow. N'exécute rien. |
| **Session du workflow** | L'agent d'exécution, qui suit la révision de la compétence à laquelle l'exécution est rattachée | Traite les tâches de l'exécution, demande des approbations et appelle des outils MCP. |

Aucune de ces discussions n'est un enregistrement à part entière. Une session de conception est identifiée par son workflow et une session du workflow par son exécution ; la conversation sous-jacente est créée à la première utilisation et conservée sous cet identifiant. Rouvrir l'une ou l'autre reprend donc là où elle s'était arrêtée.
