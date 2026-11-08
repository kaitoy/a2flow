---
title: Rôles et autorisations
sidebar_position: 3
---

# Rôles et autorisations

Chaque utilisateur possède un ensemble de **rôles** qui déterminent les opérations qu'il peut effectuer. Les rôles sont **indépendants** : il n'existe aucune hiérarchie, à une exception près. **Le Super administrateur contourne tous les contrôles fondés sur les rôles** et, pour cette raison, ce rôle est **mutuellement exclusif** avec tous les autres : un utilisateur est soit Super administrateur, soit titulaire d'une combinaison des cinq autres rôles, jamais les deux. Deux contrôles liés à la propriété font délibérément exception à ce contournement, et tous deux apparaissent dans la [matrice d'accès aux sessions](./authorization.md#workflow-execution-access) ci-dessous. Un utilisateur **sans aucun rôle** est valide : il peut toujours gérer son propre [compte](../guides/users-and-groups.md#users) (avatar et langue), mais rien d'autre.

## Rôles effectifs {#effective-roles}

Un rôle parvient à un utilisateur de deux façons, et chaque contrôle d'autorisation utilise l'**union** des deux, c'est-à-dire les **rôles effectifs** de l'utilisateur :

- **Directement**, accordé sur l'enregistrement de l'utilisateur depuis la page [Utilisateurs](../guides/users-and-groups.md#users).
- **Par héritage**, depuis un [groupe d'utilisateurs](../guides/users-and-groups.md#user-groups) auquel il appartient : attribuer un rôle à un groupe l'accorde à tous ses membres.

![Organigramme montrant que les rôles accordés directement sur l'enregistrement de l'utilisateur et les rôles hérités des groupes d'utilisateurs alimentent ensemble les rôles effectifs de l'utilisateur, l'union utilisée par chaque contrôle d'autorisation.](./img/authorization-effective-roles.svg#gh-light-mode-only)
![Organigramme montrant que les rôles accordés directement sur l'enregistrement de l'utilisateur et les rôles hérités des groupes d'utilisateurs alimentent ensemble les rôles effectifs de l'utilisateur, l'union utilisée par chaque contrôle d'autorisation.](./img/authorization-effective-roles-dark.svg#gh-dark-mode-only)

Un rôle détenu uniquement par l'intermédiaire d'un groupe vaut exactement un rôle accordé directement : il franchit les mêmes contrôles, rend l'utilisateur éligible comme approbateur et le protège de la même façon contre l'[emprunt d'identité](./impersonation.md). Rien n'est mis en cache, l'union étant calculée à chaque requête : ajouter une personne à un groupe, ou l'en retirer, prend donc effet immédiatement, sans étape de resynchronisation.

Un groupe peut aussi être désigné en tant que tel : une [approbation](../guides/approvals.md#human-approval) peut être adressée à un groupe plutôt qu'à une personne, et tout membre possédant le rôle Approbateur peut alors statuer.

**Un groupe ne peut jamais accorder le rôle Super administrateur** : l'option n'est pas proposée dans l'interface, l'API la rejette (HTTP 422), et une contrainte de vérification en base de données vient renforcer le tout. Comme un Super administrateur relève de la plateforme et qu'un groupe appartient à exactement un [tenant](./tenants.md), un Super administrateur ne peut jamais non plus être membre d'un groupe.

## Les rôles {#the-roles}

| Rôle | Accorde |
|---|---|
| Super administrateur | Tout (contourne tous les contrôles de rôle ; ne contourne **pas** les deux contrôles propres à l'approbateur désigné dans la [matrice ci-dessous](./authorization.md#workflow-execution-access)) |
| Administrateur | CRUD des utilisateurs, CRUD des secrets, suppression des exécutions, et accès en lecture seule à toutes les exécutions, à leurs tâches et à leur historique de discussion, ainsi qu'à toutes les approbations, au sein de son tenant (voir [L'exécution et sa session du workflow](./authorization.md#workflow-execution-access) ; hormis la suppression, un Administrateur ne peut ni piloter l'agent d'une exécution, ni changer l'état de l'une de ses tâches, ni statuer sur une approbation) |
| Développeur | CRUD des secrets, CRUD des serveurs MCP, CRUD des [simulacres d'outils](../guides/tool-mocks.md), CRUD des compétences d'agent, génération et modification des workflows (y compris la régénération du **Prompt généré** par l'IA d'un workflow, bien que seul un Super administrateur puisse modifier ce champ directement), CRUD des modèles de tâches, pilotage de la discussion de la session de conception, et exécution des workflows (`POST /workflows/{id}/execute`), y compris les workflows à l'état `brouillon` et les modifications non publiées d'un workflow à l'état `modifié`, pour les tester avant publication. La publication et la désactivation **n'en font pas partie** : elles reviennent au rôle Relecteur |
| Relecteur | Publication et désactivation d'un workflow, les deux opérations que le rôle Développeur n'effectue plus. Partage la visibilité complète du Développeur sur un workflow : un workflow à l'état `brouillon`, les modifications non publiées d'un workflow à l'état `modifié` et l'historique de discussion de la session de conception se lisent de la même façon pour un Relecteur que pour un Développeur. Ne peut ni modifier un workflow ou ses modèles de tâches, ni piloter sa session de conception |
| Demandeur | Exécution des workflows **publiés** (et à l'état `modifié`) (`POST /workflows/{id}/execute`), toujours d'après la dernière conception publiée |
| Approbateur | Possibilité d'être l'approbateur désigné d'une approbation de workflow, individuellement ou comme membre d'un groupe auquel une approbation est adressée, et de statuer sur ses propres approbations |

L'utilisateur **`root`** créé à l'initialisation possède le rôle Super administrateur et relève de la plateforme (aucun tenant). L'utilisateur **`admin`** créé dans le tenant **Default** possède le rôle Administrateur, limité à ce tenant ; tout autre utilisateur démarre sans aucun rôle.

## Ce que contrôlent les rôles {#what-roles-gate}

**Les lectures restent ouvertes.** Seuls les écritures, l'exécution des workflows et les approbations sont soumis à un contrôle de rôle ; tout utilisateur authentifié peut lire les collections par `GET` (l'interface en a besoin pour résoudre les noms, choisir les approbateurs et lister les workflows). Les *valeurs* des secrets ne sont jamais renvoyées par l'API, quel que soit le rôle.

Le **Prompt** et le **Prompt généré** d'un workflow, c'est-à-dire le texte transmis à une exécution, ne sont visibles que par un Administrateur, un Développeur, un Relecteur ou un Super administrateur. Toute autre personne lit le workflow et ses exécutions avec ces champs vides. L'[historique des versions](../guides/workflows.md#version-history) du workflow est réservé aux mêmes rôles ; un Demandeur ou un Approbateur ne peut pas l'ouvrir. La **Description** du workflow reste visible par toute personne qui peut l'ouvrir.

La seule exception n'est pas un rôle : un enregistrement portant une [étiquette de contrôle d'accès](../guides/tags.md#access-control-tags) n'est visible que par les utilisateurs dont les groupes portent, à eux tous, chacune de ces étiquettes présentes sur l'enregistrement, ainsi que par les Administrateurs et les Super administrateurs, qui contournent tous deux cette règle. Pour tous les autres, ni l'enregistrement ni aucun indice de son existence ne sont visibles.

Les rôles s'attribuent depuis la page d'administration [Utilisateurs](../guides/users-and-groups.md#users), ou en bloc depuis la page [Groupes d'utilisateurs](../guides/users-and-groups.md#user-groups) ; seul un Super administrateur peut accorder ou retirer le rôle Super administrateur. Une requête rejetée renvoie une erreur HTTP 403 (`FORBIDDEN`).

### Ce que masque l'interface {#what-the-ui-hides}

L'interface d'administration masque les actions et les entrées de navigation que les rôles d'un utilisateur n'autorisent pas : une requête rejetée est donc normalement inaccessible plutôt que simplement refusée.

| Écran | Sans le rôle |
|---|---|
| **Page de liste** | Le bouton d'ajout et la colonne Actions par ligne sont masqués : Supprimer, et pour les serveurs MCP « Parcourir le registre », qui ne mène qu'au formulaire de création |
| **Page de détail** | S'affiche en **lecture seule** : chaque champ apparaît sous forme de valeur en retrait au lieu d'une zone de saisie, Enregistrer et Supprimer sont absents, et Annuler devient Retour |
| **Formulaire de création** (`/<section>/new`) | Un écran d'accès refusé : y parvenir suppose un lien direct, puisque le bouton d'ajout qui y mène est déjà masqué |

Les lectures restant ouvertes, une page de détail peut être ouverte par quelqu'un qui n'a pas le droit de la modifier : les compétences d'agent, les serveurs MCP, les simulacres d'outils, les secrets, les tenants, les utilisateurs, les workflows et les modèles de tâches adoptent tous l'affichage en lecture seule décrit ci-dessus. Les entrées d'un secret ne listent alors que leurs clés (les valeurs ne sont de toute façon jamais renvoyées), et le champ de mot de passe d'un utilisateur est entièrement omis. Les champs immuables pour *tout le monde*, comme le `name` d'un tenant ou le `username` d'un utilisateur, s'affichent de la même façon quel que soit le rôle. Les formulaires de création n'ont pas de version en lecture seule : c'est pourquoi ils répondent par un écran plutôt que par un formulaire.

## Accès aux sessions {#session-access}

A2Flow propose deux types de discussion, soumis à deux contrôles différents :

- Une **session de conception** est la discussion dans laquelle un workflow est conçu. L'accès dépend du **rôle** : la conception étant un travail de développeur, les Développeurs du tenant la partagent et peuvent la piloter ; les Relecteurs peuvent aussi la lire, pour examiner la conception avant publication, mais pas la piloter.
- Une **session du workflow** est la discussion dans laquelle se déroule une exécution. L'accès dépend de la **participation** : la personne qui a lancé l'exécution et celles à qui l'on demande d'y approuver quelque chose la partagent, quels que soient leurs rôles.

![Matrice d'accès montrant que les Développeurs, le créateur du workflow et le Super administrateur accèdent à une session de conception, les Relecteurs y ayant un accès en lecture seule, tandis que l'initiateur de l'exécution, ses approbateurs désignés et le Super administrateur accèdent à une session du workflow, l'Administrateur y ayant un accès en lecture seule.](./img/authorization-session-matrix.svg#gh-light-mode-only)
![Matrice d'accès montrant que les Développeurs, le créateur du workflow et le Super administrateur accèdent à une session de conception, les Relecteurs y ayant un accès en lecture seule, tandis que l'initiateur de l'exécution, ses approbateurs désignés et le Super administrateur accèdent à une session du workflow, l'Administrateur y ayant un accès en lecture seule.](./img/authorization-session-matrix-dark.svg#gh-dark-mode-only)

### Session de conception {#design-session-access}

La discussion de conception d'un workflow (`GET /workflows/{id}/messages`, `POST /workflows/{id}/agent`) est partagée selon les rôles et non selon une participation propre à chaque enregistrement, afin qu'une équipe puisse affiner une conception ensemble.

| Qui | Lire l'historique | Piloter l'agent |
|---|---|---|
| Tout **Développeur** du tenant | ✅ | ✅ |
| Tout **Relecteur** du tenant | ✅ | ❌ 403 |
| Le **créateur** du workflow (`createdBy`), même après avoir perdu le rôle Développeur | ✅ | ✅ |
| **Super administrateur** | ✅ | ✅ |
| Toute autre personne | ❌ 403 | ❌ 403 |

Admettre explicitement le créateur garantit que personne n'est exclu d'une discussion qu'il a lui-même lancée. L'identifiant de workflow d'un autre tenant renvoie une erreur **404**, jamais 403, sauf pour `GET .../messages` avec la sélection [Tous les tenants](./tenants.md#all-tenants) d'un Super administrateur : le workflow est alors résolu quel que soit le tenant, et c'est ce même contrôle (rôle, créateur, Super administrateur) qui tient lieu de frontière de tenant.

### L'exécution et sa session du workflow {#workflow-execution-access}

Au-delà des rôles, chaque opération sur une exécution exige que l'appelant soit l'**initiateur** de l'exécution (l'utilisateur qui a lancé le workflow) ou un **approbateur désigné de l'une de ses approbations**, c'est-à-dire l'utilisateur nommé ou un membre possédant le rôle Approbateur d'un groupe auquel l'une d'elles est adressée (voir [Approbation humaine](../guides/approvals.md#human-approval)). Cela préserve le partage prévu avec l'approbateur, qui rejoint la discussion de l'initiateur, tout en tenant les tiers à l'écart. La lecture est plus large, et les opérations d'action sont plus restreintes :

| Opération | Point de terminaison | Initiateur | Approbateur désigné | Administrateur (même tenant) | Super administrateur |
|---|---|---|---|---|---|
| Lire l'exécution | `GET /workflow-executions/{id}` | ✅ | ✅ | ✅ | ✅ |
| Lister ou ouvrir ses tâches | `GET .../workflow-tasks` | ✅ | ✅ | ✅ | ✅ |
| Lire l'historique de la session du workflow | `GET .../messages` | ✅ | ✅ | ✅ | ✅ |
| Piloter son agent | `POST .../agent` | ✅ | ✅ | ❌ | ✅ |
| Changer l'**état** d'une tâche (à la main ou par l'agent) | `PATCH /workflow-tasks/{id}` | ✅ | Uniquement pour une tâche couverte par une approbation qui lui est adressée | ❌ | Uniquement pour une tâche qu'aucune approbation ne couvre |
| Statuer sur une approbation | `PATCH /approvals/{id}` | ❌ | Uniquement l'approbateur de cette approbation | ❌ | ❌ |
| Supprimer l'exécution | `DELETE /workflow-executions/{id}` | Uniquement s'il est Administrateur | Uniquement s'il est Administrateur | ✅ | ✅ |

Toute personne extérieure à ces colonnes reçoit une erreur HTTP 403. La même liste `GET /approvals` montre à un Administrateur toutes les approbations du tenant, conformément à la ligne de lecture ci-dessus.

La **liste des tâches d'une exécution est fixée au lancement du workflow** : les tâches sont copiées depuis les modèles publiés du workflow, et seul leur `status` (ainsi que la cause d'un échec) change ensuite. Personne ne peut, par l'API, ajouter, retirer, renommer, redécrire ou relier autrement les tâches d'une exécution ; pour changer les étapes, modifiez les [modèles de tâches](../guides/workflows.md#adjusting-the-task-templates) et relancez l'exécution.

**Les trois dernières lignes méritent une seconde lecture.**

Les lignes sur l'état et sur la décision sont les **exceptions liées à la propriété au contournement du Super administrateur**, annoncées en haut de cette page : seul l'approbateur désigné peut statuer sur une approbation, et l'état d'une tâche ne peut être changé que par l'initiateur ou par un approbateur destinataire d'une approbation **couvrant cette tâche**. N'importe quel approbateur de l'exécution ne suffit donc pas et, dès qu'une approbation couvre la tâche, ni un Super administrateur ni un Administrateur ne le peuvent. Un approbateur ne peut faire avancer une tâche que dans les limites de ce qu'on lui a demandé d'approuver, à savoir la tâche nommée par l'approbation et les étapes suivantes jusqu'à la prochaine approbation : une décision peut ainsi relancer l'exécution sans qu'un approbateur puisse faire avancer des étapes sans rapport. Sinon, faire passer directement une tâche à `terminé` permettrait à n'importe qui de se substituer au destinataire (voir [Approbation humaine](../guides/approvals.md#human-approval)). La règle est la même, que le changement soit effectué à la main ou demandé à l'agent d'exécution dans la discussion de la session du workflow : l'agent refuse un changement d'état que la personne qui le pilote ne pourrait pas effectuer directement.

La **suppression** d'une exécution suit la logique inverse : il s'agit d'un simple contrôle de rôle, sans aucune composante de propriété. Un Administrateur peut donc supprimer n'importe quelle exécution du tenant, alors qu'un initiateur qui n'est pas Administrateur ne peut pas supprimer la sienne. La suppression retire aussi les tâches de l'exécution et sa session du workflow.

## Sections à l'échelle de la plateforme {#platform-wide-sections}

[Tenants](../guides/users-and-groups.md#tenants) et [Paramètres système](../guides/system-settings.md) sont les deux sections d'administration que le **Super administrateur** se réserve. Contrairement au reste de l'application, les lectures y sont également contrôlées : ces sections contiennent une configuration de niveau plateforme et non des données de tenant, si bien que l'entrée de la barre latérale, la carte de la page de bienvenue et tous les points de terminaison associés sont fermés à tous les autres rôles.

## L'éligibilité des approbateurs dans le temps {#approver-eligibility}

⚠️ L'éligibilité d'un approbateur est validée à la création de l'approbation : `list_users` / `list_user_groups` ne proposent que des destinataires réellement capables d'approuver, et `request_approval` rejette tout le reste (y compris un groupe sans membre éligible). Ce qui se passe *ensuite* dépend du destinataire, et cette différence est délibérée :

- **Destinataire utilisateur** : retirer ultérieurement le rôle Approbateur n'invalide **pas** les approbations déjà adressées à cet utilisateur. Il peut toujours statuer dessus, de sorte qu'un workflow en cours ne reste jamais bloqué.
- **Destinataire groupe** : l'appartenance et le rôle sont revérifiés au moment de la décision, car « le groupe » est un ensemble mouvant et non une personne fixe. C'est ce qui permet à un nouveau membre de prendre en charge une demande en attente, mais cela vaut dans les deux sens : retirer au groupe le rôle Approbateur, ou le vider de ses membres éligibles, laisse la demande en attente **sans personne pour y statuer** et son exécution en attente indéfiniment. Accorder de nouveau le rôle ou ajouter de nouveau un membre la débloque immédiatement.
