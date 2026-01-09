# wizard-ui — BornToShare (dev)

The wizard initializes the platform in development mode:

- validates connectivity to `db_api:3306`
- creates the **application database/user** (using a privileged DB connection)
- applies the SQL schema from `backend/app/schema_initial.sql`
- creates the initial local admin user (for dev)
- stores optional settings (e.g. syslog target)

## DB env (backend)

- `DB_HOST` (default: `db_api`)
- `DB_PORT` (default: `3306`)
- `DB_NAME` (default: `b2s`)
- `DB_USER` (default: `b2s_api`)
- `DB_PASSWORD` (default: `b2s_api_password`)

For database creation via the wizard (service account):
- `DB_ROOT_USER` (default: `root`)
- `DB_ROOT_PASSWORD` (**required** for create-db step)

## Schema

The schema file is kept **MariaDB-compatible** (no placeholders, no `CREATE INDEX IF NOT EXISTS`).
