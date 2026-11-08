---
title: Interface d'administration
sidebar_position: 1
---

# Interface d'administration

C'est dans l'espace d'administration que tout enregistrement d'A2Flow se crée, se consulte et se modifie. Il tient dans un cadre unique, avec une barre d'application en haut et une barre latérale de sections à gauche, et toutes ses sections fonctionnent de la même façon : une fois que vous savez utiliser une liste, vous savez utiliser les quinze.

## Page de bienvenue {#welcome-page}

La page de bienvenue est l'écran d'arrivée : vous y parvenez après vous être connecté, en ouvrant la racine du site et chaque fois que vous cliquez sur le logo **A2Flow** dans la barre d'application. Elle vous accueille avec des cartes d'action rapide, une par section d'administration autorisée par vos rôles.

![Organigramme de la navigation dans l'interface d'administration : la page de bienvenue mène à la liste d'une section, d'où l'on ouvre un formulaire de création ou, en cliquant sur un nom, une page de détail ; le fil d'Ariane de la page de détail ramène à la liste.](./img/admin-ui-navigation.svg#gh-light-mode-only)
![Organigramme de la navigation dans l'interface d'administration : la page de bienvenue mène à la liste d'une section, d'où l'on ouvre un formulaire de création ou, en cliquant sur un nom, une page de détail ; le fil d'Ariane de la page de détail ramène à la liste.](./img/admin-ui-navigation-dark.svg#gh-dark-mode-only)

Le fil d'Ariane au-dessus de chaque titre reflète ce parcours, par exemple `Accueil › Workflows › my-workflow`, et chaque élément sauf le dernier est un lien vers le niveau supérieur.

## Les sections {#the-sections}

| Section | Contenu | Affichée dans la barre latérale pour |
|---|---|---|
| **Tenants** | Les organisations de tenants | Super administrateur |
| **Utilisateurs** | Les comptes et leurs rôles | Administrateur, Développeur |
| **Groupes d'utilisateurs** | Des ensembles nommés qui accordent des rôles à plusieurs comptes à la fois | Administrateur, Développeur |
| **Étiquettes** | Les libellés qui servent à classer les enregistrements | Administrateur, Développeur |
| **Secrets** | Les identifiants des outils et des dépôts | Administrateur, Développeur |
| **Compétences d'agent** | Les capacités des agents, clonées depuis des dépôts Git | Développeur, Administrateur |
| **Bases de connaissances** | Des wikis que le LLM rédige à partir de vos documents, et que les workflows consultent | Développeur, Administrateur, Relecteur |
| **Serveurs MCP** | Les serveurs d'outils que l'agent peut appeler | Développeur, Administrateur |
| **Simulacres d'outils** | Des substituts qui simulent des outils pour les exécutions de workflows en brouillon | Développeur, Administrateur |
| **Workflows** | Les flux en plusieurs étapes et leurs modèles de tâches | Développeur, Demandeur, Administrateur |
| **Exécutions de workflows** | Les exécutions de workflows et leur historique | Toute personne connectée |
| **Approbations** | Les demandes d'approbation et leurs décisions | Toute personne connectée |
| **Journaux d'audit** | Les appels d'outils, les emprunts d'identité, l'autorité accordée et les e-mails envoyés | Administrateur, Super administrateur |
| **Paramètres du tenant** | La façon dont les échecs de connexion verrouillent les comptes de votre tenant, et le Vault propre à votre tenant : voir [Échecs de connexion](./users-and-groups.md#failed-sign-ins) et [Le Vault du tenant](./users-and-groups.md#tenant-vault) | Administrateur |
| **Paramètres système** | Le serveur de messagerie par lequel partent les notifications, et l'adresse du Vault global | Super administrateur |

Une section absente de votre barre latérale est une section dans laquelle vos rôles ne permettent pas d'écrire. La lecture reste ouverte : un collègue peut donc toujours vous envoyer un lien direct vers un enregistrement qu'elle contient. Voir [Rôles et autorisations](../concepts/authorization.md).

Les [Journaux d'audit](./audit-logs.md) font exception : leur lecture est restreinte elle aussi, et un lien direct vers eux aboutit à un écran d'accès refusé sans le rôle Administrateur. Un enregistrement portant une [étiquette de contrôle d'accès](./tags.md#access-control-tags) est l'autre exception : si vos groupes ne portent pas cette étiquette, le lien indique que l'enregistrement est introuvable.

## L'écran de liste {#the-list-screen}

Chaque section s'ouvre sur un tableau, et tous les tableaux proposent les mêmes commandes :

| Commande | Effet |
|---|---|
| **Menu de l'en-tête de colonne** | Trie et filtre selon cette colonne. Les deux s'appliquent à l'ensemble des données, et pas seulement à la page affichée. |
| **Bords de colonne** | Faites-les glisser pour redimensionner la colonne. Les largeurs durent le temps de la session et ne sont pas enregistrées. |
| **Survol d'une cellule** | Affiche le texte complet de tout contenu tronqué par la largeur de la colonne. |
| **▥ Colonnes** | Ouvre le sélecteur de colonnes (voir ci-dessous). |
| **Actualiser** | Relit la liste. |
| **+ Ajouter …** | Ouvre le formulaire de création. Masqué sans le rôle d'écriture. |
| **Colonne Actions** | Les actions propres à chaque ligne : Supprimer, et tout ce que propose par ailleurs le type d'enregistrement. Masquée sans le rôle d'écriture. |

Une colonne dont les valeurs appartiennent à un ensemble fixe (l'état d'une tâche, le transport d'un serveur MCP, la couleur d'une étiquette) se trie dans l'ordre où ces valeurs sont censées se lire, et non par ordre alphabétique. Trier les tâches par état donne donc `en attente`, `en cours`, `terminé`, `échec`, `ignoré`, le même ordre de cycle de vie que celui des pastilles d'état partout ailleurs.

### Choisir les colonnes {#choosing-columns}

Le bouton **▥**, à côté d'**Actualiser**, liste toutes les colonnes que le tableau peut afficher :

- **Tout afficher** / **Tout masquer** bascule l'ensemble ; **Rétablir les valeurs par défaut** revient à la sélection d'origine.
- Certaines colonnes sont masquées au départ pour laisser la largeur à celles qui comptent : le transport d'un serveur MCP, la référence d'un secret, la référence et la révision d'une compétence d'agent, l'e-mail et l'indicateur de vérification d'un utilisateur.
- La colonne d'identifiant et la colonne Actions sont toujours affichées ; elles ne figurent donc pas dans la liste.
- Vos choix sont mémorisés par tableau dans le navigateur et résistent à un rechargement de la page. Seuls vos écarts par rapport au réglage par défaut sont conservés : une colonne ajoutée plus tard à un tableau arrive donc bien avec l'état par défaut prévu pour elle.
- Masquer une colonne utilisée par un tri ou un filtre annule ce tri ou ce filtre : les lignes affichées ne sont ainsi jamais restreintes par un critère que rien à l'écran ne permettrait de voir.

Le panneau tient toujours dans l'écran : il s'ouvre vers le haut quand la place manque en dessous, fait défiler sa liste en interne tout en gardant visibles les boutons de bascule globaux, et se répartit sur deux colonnes dès qu'un tableau compte plus de huit colonnes masquables. Même les Compétences d'agent, avec leurs dix-sept colonnes, restent ainsi accessibles sur le petit écran d'un ordinateur portable.

## L'écran de détail {#the-detail-screen}

Cliquer sur le nom d'un enregistrement dans la colonne d'identifiant ouvre sa page de détail. Cette page est l'unique écran de l'enregistrement : elle réunit ses attributs et toutes les actions qu'il permet, à savoir enregistrer les modifications, le supprimer, et tout ce que propose par ailleurs son type, comme publier un workflow ou récupérer le dépôt d'une compétence. Elle a pour titre le **nom de l'enregistrement** plutôt que celui de l'opération.

Sans le rôle d'écriture, la même page s'affiche en lecture seule : les champs apparaissent comme des valeurs en retrait au lieu de zones de saisie, **Enregistrer** et **Supprimer** disparaissent, et **Annuler** devient **Retour**.

Les [exécutions de workflows](./workflow-executions.md) échappent à tout cela. Une exécution est un historique et non un enregistrement à modifier : sa ligne ouvre donc la discussion de l'exécution ou sa liste de tâches en lecture seule, plutôt qu'un formulaire de modification.
