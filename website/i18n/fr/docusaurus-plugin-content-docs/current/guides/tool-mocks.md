---
title: Simulacres d'outils
sidebar_position: 8
---

# Simulacres d'outils

Un simulacre d'outil est un substitut qui permet d'éprouver de bout en bout l'exécution d'un workflow en **brouillon** sans les effets de bord de ses outils. Un outil simulé n'est pas appelé : c'est le résultat configuré dans le simulacre qui est renvoyé à sa place. Aucune requête n'atteint donc le serveur MCP, aucune approbation n'est enregistrée et personne ne reçoit d'e-mail.

Ouvrez **Simulacres d'outils** dans la barre latérale d'administration pour les gérer.

![Organigramme montrant l'agent qui appelle un outil, vérifie si celui-ci est simulé pour cette exécution, puis atteint le véritable serveur MCP ou reçoit la réponse suivante du simulacre sans contacter aucun serveur.](./img/tool-mocks-decision.svg#gh-light-mode-only)
![Organigramme montrant l'agent qui appelle un outil, vérifie si celui-ci est simulé pour cette exécution, puis atteint le véritable serveur MCP ou reçoit la réponse suivante du simulacre sans contacter aucun serveur.](./img/tool-mocks-decision-dark.svg#gh-dark-mode-only)

## Utiliser un simulacre {#using-one}

1. Créez un simulacre pour l'outil à remplacer.
2. Sur un workflow en **brouillon**, cliquez sur **Exécuter** ; sur un workflow `modifié`, faites de même en choisissant **Modifications non publiées** dans la boîte de dialogue. Sous **Outils simulés**, celle-ci liste les simulacres des outils utilisés par l'une des tâches de ce workflow, ainsi que tous les simulacres d'outils intégrés.
3. Cochez ceux que cette exécution doit utiliser, puis lancez l'exécution.

Un simulacre d'un outil qu'aucune tâche de ce workflow n'utilise n'apparaît pas dans la liste : liez d'abord cet outil à une tâche. Les simulacres ne sont proposés que pour une [exécution de test](./workflows.md#trying-the-edits-out) ; la boîte de dialogue n'en propose aucun pour l'exécution d'une conception publiée, et une demande explicite est refusée. Le lancement de l'exécution **copie** sur celle-ci le contenu actuel de chaque simulacre choisi : modifier ou supprimer un simulacre par la suite ne change donc jamais une exécution déjà en cours — et ne peut jamais retransformer en silence un appel simulé en appel réel.

La simulation se choisit **outil par outil**, et non par exécution, car une exécution à blanc n'est utile que si elle reste réaliste. Un workflow qui interroge un système puis y écrit peut ne simuler que l'écriture : la lecture atteint toujours le véritable serveur, et l'agent raisonne toujours sur des données réelles.

## Contenu d'un simulacre {#what-a-mock-holds}

| Champ | Remarques |
|---|---|
| **Nom** / **Description** | Ce qui permet de le reconnaître dans la boîte de dialogue d'exécution. |
| **Cible** | Soit un outil d'un [serveur MCP enregistré](./mcp-servers.md) — choisissez **Sélectionner un serveur MCP**, sélectionnez le serveur, puis choisissez le **Nom de l'outil** dans la liste chargée depuis ce serveur —, soit un outil A2Flow **intégré**. |
| **Réponses** | Une liste ordonnée, indexée par rang d'appel. |

Le seul outil intégré actuellement simulable est `request_approval` : celui dont les effets de bord exigeraient sinon l'intervention d'une personne pour que l'exécution puisse continuer.

### Ce que renvoie l'outil {#what-the-tool-returns}

Une fois l'outil choisi, **Format de sortie** s'ouvre en dessous et affiche la description propre à l'outil ainsi que la forme qu'il annonce renvoyer. Servez-vous-en comme référence pour ce que vous écrivez ensuite : un simulacre n'est utile que si le workflow peut le lire comme il lirait la réalité.

Tous les outils n'indiquent pas ce qu'ils renvoient. Lorsque c'est le cas, le panneau le signale et vous laisse décider de la forme.

### Réponses {#responses}

La première réponse répond au premier appel de l'exécution à cet outil, la deuxième au deuxième, et ainsi de suite. Une fois la liste épuisée, la dernière réponse se répète : une seule réponse se comporte donc comme une constante. C'est ce qui permet à un même simulacre d'exprimer un *scénario* plutôt qu'une valeur fixe : approuver la première demande, rejeter la deuxième et voir comment le workflow gère les deux.

| Type | Signification |
|---|---|
| Structuré (objet JSON) | Un objet JSON placé dans le contenu structuré du résultat — pour un outil dont l'appelant lit des champs du résultat |
| Texte | Une chaîne placée dans le contenu textuel du résultat |
| Erreur | Un message renvoyé comme appel en échec : l'agent voit l'outil signaler une erreur |

Lorsque l'outil déclare un format de sortie, une réponse **Structuré (objet JSON)** propose **Insérer depuis le schéma** : cette action remplit la zone avec cette forme, clés comprises, pour que vous modifiiez des valeurs au lieu de recopier la structure. Elle remplace le contenu de la zone et demande d'abord confirmation si vous y avez déjà écrit quelque chose.

## Étiquettes {#tags}

Le formulaire de création et la page de détail d'un simulacre d'outil comportent un sélecteur **Étiquettes**, et la liste possède une colonne **Étiquettes** filtrable. Ces étiquettes relèvent du vocabulaire commun à tout le tenant que partagent les secrets, les serveurs MCP et les autres registres étiquetables — voir [Étiquettes](./tags.md) pour savoir comment les attacher et filtrer.

## Ce qu'un simulacre ne contourne pas {#what-a-mock-does-not-skip}

Un simulacre permet de passer outre l'effet de bord, pas les règles. Un appel simulé reste vérifié par rapport aux outils que la tâche en cours de l'exécution a le droit d'utiliser et par rapport à toute [approbation](./approvals.md) que cette tâche attend : un workflow qui serait refusé en production l'est donc aussi lors de son exécution à blanc. Il est également vérifié par rapport aux **entrées** autorisées par cette approbation : une exécution à blanc détecte ainsi un appel que l'approbateur n'aurait pas autorisé au lieu de le laisser passer. Une demande d'approbation simulée valide toujours sa destination et les appels qu'elle déclare : un workflow qui nomme un approbateur non éligible — ou qui déclare des appels ne correspondant pas à ce que feraient ses étapes — échoue lors d'une exécution à blanc exactement comme en conditions réelles.

## Voir ce qu'a fait un appel simulé {#seeing-what-a-mocked-call-did}

C'est dans la transcription de la discussion de l'exécution qu'on inspecte un appel simulé : sa ligne d'outil se déplie pour afficher les arguments et le résultat, avec le badge **Simulé**. Il n'apparaît volontairement pas sur la page [Appels d'outils](./workflow-executions.md#tool-invocations) de l'exécution : cette page consigne les décisions réellement prises par la passerelle MCP, et un appel simulé ne l'atteint jamais. L'exécution elle-même porte le badge **Simulé** dans la [liste des exécutions](./workflow-executions.md).
