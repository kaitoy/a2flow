---
title: Contrôles d'intégrité
sidebar_position: 5
---

# Contrôles d'intégrité

`GET /api/v1/health` est le point de terminaison qu'un orchestrateur ou un répartiteur de charge interroge pour décider si une instance du backend doit recevoir du trafic. Il ne demande aucune authentification et renvoie un objet nu plutôt que l'enveloppe `{meta, data, error}` habituelle :

| Condition | Statut | Corps |
|---|---|---|
| La base de données a répondu à une requête élémentaire | `200` | `{"status": "ok"}` |
| Elle n'a pas répondu | `503` | `{"status": "unavailable"}` |

Le contrôle se limite à cela. Il signale un échec par un code de statut sans ambiguïté plutôt que par une page d'erreur, et il est exclu du journal d'accès : l'interroger toutes les quelques secondes ne coûte donc rien et ne laisse aucun bruit.

**Utilisez-le à la fois pour la liveness et la readiness.** Un backend qui ne peut pas atteindre sa base de données ne peut rien servir d'utile, et une nouvelle instance ne répond 200 qu'une fois son démarrage terminé, c'est-à-dire une fois ses [migrations](../architecture/database.md) appliquées. Conditionner le déploiement à ce point de terminaison évite qu'un déploiement progressif n'envoie du trafic à une instance dont les opérations sur le schéma sont encore en cours.

Docker Compose le fait déjà ([compose.yml](https://github.com/kaitoy/a2flow/blob/master/compose.yml)) :

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sf http://localhost:8000/api/v1/health || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

Accordez au contrôle un délai de grâce au démarrage, où que vous le configuriez. Le premier démarrage applique les migrations et crée les [utilisateurs initiaux](./configuration.md#seeded-users) : une instance peut donc légitimement mettre plus de temps à répondre que lors d'un redémarrage ordinaire.

Le frontend n'a pas de route de contrôle d'intégrité propre. Il ne conserve aucun état et ne dépend que du backend : une simple requête HTTP vers sa racine suffit donc comme contrôle.

Pour les chiffres d'un déploiement en fonctionnement (arriéré d'approbations, volume d'exécutions, échecs, délai d'exécution, profondeur de la file d'e-mails), consultez [Métriques d'exploitation](./metrics.md).
