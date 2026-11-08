---
title: Tenants
sidebar_position: 2
---

# Tenants

Un **tenant** est la frontière organisationnelle de plus haut niveau d'A2Flow. Presque tous les enregistrements appartiennent à exactement un tenant, quelques éléments se situent délibérément au-dessus de tous, et aucune requête ne passe jamais d'un tenant à un autre. La création et la modification des tenants eux-mêmes relèvent de l'administration et sont décrites dans [Tenants](../guides/users-and-groups.md#tenants) ; cette page explique ce que cette frontière implique pour tout le reste.

## Ce qui dépend d'un tenant {#what-a-tenant-scopes}

| Portée | Ce qui s'y trouve |
|---|---|
| **Au niveau du tenant** | Compétences d'agent, workflows et leurs sessions de conception, modèles de tâches, exécutions et leurs sessions du workflow, approbations, secrets, serveurs MCP, simulacres d'outils, étiquettes, groupes d'utilisateurs, ainsi que la plupart des utilisateurs |
| **Au niveau de la plateforme** | Les tenants eux-mêmes, les [Paramètres système](../guides/system-settings.md), les comptes Super administrateur et l'utilisateur système créé à l'initialisation |

Un [utilisateur](../guides/users-and-groups.md#users) appartient à **au plus un** tenant. Un [groupe d'utilisateurs](../guides/users-and-groups.md#user-groups) appartient à **exactement un** tenant : c'est pourquoi un groupe ne peut jamais accorder le rôle Super administrateur, qui relève par définition de la plateforme (voir [Rôles effectifs](./authorization.md#effective-roles)). Un tenant **Default** est créé au premier démarrage et contient l'utilisateur `admin` initial ; l'utilisateur `root` initial relève de la plateforme et n'a aucun tenant.

## La frontière du tenant {#the-tenant-boundary}

Toute lecture et toute écriture au niveau d'un tenant s'effectuent dans le tenant de l'appelant, et un enregistrement qui n'existe que dans un autre tenant est signalé par une erreur **HTTP 404, et non 403** : la frontière dissimule l'existence de l'enregistrement au lieu de la révéler. Cela vaut aussi bien pour un identifiant de workflow saisi dans une URL que pour un identifiant transmis à une API, et c'est pourquoi une référence vers un autre tenant ne confirme jamais que l'enregistrement existe.

La seule lecture qui ne renvoie pas d'enregistrement sans pour autant prétendre qu'il est absent est la résolution de noms en masse : `POST /api/v1/users/resolve-names` retire de sa réponse les utilisateurs extérieurs au tenant de l'appelant, de sorte que l'interface se rabat sur l'identifiant brut, mais attribue un libellé aux deux types de comptes qui possèdent légitimement des enregistrements dans chaque tenant. Voir [Résoudre les noms en masse](../guides/users-and-groups.md#users).

## Agir au nom d'un tenant {#acting-as-a-tenant}

Un Super administrateur, qui relève de la plateforme, n'a pas de tenant à lui, alors que presque tout ce qui mérite d'être consulté appartient à un tenant. Un **sélecteur de tenant** dans l'en-tête de l'application, visible uniquement par les Super administrateurs, lui permet de choisir le tenant au nom duquel il agit. Ce choix est conservé d'un rechargement à l'autre et s'applique partout, y compris dans la section d'administration et dans la discussion. Si aucun tenant n'est sélectionné, les requêtes au niveau d'un tenant sont rejetées avec une erreur HTTP 403.

Changer de tenant ne change pas les *rôles* : un Super administrateur contourne toujours tous les contrôles de rôle, quel que soit le tenant sélectionné.

Le sélecteur n'apparaît que pour un appelant qui n'a pas de tenant à lui. Un **utilisateur rattaché à un tenant reste toujours limité à son propre tenant**, et l'en-tête `X-Tenant-Id` défini par le sélecteur est entièrement ignoré pour lui : l'envoyer à la main n'accorde rien, si bien que le client ne peut pas franchir la frontière.

### Tous les tenants {#all-tenants}

Le sélecteur propose aussi l'option **Tous les tenants**, qui permet de parcourir en même temps les données de tous les tenants sur les pages de liste et de détail de l'administration, en lecture seule. Lorsqu'elle est active, ces pages ajoutent une colonne **Tenant** à l'extrême gauche (ainsi qu'un champ correspondant), pour que les lignes de tenants différents restent identifiables.

Lorsque vous agissez en tant qu'un autre utilisateur, la sélection Tous les tenants est mise de côté : les pages se comportent comme si le tenant de cet utilisateur était sélectionné, et la colonne Tenant n'apparaît pas. Elle reprend effet dès que vous arrêtez.

| Sélection | Lectures | Écritures | Historique de discussion | Points de terminaison de l'agent |
|---|---|---|---|---|
| Son propre tenant (implicite, pour tout utilisateur rattaché à un tenant) | Son propre tenant | Son propre tenant | Son propre tenant | ✅ |
| Un tenant (Super administrateur) | Ce tenant | Ce tenant | Ce tenant | ✅ |
| **Tous les tenants** (Super administrateur) | Tous les tenants | ❌ 403 | Tous les tenants | ❌ 403 |
| Aucune sélection (Super administrateur) | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 |

L'« historique de discussion » correspond à `GET /workflows/{id}/messages` et à `GET /workflow-executions/{id}/messages` : un Super administrateur qui examine le workflow ou l'exécution d'un autre tenant peut donc aussi lire la conversation correspondante. Les points de terminaison de l'agent qui *pilotent* ces discussions (`POST .../agent`) sont des écritures et exigent toujours la sélection d'un tenant précis. Avec la sélection Tous les tenants, un identifiant de workflow est résolu quel que soit le tenant : c'est alors le contrôle de rôle propre à la session de conception qui tient lieu de frontière de tenant. Voir [Session de conception](./authorization.md#design-session-access).
