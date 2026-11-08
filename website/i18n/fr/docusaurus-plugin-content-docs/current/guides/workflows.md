---
title: Workflows
sidebar_position: 3
---

# Workflows

Un workflow est une unité de travail réutilisable : une [compétence d'agent](./agent-skills.md) associée à une **liste de tâches préconçue**, ses *modèles de tâches*. Les modèles sont arrêtés *avant* toute exécution : lancer un workflow met donc immédiatement au travail, sans reconcevoir les mêmes étapes à chaque fois.

Ouvrez **Workflows** dans la barre latérale d'administration pour les gérer.

![Diagramme de flux montrant une compétence d'agent qui génère un workflow, affiné en brouillon ajusté, publié, puis lancé sous forme d'exécution.](./img/workflows-lifecycle.svg#gh-light-mode-only)
![Diagramme de flux montrant une compétence d'agent qui génère un workflow, affiné en brouillon ajusté, publié, puis lancé sous forme d'exécution.](./img/workflows-lifecycle-dark.svg#gh-dark-mode-only)

Il n'existe aucun moyen de créer un workflow vide : un workflow naît toujours de sa génération à partir d'une compétence.

## États {#statuses}

![Diagramme d'états de l'état détaillé d'un workflow : génération en cours mène à brouillon ou échec, échec peut être réécrit pour revenir à brouillon, brouillon se publie en publié, publié et modifié alternent au gré des modifications et des publications, et l'un comme l'autre peuvent être désactivés pour revenir à brouillon.](./img/workflows-status.svg#gh-light-mode-only)
![Diagramme d'états de l'état détaillé d'un workflow : génération en cours mène à brouillon ou échec, échec peut être réécrit pour revenir à brouillon, brouillon se publie en publié, publié et modifié alternent au gré des modifications et des publications, et l'un comme l'autre peuvent être désactivés pour revenir à brouillon.](./img/workflows-status-dark.svg#gh-dark-mode-only)

| État | Signification | Qui peut l'exécuter |
|---|---|---|
| `génération en cours` | La conception en arrière-plan rédige encore les modèles de tâches. | Personne |
| `brouillon` | La conception existe mais n'a jamais été publiée, ou a été désactivée. | Développeur et Super administrateur, pour les tests avant publication |
| `échec` | La conception s'est terminée sans produire de modèles. La raison s'affiche sur la page de détail et dans la discussion de conception. | Personne |
| `publié` | La conception est figée et exécutable. | Toute personne détenant le rôle Demandeur ou supérieur |
| `modifié` | Publié une fois, puis modifié. Les exécutions utilisent toujours la version publiée. | Comme `publié` |

`modifié` est un état que seuls un **Développeur**, un **Relecteur** ou un **Super administrateur** voient jamais. Pour tous les autres, le workflow apparaît comme `publié`, avec le nom, la description et les modèles de tâches enregistrés lors de la dernière publication : les modifications non publiées ne les concernent pas, et la conception qu'ils *peuvent* voir est celle que leur exécution appliquerait.

## Les écrans {#the-screens}

| Écran | Comment y accéder | Ce que vous y faites |
|---|---|---|
| Liste **Workflows** | Barre latérale d'administration → Workflows | Parcourir, filtrer par [étiquette](./tags.md) et **Exécuter** un workflow |
| Détail du workflow | Cliquez sur le nom d'un workflow | Modifier ses champs, **Abandonner les modifications**, **Ouvrir la session de conception** (Développeur) ; **Publier**, **Désactiver** (Relecteur) |
| **Modèles de tâches** | Le lien Modèles de tâches de la page de détail du workflow | Ajouter, modifier et réordonner les étapes à la main, sous forme de Tableau ou de Graphe |
| Session de conception | **Ouvrir la session de conception** sur la page de détail | Affiner les étapes en dialoguant avec l'agent de conception |

Chaque enregistrement de workflow comporte un **Nom**, les [étiquettes](./tags.md) qui le classent, la **Compétence d'agent** qu'il suit, son état, une **Description** et deux champs de prompt.

## Générer un workflow {#generating-a-workflow}

**Générer un workflow** est accessible depuis deux endroits, qui ouvrent tous deux la même boîte de dialogue sans quitter la page : l'action de ligne de la liste [Compétences d'agent](./agent-skills.md), et le bouton-icône Générer un workflow dans l'en-tête de la page de détail d'une compétence. Les deux sont désactivés tant que la compétence n'a pas publié de révision.

1. Renseignez le **Nom du workflow** (prérempli avec le nom de la compétence) et le **Prompt** décrivant le travail. Vous pouvez aussi choisir des [bases de connaissances](./knowledge-bases.md) sous **Bases de connaissances** : elles sont liées aussitôt au nouveau workflow, et l'agent de conception peut donc déjà les consulter. Comme la génération change de page, la page de détail propose d'abord d'enregistrer les modifications en cours ; refuser laisse la page intacte et ne lance pas la génération.
2. Le workflow est enregistré aussitôt à l'état `génération en cours`, et vous arrivez sur sa page de détail, qui s'actualise d'elle-même pendant le travail.
3. En arrière-plan, le prompt est envoyé comme premier message de la **session de conception** du workflow. L'agent de conception suit la compétence, décompose la demande en étapes et les enregistre comme modèles de tâches du workflow : un graphe de dépendances où chaque étape déclare quelles étapes doivent se terminer avant elle, ainsi que les éventuels [outils MCP](./workflows.md#mcp-tools-for-tasks) dont elle a besoin.
4. À la fin, la conversation de conception est résumée dans **Prompt généré**, une courte **Description** destinée aux personnes qui exécuteront le workflow est rédigée en même temps, l'état passe à `brouillon`, et une [notification](./notifications.md) vous ramène directement au workflow.

Si la conception échoue, ou se termine sans enregistrer le moindre modèle, le workflow passe à `échec` avec la raison, et une notification vous en informe. La discussion de conception reste utilisable : rédiger les modèles de tâches depuis celle-ci, ou depuis les pages d'administration Modèles de tâches, ramène le workflow à `brouillon` et efface l'échec.

La demande saisie dans la boîte de dialogue Générer un workflow n'est pas stockée sur le workflow. Elle subsiste comme premier message de la conversation de conception, et le résumé généré en reprend l'intention.

## Description et prompt {#description-and-prompt}

Un workflow comporte deux types de texte, dont un seul influe sur une exécution.

| Champ | Ce que c'est | Rédigé par | Qui peut le modifier | Qui peut le voir |
|---|---|---|---|---|
| **Description** | Une explication simple de la raison d'être du workflow. Aucune exécution ne la lit jamais. | L'IA à la génération du workflow, puis une personne | Tout Développeur | Toute personne pouvant ouvrir le workflow |
| **Prompt** | Une substitution du prompt généré | Une personne, le plus souvent en retouchant à la main le résumé de l'IA | Tout Développeur | Administrateur, Développeur, Relecteur |
| **Prompt généré** | Le résumé de la conversation de conception par l'IA | L'IA | Super administrateur uniquement | Administrateur, Développeur, Relecteur |

Le prompt en vigueur est transmis à l'agent d'exécution comme contexte de chaque exécution : **Prompt** l'emporte s'il n'est pas vide ; sinon, **Prompt généré** est utilisé. Comme la substitution commence généralement comme une copie du résumé, le champ Prompt propose une action **Afficher les différences avec le prompt généré**, qui ouvre une comparaison mot à mot des deux. Elle lit les valeurs actuellement dans le formulaire : les modifications non enregistrées sont donc comparées aussi.

La Description est ce qu'affiche la liste des workflows, et ce que la boîte de dialogue **Exécuter le workflow** affiche sous sa confirmation : la personne qui lance une exécution peut ainsi vérifier qu'elle a choisi le bon workflow. Les champs de prompt sont masqués pour tous les autres rôles, sur la page de détail, dans la colonne facultative **Prompt** de la liste et sur la page de détail d'une exécution.

### Régénérer le prompt {#regenerating-the-prompt}

Le résumé de l'IA devient obsolète à mesure que les modèles de tâches sont ajustés : **Prompt généré** propose donc une action **Générer à partir de la conversation de conception**, qui résume à nouveau la conversation de conception à la demande et enregistre aussitôt le résultat. Rien n'est résumé au moment de la publication : c'est à vous de décider s'il faut l'actualiser, et quand.

La même action est proposée dans la zone de saisie de la session de conception, sous son menu « + », où elle affiche un aperçu du changement dans la même boîte de dialogue de différences avant d'enregistrer : pratique pour régénérer sans quitter la conversation. Le menu est masqué tant que les modèles de tâches sont en cours de génération.

Les deux sont des actions de Développeur. Réécrire le résumé d'un workflow `publié` le fait passer à `modifié`, car une exécution dont le Prompt est vide se rabat sur le résumé et s'écarterait sinon de la version publiée.

## Ajuster les modèles de tâches {#adjusting-the-task-templates}

Les modèles de tâches d'un brouillon s'affinent de deux façons, à combiner librement.

**Par la discussion.** **Ouvrir la session de conception** sur la page de détail du workflow ouvre la discussion de conception : la même discussion que pour une exécution, avec la liste des modèles sur le bord gauche, pilotée par un agent de conception qui modifie directement les modèles. L'agent de conception n'exécute jamais rien. La session est partagée par chaque **Développeur** du tenant, ainsi que par les Super administrateurs et le créateur du workflow : une équipe peut donc affiner une conception ensemble, avec le même comportement de discussion partagée qu'une [session du workflow](./workflow-executions.md#the-workflow-session-screen), y compris les avatars d'expéditeur par message. Un **Relecteur** peut ouvrir la même discussion pour lire son historique avant de décider de publier, mais la zone de message est masquée : relire une conception n'inclut pas de l'orienter.

**À la main.** Les pages **Modèles de tâches** proposent une vue **Tableau** et une vue **Graphe**, un formulaire de création et une page de détail par modèle, avec les sélecteurs **Dépend de** et **Outils MCP**. Le Graphe empile les modèles sur une seule colonne verticale dans l'ordre des dépendances, chacun se ramifiant vers la droite vers les serveurs MCP dont il lie des outils, puis vers les outils eux-mêmes.

Les modèles reproduisent la structure des tâches d'une exécution (titre, description, liens de dépendance et liaisons d'outils), mais ne portent **aucun état** : le cycle de vie appartient à une exécution, pas à la conception. Les dépendances doivent pointer vers des modèles du même workflow, et un lien qui fermerait un cycle est refusé.

## Publier {#publishing}

**Publier**, sur la page de détail du workflow, est ce qui rend un workflow exécutable. C'est une action de **Relecteur** : un Développeur construit et modifie un workflow mais ne le publie plus, de sorte que la personne qui promeut une conception n'est pas celle qui l'a rédigée. Il faut au moins un modèle et aucune génération en cours.

La publication **fige la conception** : le nom du workflow, sa description, son prompt en vigueur et sa liste complète de modèles, liens de dépendance et liaisons d'outils compris, sont enregistrés comme une nouvelle version publiée, soit **v1**, **v2**, etc. Les versions précédentes sont conservées dans l'[historique des versions](#version-history). Aucune IA n'intervient ici ; actualiser le résumé est une [action distincte](./workflows.md#regenerating-the-prompt). Ajustez et republiez aussi souvent que vous le souhaitez : les exécutions déjà lancées ne sont pas affectées, car chacune a pris sa propre copie des tâches.

## Modifier un workflow publié {#editing-a-published-workflow}

Modifier un workflow après sa publication ne change pas en silence ce qui s'exécute. Enregistrer le formulaire de détail, régénérer le prompt de l'IA, ou ajouter, modifier ou supprimer un modèle de tâche, y compris par un changement de l'agent de conception dans la discussion, fait passer le workflow à `modifié`.

| Tant qu'il est `modifié` | |
|---|---|
| Ce qu'utilisent les exécutions | La **dernière version publiée** (son nom, son prompt en vigueur et ses modèles), et non les modifications, sauf si un Développeur les demande (voir [Essayer les modifications](#trying-the-edits-out)) |
| Qui peut l'exécuter | Les mêmes personnes que lorsqu'il est `publié` ; le bouton Exécuter n'est pas soumis à une autre condition |
| Qui voit les modifications | Développeur, Relecteur et Super administrateur uniquement |
| **Publier** (Relecteur) | Intègre les modifications aux futures exécutions et à ce que voient tous les autres |
| **Abandonner les modifications** (Développeur) | Jette les modifications : les modèles sont réécrits à partir de la version publiée, le nom et la description sont rétablis, le prompt de la version publiée est réinscrit, et le workflow revient à `publié` |

**Abandonner les modifications** est l'icône d'annulation dans la barre d'état de la page de détail, à côté de Publier. L'utiliser sur un workflow sans modification non publiée ne fait rien d'autre que le signaler.

Toute personne sans le rôle Développeur ou Relecteur reçoit partout la version publiée : le nom et la description du workflow dans la liste et sur la page de détail, ses écrans **Modèles de tâches**, et jusqu'aux résultats d'une recherche par nom dans la liste. Son état affiche `publié`, et un modèle de tâche ajouté depuis la dernière publication n'existe tout simplement pas pour elle. Ainsi, une refonte inachevée ne déroute jamais les personnes qui ont seulement besoin d'exécuter le workflow, et ce qu'elles voient correspond toujours à ce que ferait leur exécution.

## Historique des versions et retour en arrière {#version-history}

Chaque publication est conservée. **Historique des versions** (l'icône d'horloge dans l'en-tête de la page de détail du workflow) les liste de la plus récente à la plus ancienne, avec le numéro, le nom et la description de chaque version, ainsi que la date et l'auteur de sa publication. Seul un **Administrateur**, un **Développeur**, un **Relecteur** ou un **Super administrateur** peut le consulter : un Demandeur ou un Approbateur ne voit même pas l'icône d'horloge.

Pour revenir à une conception antérieure (Développeur) :

1. Ouvrez **Historique des versions** et cliquez sur **Restaurer** pour la version souhaitée.
2. Confirmez. Les modèles, le nom, la description et le prompt de cette version remplacent la conception actuelle du workflow, et vous revenez au workflow.
3. Vérifiez le résultat. La restauration ne **publie pas** : les exécutions continuent d'utiliser la version publiée actuelle jusqu'à ce qu'un Relecteur clique sur **Publier**, ce qui enregistre la conception restaurée comme une nouvelle version.

| État avant | État après la restauration |
|---|---|
| `publié` ou `modifié` | `modifié`, ou `publié` si vous avez restauré la dernière version, puisque plus rien ne reste alors non publié |
| `brouillon` | `brouillon` |

Vous avez changé d'avis avant de publier ? **Abandonner les modifications** rétablit la version publiée actuelle. Une version qui lie un outil d'un serveur MCP supprimé depuis ne peut pas être restaurée : la restauration est rejetée avec une erreur.

### Notes internes {#internal-notes}

Les **Notes internes** de la page de détail du workflow permettent de consigner la raison d'un retour en arrière, ou toute autre information utile à l'équipe qui exploite le workflow.

| | |
|---|---|
| Qui les voit | Administrateur, Développeur et Relecteur. Masquées pour tous les autres. |
| Qui peut les modifier | Les trois mêmes rôles. Saisissez le texte dans le champ et cliquez sur son icône d'enregistrement. |
| Effet sur le workflow | Aucun. L'enregistrement ne change pas l'état, et les exécutions ne lisent jamais les notes. |
| Versions | Non versionnées. La publication, la restauration d'une version et **Abandonner les modifications** laissent toutes les notes telles quelles. |

## Désactiver un workflow {#deactivating-a-workflow}

**Désactiver**, l'icône de mise hors tension qui apparaît à côté de Publier tant qu'un workflow est `publié` ou `modifié`, accessible au même rôle **Relecteur** que Publier, le ramène à `brouillon`. Cela retire au rôle Demandeur le droit d'exécution, le même verrou que celui d'un workflow jamais publié, tandis qu'un Développeur ou un Super administrateur peut toujours l'exécuter pour le tester. Les modèles de tâches, les deux champs de description et l'instantané publié restent exactement tels quels : une nouvelle publication le remet donc aussitôt en service.

## Exécuter un workflow {#running-a-workflow}

Cliquer sur **Exécuter** dans la liste des workflows crée une **exécution**, un enregistrement indépendant qui capture un instantané du workflow à cet instant.

![Diagramme de flux montrant le workflow publié et les simulacres d'outils choisis, copiés par valeur dans un nouvel instantané d'exécution, qui ouvre une session du workflow.](./img/workflows-snapshot.svg#gh-light-mode-only)
![Diagramme de flux montrant le workflow publié et les simulacres d'outils choisis, copiés par valeur dans un nouvel instantané d'exécution, qui ouvre une session du workflow.](./img/workflows-snapshot-dark.svg#gh-dark-mode-only)

Pour une **exécution de test**, la boîte de dialogue d'exécution liste en plus, sous **Outils simulés**, les [simulacres d'outils](./tool-mocks.md) d'un outil utilisé par l'une des tâches du workflow, ainsi que tous les simulacres d'un outil intégré ; en cocher un simule cet outil pour cette exécution, de sorte qu'un test avant publication peut être répété sans les effets de bord de l'outil. Une exécution de test désigne un workflow à l'état `brouillon`, ou les modifications non publiées d'un workflow à l'état `modifié` (voir ci-dessous). Sinon, la boîte de dialogue ne propose aucun simulacre, et en demander un malgré tout est refusé : une exécution qui aurait l'air réelle et ne ferait discrètement rien serait pire que pas d'exécution du tout.

### Essayer les modifications {#trying-the-edits-out}

Tant qu'un workflow est `modifié`, il contient deux conceptions, et la boîte de dialogue d'exécution demande donc à un **Développeur** laquelle exécuter :

| Choix | Ce qui est exécuté | Comment c'est enregistré |
|---|---|---|
| **Version publiée** | La conception capturée lors de la dernière publication, celle que reçoivent tous les autres | Une vraie demande |
| **Modifications non publiées** | La conception telle qu'elle se trouve actuellement dans l'éditeur | Une **exécution de test** : elle peut simuler des outils et est exclue des [métriques d'exploitation](../operations/metrics.md) |

La version publiée est présélectionnée, car c'est ce que signifie ici une vraie demande. Choisir les modifications permet de répéter une refonte de bout en bout avant de s'y engager, et c'est une action de Développeur, puisque personne d'autre ne peut voir ces modifications. Ce choix n'apparaît pas pour un workflow à l'état `brouillon` ou `publié` : il n'y a qu'une seule conception à exécuter.

Tout ce dont l'exécution a besoin est copié dans celle-ci à son démarrage : les modifications ultérieures ne l'atteignent donc jamais.

| Copié dans l'exécution | Provenance |
|---|---|
| Nom et prompt en vigueur | La dernière version publiée, ou l'état actuel de l'éditeur pour un workflow à l'état `brouillon` ou lorsqu'un Développeur a choisi les modifications non publiées |
| Modèles de tâches, sous forme de tâches `en attente` avec leurs dépendances et liaisons d'outils | La même conception |
| La révision de la compétence d'agent à laquelle l'exécution est rattachée | La révision publiée de la compétence |
| Les simulacres d'outils choisis, par valeur | Les simulacres tels qu'ils sont à ce moment-là |

Vous arrivez ensuite sur la **session du workflow**, la discussion dans laquelle se déroule l'exécution. Elle s'ouvre sur un message de lancement fixe et l'agent se met aussitôt au travail : les tâches ont été approuvées par la publication, il n'y a donc rien à confirmer d'abord. À partir de là, l'exécution se comporte comme n'importe quelle discussion, y compris les surfaces interactives affichées et leurs boutons. Le guide [Exécutions de workflows](./workflow-executions.md) décrit cet écran.

### Comment l'agent traite les tâches {#how-the-agent-works-through-the-tasks}

L'agent d'exécution liste les tâches de l'exécution, choisit la prochaine tâche exécutable (une tâche `en attente` dont toutes les dépendances sont terminées), la marque `en cours`, effectue le travail selon les consignes de la compétence, puis la marque `terminé`, `échec` ou `ignoré`. Lorsque toutes les tâches ont atteint un état final, une [notification](./notifications.md) signale que l'exécution est finie.

Vous pouvez suivre l'évolution des états en direct dans la vue **Tâches du workflow** de l'exécution, en lecture seule, sous forme de Tableau ou de Graphe. La liste des tâches de l'exécution est fixe (c'est celle figée lors de la publication du workflow) : l'agent ne fait donc qu'avancer chaque tâche d'un état à l'autre, sans jamais en ajouter ni en retirer.

**Tâches qui doivent attendre l'heure prévue.** Écrivez cette exigence en toutes lettres dans la description de la tâche : « exécuter après 9 h demain », « pas avant le 1er du mois ». Lorsque l'agent atteint cette tâche avant l'heure, il la laisse `en attente`, indique dans la discussion quand l'exécution reprendra, et s'arrête. Sa session affiche **Planifiée** jusque-là, puis A2Flow la reprend de lui-même à l'heure dite, sans que personne ait besoin de garder la discussion ouverte. Une heure écrite sans fuseau horaire est interprétée dans le fuseau horaire local du déploiement. Les branches traitées dans d'autres sessions continuent d'avancer pendant qu'une session attend, et un message envoyé à la session en attente la fait reprendre aussitôt.

## Outils MCP des tâches {#mcp-tools-for-tasks}

Les tâches peuvent utiliser les outils des serveurs enregistrés sous [Serveurs MCP](./mcp-servers.md). Les outils sont liés lors de la conception et contrôlés lors de l'exécution.

![Diagramme de flux montrant une liaison d'outil établie à la conception, copiée sur la tâche au lancement, puis vérifiée au moment de l'appel : si l'outil est lié à une tâche en cours, l'appel passe ; sinon, il est refusé avec la liste des outils autorisés.](./img/workflows-tool-binding.svg#gh-light-mode-only)
![Diagramme de flux montrant une liaison d'outil établie à la conception, copiée sur la tâche au lancement, puis vérifiée au moment de l'appel : si l'outil est lié à une tâche en cours, l'appel passe ; sinon, il est refusé avec la liste des outils autorisés.](./img/workflows-tool-binding-dark.svg#gh-dark-mode-only)

Pendant la conception, l'agent peut lister les outils proposés par les serveurs que vous pouvez voir (un serveur masqué par une [étiquette de contrôle d'accès](./tags.md) en est exclu) et donner à une étape ceux dont elle a besoin. Ces liaisons résident sur le modèle et sont copiées sur les tâches de l'exécution à son démarrage.

À l'exécution, chaque appel est vérifié avant d'atteindre un serveur : la paire `(serveur, outil)` doit être liée à une tâche en cours. Les appels à des outils non liés sont refusés avec un message listant ce qui est autorisé : un agent partagé entre plusieurs workflows ne peut donc jamais recourir à un outil qui n'a pas été accordé à une tâche. Une tâche à laquelle une [approbation](./approvals.md) est également attachée est aussi soumise à celle-ci.

**Lier des outils à la main.** Les formulaires de modèle comportent un sélecteur **Outils MCP** en deux temps : choisissez un serveur dans une boîte de dialogue paginée, puis ajoutez l'un de ses outils depuis une liste déroulante, chaque outil ajouté devenant une puce amovible. Seul le serveur choisi est interrogé : ouvrir le formulaire ne sollicite donc pas tous les serveurs enregistrés ; un serveur injoignable le signale à la place de sa liste d'outils, et un outil déjà lié conserve sa puce dans tous les cas. Les outils liés apparaissent sous forme de puces dans la colonne **Outils** des listes Modèles de tâches et Tâches du workflow.

**Outils dont l'entrée ne nécessite pas d'approbation.** La puce de chaque outil sous **Outils sélectionnés** porte un petit bouton en forme de bouclier à côté de son bouton de retrait. Cliquez dessus : les valeurs avec lesquelles cet outil est appelé ne font plus partie de ce qu'une [approbation](./approvals.md) couvrant l'étape demande à une personne d'accepter ; l'approbation elle-même s'applique toujours, et l'étape continue de l'attendre. L'icône et la teinte du bouton changent pour montrer l'état actuel de l'outil, et le survol indique cet état et l'effet d'un clic.

Ne cliquez dessus que pour un outil qui **lit** : une liste, une recherche, une vérification d'état. Cette fonction existe pour deux raisons, qui concernent toutes deux le travail en lecture seule :

| | |
|---|---|
| Il n'y a rien à peser | Personne n'a besoin d'accepter les arguments d'une requête qui ne change rien |
| Les valeurs ne peuvent pas encore être connues | Une étape peut avoir à chercher une information pour décider de la suite : elle ne peut donc pas indiquer à l'avance ce qu'elle demandera |

Laissez l'état par défaut pour tout ce qui écrit, supprime, dépense ou envoie. Par défaut, l'entrée « nécessite une approbation » : un outil ajouté et laissé tel quel conserve donc une entrée limitée. Un outil passé à « ne nécessite pas d'approbation » porte le libellé **Toute entrée** sur l'approbation que l'exécution demande ensuite : l'approbateur voit ainsi quels outils n'ont pas de limites, sans avoir à le déduire.

**Outils qui interrogent l'initiateur.** Certains outils s'arrêtent en cours d'appel pour poser une question à la personne qui exécute le workflow : Azure MCP Server demande un consentement avant chaque opération sur un secret. Indiquez à l'agent de conception quel outil de quelle tâche agit ainsi, dans le prompt à la génération du workflow ou dans sa session de conception, et il marque l'outil comme interrogeant l'initiateur. Une étape dotée d'un tel outil attend que son initiateur la reprenne avant de démarrer, pour qu'il soit dans la discussion et puisse répondre ([Confirmations d'un serveur MCP](./workflow-executions.md#mcp-server-confirmations)). Un outil non marqué ainsi n'est pas autorisé à poser des questions. Le formulaire d'administration n'a aucun contrôle pour cette marque : il conserve celle définie par l'agent de conception. Dans la chronologie des tâches d'une exécution, la boîte de dialogue **Outils liés** affiche pour un tel outil le libellé **Interroge l'initiateur pendant l'appel**.

**Titres des tâches.** Ces deux listes affichent tous les enregistrements au lieu de les paginer, ce qui permet à la colonne **Dépend de** de servir de renvoi : chaque dépendance est nommée par son titre, et survoler cette puce met en évidence la ligne visée. L'agent de conception est tenu à des titres brefs à l'impératif (2 à 4 mots, 50 caractères) pour qu'ils restent lisibles en puces ; un titre plus long est refusé avec une note lui demandant de déplacer le détail dans la description. La limite s'impose à l'agent, pas aux personnes : un titre modifié via le formulaire d'administration peut aller jusqu'à 200 caractères, et celui qui déborde de sa puce est tronqué et révélé au survol.

## Bases de connaissances {#knowledge-bases}

Choisissez des bases de connaissances sous **Bases de connaissances** sur la page de détail du workflow et cliquez sur **Enregistrer** : l'agent de conception et l'agent d'exécution les consulteront pendant leur travail. Voir [Bases de connaissances](./knowledge-bases.md#linking-a-knowledge-base-to-a-workflow). Ce choix ne fait pas partie de la conception publiée : le changer ne marque donc jamais le workflow comme modifié.

## Supprimer un workflow {#deleting-a-workflow}

Supprimer un workflow supprime aussi ses modèles de tâches, sa version publiée et sa session de conception. Les [exécutions](./workflow-executions.md) existantes subsistent : chacune conserve son propre instantané, et l'historique d'une exécution reste lisible une fois disparu le workflow dont elle provient.
