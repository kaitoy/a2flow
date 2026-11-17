---
title: Tableau de bord
sidebar_position: 16
---

# Tableau de bord

Le tableau de bord montre comment les workflows de votre tenant s'exécutent en ce moment : ce qui est en cours, ce qui attend une approbation, ce qui a échoué et combien de temps prennent les exécutions du début à la fin. Ouvrez **Tableau de bord** en haut de la barre latérale d'administration.

Il est conçu pour rester ouvert : chaque chiffre est relu toutes les 15 secondes. Il existe en deux vues, et le navigateur retient celle que vous avez choisie. La vue standard ressemble au reste de l'application et suit votre thème clair ou sombre. La vue Centre de contrôle est faite pour un écran mural : elle reste sombre quel que soit le thème du reste de l'application, ses chiffres brillent et quelque chose y bouge en permanence.

Deux sortes d'exécutions sont exclues de tous les chiffres : les exécutions de test lancées depuis un workflow encore à l'état de brouillon, et les exécutions qu'une [étiquette de contrôle d'accès](./tags.md#access-control-tags) vous masque.

Pour voir le tableau de bord rempli avant que votre tenant ait exécuté quoi que ce soit, activez les [données de démonstration](../getting-started/demo-data.md) : elles comprennent environ quatre-vingt-dix jours d'exécutions fictives.

## La barre d'outils {#the-toolbar}

| Contrôle | Ce qu'il fait |
|---|---|
| **En direct** | Le point indique que les chiffres sont à jour. Dans la vue Centre de contrôle il pulse, et l'anneau qui l'entoure se vide à mesure que la prochaine lecture approche. Il devient **Connexion perdue** lorsqu'une lecture échoue : les chiffres à l'écran sont alors les derniers lus, et le tableau de bord réessaie. |
| **7 jours** / **30 jours** / **90 jours** | Fixe la période couverte par **Délai d'exécution**, **Exécutions par workflow** et **À traiter**. Les tuiles et les autres panneaux montrent toujours le présent. |
| **Actualiser** | Relit tout immédiatement. |
| **Passer à la vue Centre de contrôle** | Passe à la vue Centre de contrôle. **Passer à la vue standard** revient à la précédente. Les deux vues montrent les mêmes chiffres. |
| **Plein écran** | Remplit l'écran avec le seul tableau de bord. Appuyez sur Échap, ou sur **Quitter le plein écran**, pour revenir. |

## Les tuiles {#the-tiles}

Chaque tuile est un nombre, une ligne d'appui et un tracé de l'évolution du nombre depuis l'ouverture de la page. Dans la vue Centre de contrôle, le nombre s'illumine brièvement à chaque changement.

| Tuile | Le nombre | La ligne en dessous | Sa couleur change |
|---|---|---|---|
| **Exécutions actives** | Exécutions en cours, y compris celles qui sont planifiées | Exécutions démarrées au cours des 24 dernières heures | Jamais |
| **Approbations en attente** | Demandes d'approbation en attente d'une décision | Approbations décidées aujourd'hui | En ambre dès que l'une attend depuis plus de 24 heures |
| **Terminées aujourd'hui** | Exécutions terminées aujourd'hui | La part terminée sans aucune tâche en échec | Jamais |
| **Exécutions en échec, 24 dernières h** | Exécutions terminées en échec au cours des 24 dernières heures | Tâches en échec sur la même période | En rouge dès qu'il dépasse zéro |
| **File d'attente des e-mails** | [E-mails de notification](./notifications.md#the-delivery-queue) pas encore envoyés | Depuis combien de temps le plus ancien attend, ou combien d'envois ont échoué | En ambre dès que le plus ancien attend depuis plus de cinq minutes, en rouge dès qu'un envoi a échoué |

« Aujourd'hui » commence à minuit dans le fuseau horaire du serveur : voir [Paramètres du serveur](../operations/configuration.md#server-settings).

## Les panneaux {#the-panels}

| Panneau | Ce qu'il montre | Comment le lire |
|---|---|---|
| **Délai d'exécution** | La durée moyenne entre le début et la fin d'une exécution, pour chaque jour où des exécutions se sont terminées. Le chiffre dans le coin est la moyenne sur toute la période. | Survolez le graphique, ou donnez-lui le focus et appuyez sur les touches fléchées, pour lire un jour. Un jour où rien ne s'est terminé n'a pas de point. |
| **Arriéré d'approbations** | Toutes les approbations en attente. L'arc ambre de l'anneau est la part qui attend depuis plus de 24 heures. En dessous figurent les cinq attentes les plus longues. | Basculez entre **Approbateur** et **Workflow** pour voir qui, ou quel workflow, les approbations attendent. Une barre devient ambre dès que l'une de ses approbations attend depuis plus de 24 heures. |
| **Exécutions par workflow** | Les huit workflows les plus actifs de la période, par exécutions démarrées. Chaque barre se divise en **terminé**, **échec** et **en cours d'exécution**. | Le chiffre en fin de ligne est son nombre d'exécutions, à côté du délai d'exécution moyen du workflow. Survolez un segment pour voir son décompte. |
| **Causes d'échec** | Les tâches en échec au cours des 24 dernières heures, selon la cause enregistrée pour chacune. | La légende nomme chaque cause présente et son décompte. |
| **À traiter** | Les exécutions comportant une tâche en échec sur la période, les plus récentes d'abord, chacune avec sa cause. Affiché uniquement pour un Administrateur. | Cliquez sur une exécution pour l'ouvrir, et faites défiler le bandeau latéralement pour voir les autres. Dans la vue Centre de contrôle, le bandeau défile tout seul et s'arrête tant que le pointeur est dessus. |

## Qui le voit {#who-sees-it}

**Tableau de bord** figure dans la barre latérale pour Administrateur, Développeur, Demandeur et Approbateur. Tout le monde voit les mêmes chiffres pour le tenant ; seul **À traiter** est réservé à un Administrateur, car il cite des noms de tâches et des causes d'échec d'exécutions auxquelles la personne qui regarde ne participe peut-être pas.

Pour tracer les mêmes chiffres dans votre propre outil de supervision, voir [Métriques d'exploitation](../operations/metrics.md).
