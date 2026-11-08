---
title: Terminologie
sidebar_position: 1
---

# Terminologie

Voici les concepts qui portent l'essentiel du domaine ; mieux vaut ne pas les confondre :

| Terme | Ce que c'est |
|---|---|
| **[Workflow](../guides/workflows.md)** | Une unité de travail réutilisable et conçue à l'avance : une compétence d'agent et les modèles de tâches générés pour elle. |
| **Session de conception** | La discussion dans laquelle les modèles de tâches d'un workflow sont produits et affinés. Il y en a exactement une par workflow, et elle existe avant toute exécution. |
| **[Exécution](../guides/workflow-executions.md)** | Une exécution d'un workflow : les métadonnées du workflow et de la compétence figées au moment du lancement, et le parent des `WorkflowTask`, des `Approval` et des métadonnées de messages de cette exécution. |
| **Session du workflow** | La discussion dans laquelle se déroule une exécution, c'est-à-dire l'équivalent, à l'exécution, d'une session de conception. |
| **Session de branche** | Une session dérivée d'une session du workflow lorsque le graphe de tâches de l'exécution se ramifie, afin que la branche soit traitée en parallèle du reste de l'exécution. Elle se termine par un résumé une fois ses tâches achevées. |
| **[Tenant](./tenants.md)** | La frontière organisationnelle de plus haut niveau : presque tous les enregistrements appartiennent à exactement un tenant, et aucune requête ne passe de l'un à l'autre. |
| **[Groupe d'utilisateurs](../guides/users-and-groups.md#user-groups)** | Un ensemble nommé d'utilisateurs au sein d'un tenant, doté de rôles dont hérite chaque membre. |
| **[Étiquette](../guides/tags.md)** | Un libellé valable dans tout le tenant, qui sert à classer les secrets, les serveurs MCP, les compétences d'agent, les bases de connaissances, les workflows, les simulacres d'outils et les groupes d'utilisateurs : un seul vocabulaire pour les sept. Une étiquette marquée **Contrôle d'accès** limite en outre les enregistrements qu'elle désigne aux membres des groupes qui la portent. |
| **[Compétence d'agent](../guides/agent-skills.md)** | Une procédure `SKILL.md` conservée dans un dépôt Git et versionnée comme du code ; un workflow est généré à partir d'une compétence, et une exécution suit sa révision publiée. |
| **[Base de connaissances](../guides/knowledge-bases.md)** | Un wiki rédigé par le LLM à partir de pages web et de documents enregistrés, à raison d'une page par sujet. Les agents de conception et d'exécution d'un workflow qui lui est lié y cherchent leurs informations. |
| **[Serveur MCP](../guides/mcp-servers.md)** | Un serveur Model Context Protocol enregistré, dont l'agent peut lier les outils aux tâches d'un workflow. |
| **[Secret](../guides/secrets.md)** | Un ensemble nommé d'entrées clé/valeur contenant des identifiants, référencé ailleurs sous la forme `name/key` et résolu seulement au moment de son utilisation. |
| **[Certificat d'outil](../guides/approvals.md#human-approval)** | Le certificat X.509 de courte durée qu'une tâche doit présenter à chaque appel d'outil MCP. Il fige l'ensemble des outils de la tâche au moment de son émission (lorsqu'une approbation est accordée, ou lorsque démarre une tâche pour laquelle aucune approbation n'a été demandée) et indique au nom de quelle autorité il agit. |
