---
title: Approbations
sidebar_position: 5
---

# Approbations

Une approbation est le moyen par lequel une exécution s'arrête pour attendre une personne. L'agent en demande une en cours d'exécution, l'approbateur désigné décide dans la discussion, et cette décision débloque les outils des étapes qu'elle couvre.

## Approbation humaine {#human-approval}

Quand une tâche exige un feu vert explicite avant que l'agent n'agisse, par exemple pour une opération destructive ou irréversible, l'agent demande une approbation et se met en pause.

![Diagramme de séquence d'une demande d'approbation : l'agent d'exécution demande une approbation, A2Flow notifie l'approbateur et l'exécution se met en pause, l'approbateur décide, puis A2Flow accorde un certificat à chaque étape couverte et reprend l'exécution.](./img/approvals-sequence.svg#gh-light-mode-only)
![Diagramme de séquence d'une demande d'approbation : l'agent d'exécution demande une approbation, A2Flow notifie l'approbateur et l'exécution se met en pause, l'approbateur décide, puis A2Flow accorde un certificat à chaque étape couverte et reprend l'exécution.](./img/approvals-sequence-dark.svg#gh-dark-mode-only)

### À qui s'adresse la demande {#who-is-asked}

Une demande s'adresse à **exactement un destinataire**, jamais aux deux et jamais à aucun.

| Destinataire | Qui est notifié | Qui peut décider |
|---|---|---|
| **Un utilisateur** | Cette personne seule | Cette personne seule |
| **Un [groupe d'utilisateurs](./users-and-groups.md#user-groups)** | Chaque membre ayant le rôle Approbateur, avec sa propre notification | N'importe lequel d'entre eux : la **première** décision tranche |

S'adresser à un groupe évite qu'une approbation reste bloquée par la disponibilité d'une seule personne. Un groupe dont aucun membre ne peut approuver est refusé d'emblée, car une telle demande ne pourrait jamais être tranchée. Il en va de même d'un destinataire qui ne porte pas toutes les [étiquettes de contrôle d'accès](./tags.md#execution-and-approval-tags) de l'exécution, car il ne pourrait jamais voir la demande pour en décider. Rien ne fait disparaître les notifications des autres membres une fois que quelqu'un a décidé ; elles cessent simplement de permettre une action. La personne qui a réellement décidé est enregistrée, car le nom du groupe ne suffit pas à répondre à la question « qui a approuvé ceci ? ».

L'agent a pour consigne de privilégier un groupe lorsque n'importe quel membre d'une équipe peut décider, et de désigner une seule personne lorsque la compétence l'exige.

### Décider {#deciding}

L'agent explique la demande en texte clair, et les commandes apparaissent en dessous dans la discussion, mais **uniquement pour l'approbateur désigné**. Pour un groupe, plusieurs personnes peuvent les avoir en même temps. Tous les autres voient un message d'attente en lecture seule.

Avant de décider, vous pouvez interroger l'agent sur la demande. Saisissez une question dans la discussion : elle ouvre une [consultation](./workflow-executions.md#consultations) où l'agent répond et que la personne ayant lancé l'exécution peut rejoindre. La décision la clôt.

| Décision | Signification | Ce que fait l'agent |
|---|---|---|
| **Approuver** | Allez-y | Poursuit, avec les outils des étapes couvertes débloqués |
| **Rejeter** | Ne faites pas cela | Marque la tâche `échec` ou `ignoré` |
| **Renvoyer** | Révisez et redemandez | Renvoie le travail au lieu de clore la demande |

Une décision fait reprendre l'exécution immédiatement, où qu'elle soit prise (dans la discussion ou depuis la liste des [Approbations](#browsing-approvals)), même si personne n'a ouvert la discussion de l'exécution. Une décision prise avant même l'apparition des commandes n'est pas perdue non plus : l'exécution la prend en compte dès qu'elle atteint ce point.

**Renvoyer** est une troisième décision à part entière, et non une variante de **Rejeter** : un taux de renvoi élevé signale un problème de qualité en amont, et non un travail qui n'aurait jamais dû être demandé.

Chaque décision accepte un **commentaire** facultatif. La décision elle-même est **définitive** : deux membres d'un groupe d'approbateurs peuvent réellement décider en même temps, si bien qu'une seconde décision qui changerait celle enregistrée est refusée au lieu de l'écraser. Modifier le commentaire par la suite reste permis, et cela ne change ni l'auteur enregistré de la décision ni son heure : le délai entre la demande et la décision reste donc bien celui de l'approbateur.

Seul l'approbateur désigné peut décider, **sans aucune exception, pas même pour un Super administrateur** qui n'est pas le destinataire. La même règle s'étend à l'état des tâches : changer l'état d'une tâche, à la main ou en le demandant à l'agent d'exécution, est réservé à la personne qui a lancé l'exécution et à l'approbateur d'une approbation **couvrant cette tâche**. Un approbateur peut faire avancer les étapes que couvre sa décision (la tâche nommée par l'approbation et tout ce qui suit jusqu'à la prochaine approbation), et c'est ce qui permet à une approbation de faire reprendre l'exécution. Il ne peut pas faire avancer une tâche en dehors de ce qu'on lui a demandé d'approuver, car n'importe quel approbateur de l'exécution pourrait alors se substituer au destinataire.

### Ce qu'une demande autorise {#what-a-request-authorizes}

Une demande n'est pas qu'une phrase à laquelle donner son accord. Sous **Ceci autorise**, elle liste chaque
appel qu'elle permettrait : l'outil et, pour chacune de ses entrées, les valeurs que cette entrée
peut prendre. C'est sur cette liste que porte votre décision, et c'est à elle que le serveur
contraint l'exécution par la suite.

La limite d'une entrée s'écrit de l'une de ces cinq façons :

| Affichage | Signification |
|---|---|
| `est "ap-northeast-1"` | Exactement cette valeur, et aucune autre |
| `est l'un de ["t3.micro", "t3.small"]` | N'importe laquelle des valeurs listées |
| `est au plus 2` | Un nombre qui ne dépasse pas cette valeur |
| `est au moins 8` | Un nombre qui n'est pas inférieur à cette valeur |
| `correspond à "^dev-"` | Un texte de cette forme ; ici, tout ce qui commence par `dev-` |

Une entrée marquée **facultatif** peut être omise ; toute autre entrée listée doit être fournie.
Tout ce qui **ne figure pas dans la liste est refusé** : une exécution ne peut donc pas glisser une entrée qu'on ne vous a
jamais montrée.

Lisez les limites avant de décider, et considérez qu'une limite large est une décision large : approuver
`est au plus 100` alors que le travail en demande deux, c'est accorder une autorité valant cent serveurs. Si
les limites sont plus larges que ne le justifie le travail, cliquez sur **Renvoyer** et dites-le : l'agent
peut redemander avec des limites plus étroites.

Un appel marqué **Toute entrée** est la seule exception. La conception du workflow indique que cet outil
ne fait que lire (une liste, une recherche) : la demande ne vous invite donc pas à valider les valeurs
avec lesquelles il est appelé, et l'exécution peut l'appeler avec ce dont elle a besoin. Tout le reste
est inchangé : il est couvert par votre décision et ne peut pas être appelé tant que vous ne l'avez pas
accordé. Si un outil présenté ainsi vous semble capable de modifier quelque chose, c'est une raison de
cliquer sur **Renvoyer** et de poser la question.

Veillez à lire cela dans le bon sens. Un appel listé **sans** aucune entrée en dessous
signifie le contraire : cet outil peut être appelé, mais sans lui transmettre quoi que ce soit.

Une demande qui n'autorise aucun appel d'outil n'affiche pas cette liste. Il s'agit alors d'une approbation
portant sur une action qu'A2Flow n'effectue pas lui-même, comme valider la formulation d'un
avis.

### Ce que débloque l'approbation {#what-approval-unlocks}

**Le contrôle d'approbation est appliqué par le serveur, et non par l'agent.** Une étape couverte par une approbation ne peut appeler aucun de ses [outils MCP](./mcp-servers.md) liés tant que cette approbation n'est pas accordée : l'appel est refusé avant d'atteindre le serveur. Chaque étape couverte reçoit à son démarrage un **certificat** de courte durée, et chacun de ses appels d'outil suivants doit présenter ce certificat.

Toutes les étapes ont besoin d'un tel certificat, et pas seulement celles pour lesquelles on a sollicité quelqu'un. Une étape qu'aucune approbation ne couvre en reçoit un dès qu'elle est marquée **en cours**, sous l'autorité de la personne qui a lancé l'exécution : l'enregistrement indique donc toujours au nom de qui un outil a été appelé, et aucun chemin ne mène à un outil sans attribution. Une approbation remplace simplement cette autorité par celle de l'approbateur.

Deux choses que cela apporte et qu'une consigne donnée au modèle ne pourrait pas apporter :

- **Une injection de prompt ou un bogue ne peut pas contourner l'approbation.** Le contrôle est une règle vérifiée par le serveur, et non une phrase dans les instructions de l'agent associée à une interface qui refuse de reprendre.
- **Les outils accordés sont figés.** Un certificat contient les outils liés à son étape au moment où elle a démarré, et les outils d'une étape couverte ne peuvent plus du tout être modifiés. Les étapes d'une exécution et leurs outils proviennent de la conception publiée du workflow et l'agent ne peut pas les changer : rien de ce qui survient après la décision ne peut donc élargir ce qui a été accordé. Approuver une étape pour lire un fichier ne devient pas une approbation pour en supprimer un.
- **Les arguments approuvés sont figés eux aussi.** Une demande contient également les appels qu'elle autorise, c'est-à-dire chaque outil et les limites des valeurs avec lesquelles il peut être appelé, et c'est cela que la demande vous montre avant que vous ne décidiez. Chaque appel ultérieur est vérifié par rapport à ces limites : approuver « démarrer un petit serveur à Tokyo » ne devient donc jamais une approbation pour en démarrer dix grands ailleurs. Voir [Ce qu'une demande autorise](#what-a-request-authorizes).

**Ce que couvre une décision**, c'est l'étape nommée par la demande **et toutes les étapes suivantes, jusqu'à la prochaine approbation**. Un workflow présente généralement la demande comme une étape à part entière, « Demander l'approbation » suivie de « Lancer l'instance », et une seule décision couvre les deux : l'approbateur n'est donc pas sollicité de nouveau pour chaque étape d'un même travail. Deux conséquences à connaître :

- Là où deux branches approuvées se rejoignent, l'étape de jonction a besoin des **deux** décisions avant de pouvoir agir.
- Rien de ce qui précède la demande n'est jamais couvert par elle. Une approbation ne porte que vers l'avant.

Chaque appel d'outil ayant fait l'objet d'une décision, autorisé ou refusé, est enregistré sur la page [Appels d'outils](./workflow-executions.md#tool-invocations) de l'exécution avec le certificat présenté : il est ainsi possible de répondre après coup à la question « qui a autorisé ceci, et sur quelle base ? ».

Rien de tout cela ne nécessite de configuration ; la durée de vie du certificat est réglable dans la [référence de configuration](../operations/configuration.md#mcp-tools-and-approvals).

> **Portée de la garantie.** La passerelle MCP s'exécute actuellement dans le processus du backend : un certificat prouve donc sa possession à un vérificateur qui partage ce processus, et ne protège pas contre un attaquant qui contrôle déjà le backend. Il apporte un point de contrôle unique qui bloque en cas de défaillance, une autorisation impossible à élargir après coup et un enregistrement vérifiable.

## Parcourir les approbations {#browsing-approvals}

Ouvrez **Approbations** dans la barre latérale d'administration pour parcourir toutes les demandes d'approbation. Cette vue sert à consulter : les décisions se prennent avec les commandes **Approuver** / **Rejeter** / **Renvoyer** dans la discussion.

| Colonne | Affichée par défaut |
|---|---|
| Titre, état (`en attente` / `approuvé` / `rejeté` / `renvoyé`), description, date de création | Oui |
| Exécution du workflow : un lien vers l'exécution d'origine | Oui |
| Étiquettes : en lecture seule, les étiquettes de l'exécution de workflow à laquelle elle appartient (voir [Étiquettes des exécutions de workflow et des approbations](./tags.md#execution-and-approval-tags)) | Oui |
| Décidé par : l'utilisateur ou le nom du groupe d'approbateurs, avec un lien vers sa page | Via le sélecteur de colonnes |
| Le commentaire de l'approbateur et l'heure de la décision | Via le sélecteur de colonnes |

Chaque ligne comporte aussi une action **Ouvrir la session du workflow** qui mène directement à la discussion de l'exécution, à l'image de celle de la liste des [Exécutions de workflows](./workflow-executions.md).

La page de détail d'une approbation accordée montre en outre ce qu'elle a autorisé sous **Outils MCP autorisés** : une entrée par étape couverte qui a démarré, avec les outils qui lui sont accordés, la période de validité et l'indication d'une éventuelle révocation de son certificat. Il est normal que ce panneau se remplisse progressivement : une étape reçoit son certificat à son démarrage, si bien qu'une approbation qui vient d'être accordée peut n'afficher encore rien. Une entrée dont la liste d'outils est vide n'est pas une anomalie non plus ; elle signifie que cette étape fait son travail sans appeler aucun outil MCP.

**Appels autorisés** montre la liste que l'approbateur a lue avant de décider : les appels permis par la demande et les limites de leurs entrées. Contrairement au panneau précédent, elle est remplie dès que la demande est faite, et non au fil du démarrage des étapes, et elle ne change plus jamais ensuite : c'est la trace de ce sur quoi la décision a réellement porté. Une approbation accordée avant qu'A2Flow n'enregistre ces limites affiche ici un tiret.

Le champ **Effectif à partir de** nomme l'étape à laquelle l'approbation commence à s'appliquer. Tout ce qui suit, jusqu'à la prochaine approbation, est également couvert.
