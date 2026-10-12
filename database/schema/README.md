# Database schema

The schema is defined by the SQLAlchemy models in `backend/app/models/` and
applied through the Alembic revisions in `backend/migrations/versions/`. There
is no hand-maintained DDL file — it would drift.

- `init/` runs once, when the development Postgres container initialises an
  empty data directory. It only enables extensions.
- To inspect the current schema: `psql -d raksha_net_ai -c '\d+ incidents'`.
- To regenerate a migration after changing a model:
  `cd backend && alembic revision --autogenerate -m "feat(db): ..."`,
  then **read the generated file** before committing it. Autogenerate does not
  detect enum value changes or data migrations.

See `docs/DATABASE.md` for the entity design and the retention policy.
