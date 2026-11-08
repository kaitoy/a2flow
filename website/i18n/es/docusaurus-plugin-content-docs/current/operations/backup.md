---
title: Copia de seguridad y restauración
sidebar_position: 4
---

# Copia de seguridad y restauración

[Tres cosas](./deployment.md#state-that-has-to-persist) deben sobrevivir a la pérdida de un contenedor. Todo lo demás (servidores MCP registrados, flujos de trabajo, usuarios, configuración del sistema) es una fila de la base de datos y queda cubierto al hacer copia de seguridad de esta.

| Qué | Cómo se copia | Cómo se restaura |
|---|---|---|
| Base de datos | `pg_dump`, o una copia del archivo SQLite | `pg_restore`, o vuelve a colocar el archivo |
| Almacén de skills de agente | Una copia del árbol de `SKILLS_DIR` | Extráelo de nuevo en su sitio |
| Clave de cifrado de secretos | El valor de `SECRET_ENCRYPTION_KEY`, o el archivo de `SECRET_KEY_FILE` | Establece el mismo valor, o vuelve a colocar el mismo archivo |

**Restaura la base de datos y la clave a la vez.** La clave descifra los secretos locales *y* la clave de firma de la CA de aprobaciones, ambos almacenados en la base de datos. Una base de datos restaurada junto a otra clave arranca con todos los secretos ilegibles.

## La base de datos {#the-database}

PostgreSQL:

```bash
pg_dump --format=custom --file=a2flow-$(date +%F).dump "postgresql://user:password@host:5432/a2flow"
pg_restore --clean --if-exists --dbname="postgresql://user:password@host:5432/a2flow" a2flow-2026-01-31.dump
```

Con Docker Compose, accede directamente al servicio `db`:

```bash
docker compose exec -T db pg_dump -U a2flow -Fc a2flow > a2flow-$(date +%F).dump
docker compose exec -T db pg_restore -U a2flow -d a2flow --clean --if-exists < a2flow-2026-01-31.dump
```

SQLite es un único archivo, en la ruta indicada en `DB_URL`. Usa `sqlite3 a2flow.db ".backup out.db"` en lugar de copiarlo mientras la aplicación está en marcha.

Una base de datos restaurada no necesita un paso de migración aparte: al arrancar, el backend aplica las migraciones de [Alembic](https://alembic.sqlalchemy.org/) pendientes, así que basta con restaurar un volcado antiguo en una compilación más reciente y arrancarla para poner el esquema al día.

## El almacén de skills de agente {#the-agent-skill-store}

`SKILLS_DIR` no se puede reconstruir volviendo a registrar las skills. Actualizar una skill clona el HEAD *actual* de su repositorio, de modo que una ejecución fijada a una revisión anterior no recupera esa revisión y sigue sin poder cargar su skill. Haz copia de seguridad del directorio.

El directorio de una revisión publicada no se modifica nunca después, por lo que una copia hecha con la aplicación en marcha es coherente:

```bash
tar -czf skills-$(date +%F).tgz -C /var/lib/a2flow/skills .
```

Con Docker Compose, el almacén es el volumen con nombre `skills`:

```bash
docker run --rm -v a2flow_skills:/skills -v "$PWD:/backup" alpine \
  tar -czf /backup/skills-$(date +%F).tgz -C /skills .
```

Para restaurarlo, extrae el archivo comprimido en un almacén vacío y después arranca el backend.

## La clave de cifrado de secretos {#the-secret-encryption-key}

Si estableciste `SECRET_ENCRYPTION_KEY` explícitamente, la clave ya está donde guardes la configuración del despliegue y aquí no hace falta nada más; solo asegúrate de que ese almacén tenga a su vez copia de seguridad.

Si no lo hiciste, el backend generó una en el primer uso y la escribió en el archivo de `SECRET_KEY_FILE` (de forma predeterminada `.secret_key`, junto al archivo de la base de datos SQLite). Ese archivo es la única copia. Guarda una copia de seguridad fuera de la máquina en la que está y trátalo como la credencial que es.

Con Docker Compose, el archivo está en el volumen con nombre `secret-key`:

```bash
docker run --rm -v a2flow_secret-key:/key -v "$PWD:/backup" alpine   cp /key/.secret_key /backup/secret_key-$(date +%F)
```

No se admite la rotación de la clave: los secretos existentes están cifrados con la antigua. Consulta [Gestión de secretos](./configuration.md#secret-management).

## Comprobar una restauración {#checking-a-restore}

1. Arranca el backend y confirma que [`GET /api/v1/health`](./health.md) devuelve 200: eso demuestra que la base de datos es accesible y que el esquema está al día.
2. Abre un [secreto](../guides/secrets.md) de tipo `local` en la interfaz de administración. Que se cargue sin error demuestra que la clave corresponde a la base de datos.
3. Abre una [ejecución](../guides/workflow-executions.md) que estuviera en curso. Que se reanude en lugar de informar de `SKILL_NOT_READY` demuestra que el almacén de skills ha vuelto con las revisiones aún en uso.
