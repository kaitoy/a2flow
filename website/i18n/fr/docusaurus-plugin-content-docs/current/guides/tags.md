---
title: Étiquettes
sidebar_position: 10
---

# Étiquettes

Les étiquettes sont les libellés servant à classer les enregistrements. Un même vocabulaire est partagé par les sept registres étiquetables : une étiquette `aws` filtre donc aussi bien les secrets que les serveurs MCP.

![Organigramme montrant un vocabulaire d'étiquettes commun par tenant, appliqué à sept registres étiquetables : Secrets, Serveurs MCP, Compétences d'agent, Bases de connaissances, Workflows, Simulacres d'outils et Groupes d'utilisateurs.](./img/tags-vocabulary.svg#gh-light-mode-only)
![Organigramme montrant un vocabulaire d'étiquettes commun par tenant, appliqué à sept registres étiquetables : Secrets, Serveurs MCP, Compétences d'agent, Bases de connaissances, Workflows, Simulacres d'outils et Groupes d'utilisateurs.](./img/tags-vocabulary-dark.svg#gh-dark-mode-only)

Ouvrez **Étiquettes** dans la barre latérale d'administration pour organiser le vocabulaire. Chaque étiquette comporte un **Nom**, unique au sein du tenant, une **Description** facultative, une **couleur** choisie dans une palette fixe de huit teintes — toute autre valeur de couleur est refusée — et une case à cocher **Contrôle d'accès**, décochée par défaut, qui transforme l'étiquette, simple libellé, en barrière (voir [Étiquettes de contrôle d'accès](#access-control-tags)).

Créer ou modifier une étiquette ordinaire exige le rôle Administrateur **ou** Développeur, soit l'union des rôles autorisés à écrire sur l'une des sept ressources étiquetables : une étiquette peut donc toujours être créée par la personne qui s'apprête à en avoir besoin. Il en va autrement d'une étiquette dont la case **Contrôle d'accès** est cochée : seul un administrateur (ou un super administrateur) peut la créer, en modifier un champ quelconque ou la supprimer. Un développeur voit une étiquette de contrôle d'accès existante entièrement en lecture seule — la case à cocher comme valeur fixe, les autres champs en texte brut, sans bouton Enregistrer ni Supprimer — et peut toujours créer ou modifier une étiquette ordinaire. La lecture reste ouverte, comme dans toutes les autres sections.

## Attacher des étiquettes à un enregistrement {#attaching-tags-to-a-record}

Le formulaire de création et la page de détail de chaque enregistrement étiquetable comportent un sélecteur **Étiquettes** : la sélection en cours s'affiche sous forme de puces colorées amovibles au-dessus d'un bouton **Sélectionner des étiquettes…**, si bien que la hauteur du champ dépend de la sélection et non de la taille du vocabulaire.

1. Cliquez sur **Sélectionner des étiquettes…**. La boîte de dialogue présente tout le vocabulaire sous forme de grille de puces colorées renvoyées à la ligne, chacune servant de bascule. Une puce activée prend un remplissage plus soutenu *et* une coche en tête : son état ne repose donc jamais sur la seule couleur.
2. Affinez la grille si nécessaire. Deux filtres se combinent : un champ de nom et une rangée des huit nuanciers de la palette, que l'on peut activer en nombre quelconque. Tous les désactiver revient à effacer le filtre.
3. Confirmez avec **Sélectionner**, ou abandonnez le brouillon avec **Annuler**. Une étiquette sélectionnée puis masquée par un filtre reste sélectionnée.

L'attachement d'étiquettes dépend du rôle d'écriture propre à l'enregistrement, indépendamment de ce qui a permis de créer l'étiquette elle-même.

## Filtrer par étiquette {#filtering-by-tag}

Chaque liste étiquetable possède une colonne **Étiquettes** qui affiche les puces de chaque enregistrement, et le menu de son en-tête propose une sélection multiple. La colonne garde chaque rangée du tableau sur une seule ligne : elle affiche autant de puces que sa largeur actuelle le permet et compte le reste dans une dernière puce `+N`. Cliquez sur cette puce pour ouvrir une boîte de dialogue listant toutes les étiquettes de l'enregistrement, chacune affichant sa description au survol. Élargissez la colonne, en faisant glisser son bord ou en masquant une autre colonne, et les étiquettes comptées réapparaissent sous forme de puces. La sélection est **conjonctive**, ce que le menu indique par « Filtrer (tous) » : un enregistrement doit donc porter *toutes* les étiquettes choisies, et en ajouter une restreint le résultat. Le filtre s'applique à l'ensemble des données, et pas seulement à la page affichée.

Les étiquettes constituent un axe distinct des autres filtres de colonne, mais elles suivent la même règle de visibilité : masquer la colonne Étiquettes via le [sélecteur de colonnes](./admin-ui.md) efface le filtre par étiquette, exactement comme masquer une autre colonne efface son propre filtre.

## Étiquettes de contrôle d'accès {#access-control-tags}

Une étiquette dont la case **Contrôle d'accès** est cochée restreint la visibilité des enregistrements auxquels elle est attachée. Sa puce porte un symbole de cadenas partout où elle apparaît — dans la colonne **Aperçu** de la liste des étiquettes, dans la colonne **Étiquettes** d'un enregistrement et dans le sélecteur —, et la liste des étiquettes gagne une colonne **Contrôle d'accès** sur laquelle vous pouvez filtrer.

L'accès est déterminé par vos [groupes d'utilisateurs](./users-and-groups.md#user-groups) : un groupe porte ses propres étiquettes, et les étiquettes de tous vos groupes sont mises en commun.

| Un enregistrement porte… | Vous le voyez lorsque… |
|---|---|
| Aucune étiquette de contrôle d'accès (uniquement des étiquettes ordinaires, ou aucune) | Toujours : les étiquettes ordinaires ne restreignent jamais rien |
| Une ou plusieurs étiquettes de contrôle d'accès | Vos groupes, à eux tous, les portent **toutes** |

Un enregistrement que vous n'avez pas le droit de voir est tout simplement absent : il ne figure pas dans la liste, et l'ouverture d'un lien direct indique qu'il est introuvable. Un administrateur ou un super administrateur voit tout : un administrateur est exempté de toute étiquette de contrôle d'accès, et un super administrateur agit en outre à l'échelle de la plateforme et n'appartient à aucun groupe, si bien qu'aucune autre règle ne pourrait l'atteindre non plus.

Un garde-fou s'applique lors de l'étiquetage : **vous ne pouvez pas attacher une étiquette de contrôle d'accès que vos groupes ne portent pas.** La sauvegarde est rejetée avec une erreur, car elle vous masquerait l'enregistrement au prochain chargement de la page. Demandez d'abord à un administrateur de vous ajouter à un groupe portant cette étiquette. L'étiquetage d'un *groupe d'utilisateurs* est exempté : c'est précisément ainsi qu'un administrateur accorde l'accès.

La restriction porte sur les personnes pouvant ouvrir, modifier, exécuter ou supprimer un enregistrement. Ce qu'un enregistrement utilise en coulisses n'est pas concerné : un workflow s'exécute toujours avec la compétence d'agent à partir de laquelle il a été généré et les secrets référencés par ses serveurs MCP, même pour un demandeur qui ne pourrait pas ouvrir lui-même cette compétence ou ce secret.

La conception de workflows constitue l'exception : donner un outil à une étape revient à utiliser vous-même le serveur MCP. Vous ne pouvez lier que des outils de serveurs que **vous** pourriez ouvrir, que vous les choisissiez dans le sélecteur **Outils MCP** d'un modèle de tâche ou que vous le demandiez à l'agent de conception, qui agit en votre nom. Un serveur portant une étiquette de contrôle d'accès que vos groupes n'ont pas n'apparaît jamais dans la liste d'outils de l'agent, et toute tentative de liaison est rejetée comme si le serveur n'existait pas. Un outil déjà lié à une étape par une personne qui pouvait le voir reste en place lorsque vous modifiez l'étape, et **Abandonner les modifications** rétablit les liaisons publiées telles quelles.

## Étiquettes des exécutions de workflow et des approbations {#execution-and-approval-tags}

Une [exécution de workflow](./workflow-executions.md) affiche elle aussi une colonne et un champ **Étiquettes**, tout comme l'[approbation](./approvals.md) qui lui est rattachée — mais en lecture seule, et hors des sept registres étiquetables ci-dessus. Lorsqu'une exécution démarre, elle copie les étiquettes que porte alors son workflow ; modifier ensuite les étiquettes du workflow, ou le supprimer, ne change jamais ce qu'affiche une exécution déjà commencée. Ces deux écrans n'ont ni sélecteur **Étiquettes** ni filtre par étiquette sur leurs listes : attacher et détacher des étiquettes se fait uniquement sur le workflow lui-même.

Une étiquette de contrôle d'accès ainsi copiée continue de protéger l'exécution et ses approbations, exactement comme elle protège le workflow : si vos groupes ne portent plus une étiquette copiée par l'exécution, l'exécution et toutes ses approbations disparaissent de vos listes et de vos liens directs — même si vous avez lancé l'exécution vous-même ou en êtes l'approbateur désigné. Il en va de même pour tout ce que vous pourriez faire au sein de l'exécution : envoyer un message dans sa discussion, ouvrir ses tâches, approuver ou rejeter l'une de ses approbations échouent comme si l'exécution n'existait pas. Seuls un administrateur ou un super administrateur en sont exemptés, comme pour toute étiquette de contrôle d'accès. L'étiquette doit être attachée au workflow *avant* son exécution ; modifier ensuite les étiquettes du workflow n'atteint jamais les exécutions déjà commencées, puisque la copie a lieu une seule fois, au moment où l'exécution démarre.

Une étiquette de contrôle d'accès copiée sur une exécution détermine aussi à qui celle-ci peut [demander une approbation](./approvals.md#human-approval) : pour s'adresser à une personne, il faut que l'un de ses groupes porte chacune de ces étiquettes présentes sur l'exécution, et pour s'adresser à un [groupe d'utilisateurs](./users-and-groups.md#user-groups), il faut que le groupe lui-même les porte. Sinon, la demande est refusée, car cette personne ou ce groupe ne pourrait jamais la voir pour statuer. Un administrateur est exempté en tant que destinataire individuel, puisqu'un administrateur contourne aussi ces étiquettes partout ailleurs ; un groupe d'utilisateurs ne bénéficie d'aucune exemption de ce type, même si un administrateur figure parmi ses membres.

## Renommer et supprimer {#renaming-and-deleting}

**Renommer est sans risque à tout moment.** Les enregistrements référencent une étiquette par son identité, jamais par son nom : tous ceux qui la portent suivent donc le nouveau nom sans aucune resynchronisation — c'est d'ailleurs toute la raison pour laquelle les étiquettes sont enregistrées à l'avance au lieu d'être saisies librement sur chaque enregistrement.

**Supprimer** une étiquette fonctionne à l'inverse : au lieu d'être bloquée par les enregistrements qui la portent, elle est retirée de tous. La confirmation l'indique. Supprimer une étiquette dont la case **Contrôle d'accès** est cochée exige un administrateur ou un super administrateur, comme pour la modifier ; supprimer une étiquette ordinaire reste ouvert à un développeur.
