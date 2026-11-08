---
title: Sauvegarde et restauration
sidebar_position: 4
---

# Sauvegarde et restauration

[Trois éléments](./deployment.md#state-that-has-to-persist) doivent survivre à la perte d'un conteneur. Tout le reste (serveurs MCP enregistrés, workflows, utilisateurs, paramètres système) est stocké sous forme de lignes dans la base de données et se trouve donc couvert par sa sauvegarde.

| Élément | Sauvegarde | Restauration |
|---|---|---|
| Base de données | `pg_dump`, ou une copie du fichier SQLite | `pg_restore`, ou remise en place du fichier |
| Magasin de compétences d'agent | Une copie de l'arborescence `SKILLS_DIR` | Extraction à son emplacement d'origine |
| Clé de chiffrement des secrets | La valeur de `SECRET_ENCRYPTION_KEY`, ou le fichier indiqué par `SECRET_KEY_FILE` | Définition de la même valeur, ou remise en place du même fichier |

**Restaurez toujours ensemble la base de données et la clé.** La clé déchiffre les secrets locaux *et* la clé de signature de la CA d'approbation, tous deux stockés dans la base de données. Une base de données restaurée avec une autre clé démarre avec des secrets entièrement illisibles.

## La base de données {#the-database}

Avec PostgreSQL :

```bash
pg_dump --format=custom --file=a2flow-$(date +%F).dump "postgresql://user:password@host:5432/a2flow"
pg_restore --clean --if-exists --dbname="postgresql://user:password@host:5432/a2flow" a2flow-2026-01-31.dump
```

Avec Docker Compose, adressez-vous directement au service `db` :

```bash
docker compose exec -T db pg_dump -U a2flow -Fc a2flow > a2flow-$(date +%F).dump
docker compose exec -T db pg_restore -U a2flow -d a2flow --clean --if-exists < a2flow-2026-01-31.dump
```

Une base SQLite tient en un seul fichier, situé au chemin indiqué par `DB_URL`. Utilisez `sqlite3 a2flow.db ".backup out.db"` plutôt que de le copier pendant que l'application tourne.

Une base de données restaurée ne nécessite aucune étape de migration distincte : le backend applique au démarrage les migrations [Alembic](https://alembic.sqlalchemy.org/) en attente. Il suffit donc de restaurer une ancienne sauvegarde sous une version plus récente et de démarrer celle-ci pour mettre le schéma à niveau.

## Le magasin de compétences d'agent {#the-agent-skill-store}

Réenregistrer les compétences ne permet pas de reconstruire `SKILLS_DIR`. Récupérer une compétence clone le head *actuel* de son dépôt : une exécution figée sur une révision plus ancienne ne retrouve donc pas cette révision et reste incapable de charger sa compétence. Sauvegardez ce répertoire.

Le répertoire d'une révision publiée n'est plus jamais modifié ensuite. Une copie prise pendant que l'application tourne est donc cohérente :

```bash
tar -czf skills-$(date +%F).tgz -C /var/lib/a2flow/skills .
```

Avec Docker Compose, le magasin est le volume nommé `skills` :

```bash
docker run --rm -v a2flow_skills:/skills -v "$PWD:/backup" alpine \
  tar -czf /backup/skills-$(date +%F).tgz -C /skills .
```

Pour restaurer, extrayez l'archive dans un magasin vide, puis démarrez le backend.

## La clé de chiffrement des secrets {#the-secret-encryption-key}

Si vous définissez explicitement `SECRET_ENCRYPTION_KEY`, la clé se trouve déjà là où vous conservez la configuration du déploiement et ne demande rien de plus ici : assurez-vous simplement que cet emplacement est lui-même sauvegardé.

Sinon, le backend en a généré une à la première utilisation et l'a écrite dans le fichier indiqué par `SECRET_KEY_FILE` (par défaut `.secret_key`, à côté du fichier de base de données SQLite). Ce fichier en est l'unique copie. Sauvegardez-le ailleurs que sur la machine qui l'héberge et traitez-le comme l'identifiant sensible qu'il est.

Avec Docker Compose, le fichier se trouve dans le volume nommé `secret-key` :

```bash
docker run --rm -v a2flow_secret-key:/key -v "$PWD:/backup" alpine   cp /key/.secret_key /backup/secret_key-$(date +%F)
```

La rotation de la clé n'est pas prise en charge : les secrets existants sont chiffrés avec l'ancienne. Consultez [Gestion des secrets](./configuration.md#secret-management).

## Vérifier une restauration {#checking-a-restore}

1. Démarrez le backend et vérifiez que [`GET /api/v1/health`](./health.md) renvoie 200 : cela prouve que la base de données est joignable et que le schéma est à jour.
2. Ouvrez un [secret](../guides/secrets.md) `local` dans l'interface d'administration. S'il se charge sans erreur, c'est la preuve que la clé correspond à la base de données.
3. Ouvrez une [exécution](../guides/workflow-executions.md) qui était en cours. Si elle reprend au lieu de signaler `SKILL_NOT_READY`, c'est la preuve que le magasin de compétences a bien été restauré avec les révisions encore utilisées.
