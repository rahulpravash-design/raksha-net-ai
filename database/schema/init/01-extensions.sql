-- Enabled here as well as in the first Alembic revision, because the extension
-- needs superuser rights that the application role does not have in a managed
-- database. Both paths are idempotent.
CREATE EXTENSION IF NOT EXISTS postgis;
