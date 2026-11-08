---
title: Emprunt d'identité
sidebar_position: 4
---

# Emprunt d'identité

L'emprunt d'identité permet à un utilisateur privilégié d'**agir en tant qu'un autre utilisateur**, pour reproduire ce que cette personne voit ou pour effectuer une opération à sa place. Toute requête émise pendant un emprunt d'identité est attribuée à l'utilisateur concerné, et chaque session d'emprunt d'identité est enregistrée. Pour en démarrer une, il faut le rôle Administrateur (ou Super administrateur).

## Qui peut agir en tant que qui {#who-can-impersonate-whom}

| Auteur ＼ Cible | Possède le rôle Super administrateur | Possède le rôle Administrateur | Tout autre utilisateur |
|---|---|---|---|
| **Super administrateur** | ❌ | ✅ sur toute la plateforme | ✅ sur toute la plateforme |
| **Administrateur** | ❌ | ❌ | ✅ dans son propre tenant uniquement |
| Tout autre rôle | ❌ | ❌ | ❌ : l'action n'est même pas proposée |

L'essentiel tient à la forme de ce tableau : un emprunt d'identité ne peut jamais servir à obtenir un privilège que son auteur ne possède pas déjà. Un Administrateur ordinaire ne peut pas agir en tant qu'un autre Administrateur, et un Super administrateur n'aurait rien à y gagner, puisqu'il contourne déjà tous les contrôles qu'un Administrateur franchirait.

La **cible** est évaluée d'après ses [rôles effectifs](./authorization.md#effective-roles) : un rôle Administrateur hérité d'un [groupe d'utilisateurs](../guides/users-and-groups.md#user-groups) protège donc son titulaire exactement comme un rôle accordé directement. Sinon, le groupe permettrait de contourner le tableau ci-dessus.

Quatre autres cibles sont refusées quels que soient les rôles : **vous-même**, l'**utilisateur système** créé à l'initialisation, un utilisateur **désactivé** et un utilisateur **supprimé de façon logique**. Enfin, pour un Administrateur, une cible située dans un autre [tenant](./tenants.md) renvoie une erreur **HTTP 404, et non 403** : une référence vers un autre tenant ne confirme jamais que l'utilisateur existe.

## Démarrer et arrêter {#starting-and-stopping}

Lancez l'opération avec l'action **Agir en tant que** de la liste [Utilisateurs](../guides/users-and-groups.md#users) ; après confirmation, vous arrivez sur la page de bienvenue en tant que cet utilisateur. Pendant toute la durée de l'emprunt, une pastille dans l'en-tête affiche « Vous agissez en tant que `<user>` » avec un bouton **Cesser d'agir en tant que cet utilisateur**.

Un seul emprunt d'identité peut être ouvert à la fois : en démarrer un nouveau ferme celui qui était ouvert. L'arrêt peut toujours être demandé sans risque, même si aucun emprunt n'est ouvert.

## L'identité effective {#effective-identity}

L'emprunt d'identité est une **substitution par en-tête de requête, et non un changement de session**. Le véritable cookie de session ne change jamais : le navigateur joint simplement l'identifiant de l'utilisateur sélectionné à chaque requête, et le backend en déduit l'identité effective. Il en découle deux conséquences :

- La session du véritable auteur reste active en arrière-plan : arrêter l'emprunt n'oblige donc jamais à se reconnecter.
- Tout ce que touche une requête (lectures, écritures et champs d'audit `createdBy` / `updatedBy`) est attribué à l'utilisateur dont l'identité est empruntée, exactement comme s'il était lui-même connecté. **Les contrôles de rôle portent eux aussi sur les rôles effectifs de cet utilisateur** : un Super administrateur qui agit en tant que Demandeur est soumis aux mêmes contrôles qu'un Demandeur et voit la même interface que lui.

Les points de terminaison de démarrage et d'arrêt constituent l'exception délibérée : ils sont contrôlés d'après les rôles du **véritable** auteur et non d'après ceux de l'identité effective. Sinon, un administrateur agissant en tant qu'un utilisateur volontairement sans privilèges échouerait au contrôle de rôle de son propre appel d'arrêt et resterait bloqué.

## Lorsqu'un emprunt d'identité n'est plus valide {#stale-impersonations}

L'éligibilité est revérifiée à **chaque** requête, et pas seulement au démarrage de l'emprunt : le tableau ci-dessus dépend des rôles, et les rôles évoluent. Si l'emprunt n'est plus valable, la requête n'échoue pas : elle revient silencieusement au véritable auteur et ferme l'enregistrement devenu caduc. Cela couvre les cas suivants : la cible a été désactivée ou supprimée, la cible a été promue (y compris par son ajout à un groupe qui accorde le rôle Administrateur), l'auteur a perdu le rôle Administrateur (directement ou en quittant un groupe qui l'accorde) ou Super administrateur, l'auteur ne partage plus le tenant de la cible, ou l'emprunt a été arrêté ailleurs.

Faire échouer la requête serait pire qu'inutile : la sélection étant conservée dans le stockage local du navigateur, une erreur permettrait à une seule valeur périmée de priver un administrateur légitime de toute l'application.

## Piste d'audit {#audit-trail}

Chaque session d'emprunt d'identité est consignée dans une piste d'audit persistante (qui, en tant que qui, et quand), dans la table `impersonation_events` (voir la [référence de configuration](../operations/configuration.md)). Comme c'est l'utilisateur dont l'identité est empruntée qui figure dans `createdBy` / `updatedBy`, cette piste est le seul moyen de répondre à la question « qui se cachait réellement derrière cette écriture ? », et c'est précisément pour cela qu'elle n'est pas facultative.

Un Administrateur consulte cette piste dans l'onglet **Emprunts d'identité** des [Journaux d'audit](../guides/audit-logs.md#impersonations), qui liste toutes les sessions ayant touché les comptes de son tenant, y compris celles ouvertes par un Super administrateur.
