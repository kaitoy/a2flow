---
title: Métriques d'exploitation
sidebar_position: 6
---

# Métriques d'exploitation

Les données d'exploitation des workflows (arriéré d'approbations, volume d'exécutions, échecs et délai d'exécution) sont exposées aux tableaux de bord tiers sous deux formes, toutes deux limitées au tenant de l'appelant et, à l'exception de la liste des échecs signalée plus bas, accessibles à tout utilisateur authentifié.

Les exécutions qu'une [étiquette de contrôle d'accès](../guides/tags.md#access-control-tags) masque à l'appelant sont exclues de toutes les vues ci-dessous, exactement comme elles sont absentes de la liste des exécutions : une métrique ne nomme donc jamais une exécution que son lecteur ne pourrait pas ouvrir.

Les exécutions lancées depuis un workflow encore à l'état `brouillon` (une [exécution de test avant publication](../guides/workflows.md#running-a-workflow) par un développeur ou un super administrateur) sont enregistrées avec `isDraft: true` et **exclues de toutes les métriques ci-dessous**, aussi bien des KPI Prometheus que des sous-ressources agrégées, vues de l'arriéré d'approbations comprises, afin que des données de test jetables ne faussent jamais les chiffres. L'indicateur est fixé au démarrage de l'exécution : publier le workflow par la suite ne reclasse pas les exécutions déjà passées.

## Point de terminaison Prometheus {#prometheus-endpoint}

`GET /api/v1/metrics` restitue les KPI à valeur unique au format d'exposition texte de [Prometheus](https://prometheus.io/). Chaque échantillon porte une étiquette `tenant`.

Approbations :

| Métrique | Signification |
|---|---|
| `a2flow_approvals_pending` | Demandes d'approbation en attente d'une décision |
| `a2flow_approvals_pending_over_threshold{threshold}` | Parmi celles-ci, celles qui attendent depuis plus longtemps que le seuil (24 h par défaut) |
| `a2flow_approval_pending_age_seconds_max` | Durée d'attente de la demande la plus ancienne |
| `a2flow_approvals_decided_today{decision}` | Approbations décidées aujourd'hui, par `approved` / `rejected` / `returned` |

Exécutions :

| Métrique | Signification |
|---|---|
| `a2flow_workflow_executions_active` | Exécutions actuellement en cours (`running` ou `scheduled`) |
| `a2flow_workflow_executions_finished_today{status}` | Exécutions terminées aujourd'hui, par état final |
| `a2flow_workflow_executions_started_recently{window,workflow}` | Exécutions lancées au cours des dernières 24 h, par workflow |
| `a2flow_workflow_executions_failed_recently{window}` | Exécutions terminées en échec au cours des dernières 24 h |
| `a2flow_workflow_tasks_failed_recently{window,error_kind}` | Tâches ayant échoué au cours des dernières 24 h, par cause |
| `a2flow_workflow_execution_lead_time_seconds_avg{window,workflow}` | Durée moyenne, du début à la fin, des exécutions terminées au cours des dernières 24 h |

E-mails de notification :

| Métrique | Signification |
|---|---|
| `a2flow_email_queue_depth{status}` | E-mails présents dans la [file d'envoi](../guides/notifications.md#the-delivery-queue), par `pending` / `sending` / `sent` / `failed` |
| `a2flow_email_queue_oldest_pending_age_seconds` | Durée d'attente de l'e-mail non remis le plus ancien ; elle augmente lorsque le relais est injoignable |

`?thresholdHours=` remplace le seuil des approbations bloquées. `TIMEZONE` (un nom IANA, `UTC` par défaut ; consultez [Paramètres du serveur](./configuration.md#server-settings)) détermine où commence « aujourd'hui » ; un nom non reconnu se rabat sur UTC au lieu de faire échouer le démarrage.

Le point de terminaison est protégé par le cookie de session ordinaire : une configuration de collecte doit donc en fournir un. `GET` étant une méthode sûre, aucun jeton CSRF n'est nécessaire :

```yaml
- job_name: a2flow
  metrics_path: /api/v1/metrics
  http_headers:
    Cookie: { values: ["a2flow_session=<token>"] }
```

Le délai d'inactivité de la session glisse à chaque requête : une collecte en cours maintient donc sa propre session active indéfiniment. Celle-ci ne survit ni à un redémarrage du backend ni à une déconnexion explicite, et c'est alors qu'il faut renouveler le jeton. Une collecte couvre exactement un tenant : pour en surveiller plusieurs, configurez un job par tenant.

## Sous-ressources agrégées {#aggregate-sub-resources}

Tout ce dont la clé naturelle est un identifiant d'utilisateur, un identifiant d'exécution ou un message d'erreur en texte libre est volontairement tenu à l'écart de Prometheus, car ces ensembles d'étiquettes sont illimités. Ces vues sont plutôt servies sous forme de sous-ressources JSON des collections existantes, dans l'enveloppe `{meta, data, error}` habituelle :

| Point de terminaison | Renvoie |
|---|---|
| `GET /api/v1/workflow-executions/by-workflow` | Nombre d'exécutions par workflow (`total` / `running` / `completed` / `failed` ; `running` inclut les exécutions `scheduled`) et délai d'exécution moyen |
| `GET /api/v1/workflow-executions/lead-time-trend` | Délai d'exécution moyen quotidien, avec une tranche par jour calendaire, y compris les jours vides |
| `GET /api/v1/workflow-executions/failures` | Exécutions à examiner, chacune avec ses tâches en échec et leur cause enregistrée. Réservé aux administrateurs, car il cite les titres de tâches et les messages d'erreur d'exécutions auxquelles l'appelant ne participe pas forcément |
| `GET /api/v1/approvals/by-approver` | Arriéré d'approbations en attente par approbateur désigné |
| `GET /api/v1/approvals/by-workflow` | Le même arriéré, regroupé par workflow |

Les points de terminaison des exécutions acceptent `since` / `until` (ISO-8601, par défaut les 30 derniers jours, 366 au maximum) et `limit` ; ceux des approbations acceptent `thresholdHours` (24 par défaut) et `limit`. Les entrées de l'arriéré sont renvoyées par attente individuelle décroissante : `?limit=5` donne donc les cinq pires. Les durées sont toujours exprimées en secondes entières.

`by-approver` regroupe selon la **destination** d'une approbation, qui peut être un utilisateur ou un groupe. Chaque entrée porte un `groupKind` valant `"user"` ou `"group"` pour les distinguer : une entrée `"user"` ne donne que l'identifiant, tandis qu'une entrée `"group"` indique aussi le nom du groupe dans `groupLabel`.

Une tâche en échec enregistre **pourquoi** : `error_kind` (parmi `api_error`, `timeout`, `script_error`, `invalid_input`, `permission_denied`, `rejected`, `other`) et un `error_message` en texte libre sont stockés avec `status="failed"`. Ce sont des champs ordinaires de la tâche : une liste de tâches peut donc être filtrée sur eux, p. ex. `?q=errorKind:eq:timeout`.
