---
title: Concevoir un workflow
sidebar_position: 2
---

# Concevoir un workflow

Un workflow n'est jamais créé à partir de rien. Il est généré à partir d'une [compétence d'agent](../guides/agent-skills.md), un dépôt Git qu'A2Flow clone et maintient à jour, puis affiné jusqu'à ce que la conception mérite d'être figée.

![Automate à états montrant un workflow qui part d'une compétence d'agent publiée, passe par génération en cours pour aboutir à brouillon ou échec, puis va de brouillon à publié et modifié, la publication ramenant de modifié à publié.](./img/workflow-design-status.svg#gh-light-mode-only)
![Automate à états montrant un workflow qui part d'une compétence d'agent publiée, passe par génération en cours pour aboutir à brouillon ou échec, puis va de brouillon à publié et modifié, la publication ramenant de modifié à publié.](./img/workflow-design-status-dark.svg#gh-dark-mode-only)

Une compétence sans révision publiée ne permet ni de générer un workflow, ni de lancer une exécution. Le clone est ce que suivent les deux agents : tant qu'il n'existe pas, ils n'ont rien à suivre.

## L'exécution de conception {#the-design-run}

La génération enregistre aussitôt le workflow et effectue le travail de conception en arrière-plan. Il s'agit d'une véritable exécution d'agent qui interroge un LLM : l'enregistrement s'actualise donc de lui-même au fil du travail, sans monopoliser un écran.

1. Le prompt saisi dans la boîte de dialogue Générer est envoyé comme premier message de la **session de conception** du workflow.
2. L'agent de conception lit la compétence, décompose la demande en étapes et les enregistre sous forme de **modèles de tâches** : un graphe de dépendances dans lequel chaque étape déclare celles qui doivent se terminer avant elle.
3. Pour chaque étape qui en a besoin, il lie les outils MCP que cette étape est autorisée à appeler.
4. La conversation est résumée dans le **Prompt généré** du workflow, le texte transmis à chaque exécution comme contexte, ainsi que dans une courte **Description** destinée aux personnes qui l'exécutent, et le workflow passe à l'état `brouillon`.

La demande saisie dans la boîte de dialogue Générer n'est pas conservée comme champ du workflow. Elle subsiste en tant que premier message de la conversation de conception : c'est pourquoi la même discussion peut être rouverte plus tard pour affiner le résultat, et pourquoi une exécution qui n'a rien enregistré laisse tout de même un point de départ exploitable plutôt qu'un enregistrement vide.

## Ce que contient un modèle de tâche {#what-a-task-template-carries}

| Un modèle contient | Remarques |
|---|---|
| **Titre et description** | L'étape telle que la lira l'agent d'exécution. Les titres restent courts pour s'afficher sous forme de puces dans les listes de tâches. |
| **Dépend de** | Des liens vers d'autres modèles du même workflow. Un lien qui fermerait un cycle est refusé. |
| **Outils MCP** | Les paires `(serveur, outil)` que cette étape est autorisée à appeler, chacune indiquant si une [approbation](./approvals.md) couvrant l'étape doit encadrer les valeurs avec lesquelles l'outil est appelé. Les outils en lecture seule sont marqués comme ne nécessitant pas d'approbation de leur entrée ; c'est le seul endroit où ce choix peut être fait, car une exécution ne peut pas modifier ses propres liaisons. |
| *Pas d'état* | Le cycle de vie appartient à une exécution, et non à la conception. |

Les modèles s'affinent depuis la discussion de conception, depuis les formulaires d'administration ou en combinant les deux ; ces écrans sont décrits dans [Workflows](../guides/workflows.md#adjusting-the-task-templates). L'agent de conception modifie directement les modèles et n'exécute rien : c'est ce qui permet de partager sans risque la session de conception avec toute une équipe.

## Lier les outils à la conception {#binding-tools-at-design-time}

Choisir des outils et les appeler obéissent délibérément à des règles différentes.

| Opération | Qui l'effectue | Quelle restriction s'applique |
|---|---|---|
| **Lister** ce que propose un serveur | L'agent de conception, au moment de décider | Aucune : découvrir les outils est tout l'objet d'une exécution de conception |
| **Appeler** un outil | L'agent d'exécution, en cours d'exécution | Limité aux outils liés à une tâche que l'exécution a actuellement en cours ; voir [Passerelle et proxy MCP](./mcp-gateway-and-proxy.md) |

Une liaison écrite ici n'est donc pas une simple indication donnée au modèle. C'est l'autorisation que la [passerelle](./mcp-gateway-and-proxy.md) applique à l'exécution, et l'ensemble que le [certificat](./approvals.md) de la tâche fige dès le démarrage de celle-ci, ou dès l'octroi de son approbation si elle s'avère en nécessiter une.

## Publication {#publishing}

La publication fige la conception. Le nom du workflow, sa description, son prompt en vigueur et la liste complète de ses modèles, liens de dépendance et liaisons d'outils compris, sont enregistrés sous la forme d'une nouvelle version publiée numérotée ; les versions antérieures restent dans l'[historique des versions](../guides/workflows.md#version-history). Aucune IA n'intervient à ce stade : la publication est un instantané, et non une relecture.

Toute modification ultérieure fait passer le workflow à l'état `modifié` et ne change rien à ce qui s'exécute : les exécutions continuent d'utiliser la version publiée jusqu'à une nouvelle publication. Une exécution déjà en cours n'est de toute façon pas affectée, car elle a pris sa propre copie à son démarrage.

La version publiée est aussi la seule que la plupart des gens voient. Tant qu'un workflow est à l'état `modifié`, son nom, sa description, son prompt et ses modèles de tâches non publiés ne sont visibles que par un **Développeur** ou un **Super administrateur** ; tous les autres rôles lisent en permanence la version publiée, y compris dans la liste des workflows, où la recherche et le tri par nom suivent aussi le nom publié, et voient l'état `publié`. Un Développeur peut exécuter l'une ou l'autre conception : la version publiée comme une vraie demande, ou les modifications comme une [exécution de test](../guides/workflows.md#trying-the-edits-out), qui peut simuler ses outils et reste exclue des métriques d'exploitation.
