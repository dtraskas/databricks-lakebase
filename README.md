# Lakebase Template

Minimal starter template for building applications with Databricks Lakebase. A Python FastAPI backend serves a React frontend and connects to a Lakebase endpoint using OAuth tokens that are refreshed automatically in the background.

## Quick Start

### 1. Initialise the Project

```bash
uv run quickstart
```

This will:
- Check prerequisites (Python 3.11+, Node.js, uv)
- Configure `.env` with your Lakebase connection details
- Install Python and frontend dependencies

### 2. Authenticate with Databricks

```bash
databricks auth login
```

This sets up credentials locally. The app uses them automatically to mint OAuth tokens for the Lakebase endpoint.

### 3. Start the App

```bash
uv run python start-app
```

## Environment Variables

A single set of variables works for both local development and Databricks deployment. Copy `.env.example` to `.env` and fill in your values.

`LAKEBASE_ENDPOINT`: Endpoint resource path. Locally it resolves the host and mints OAuth tokens; on deploy it is injected from the postgres resource binding via `valueFrom` in `app.yaml`. 

`PGDATABASE`: Postgres database name.

`LAKEBASE_BRANCH`: Selecting Production or other branches

Example `.env`:
```
LAKEBASE_ENDPOINT=projects/dev-instance/branches/production/endpoints/primary
PGDATABASE=databricks_postgres
LAKEBASE_BRANCH=production
```

## Project Structure

```
.
├── backend/
│   ├── app.py                 # FastAPI application (lifespan, routes, health)
│   └── config/
│       └── database.py        # Async engine, OAuth token refresh, pooling
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main React component
│   │   ├── api.js            # API client
│   │   └── index.css         # Styling
│   ├── vite.config.js        # Vite configuration
│   ├── tailwind.config.js    # Tailwind CSS config
│   └── package.json
├── scripts/
│   ├── quickstart.py         # Setup wizard
│   ├── start_app.py          # Application launcher
│   ├── deploy.py             # Databricks Apps deploy helper
│   ├── clean.py              # Tear down the deployment + local bundle state
│   └── preflight.py          # Health checks
├── app.yaml                  # Databricks Apps runtime config (command + env)
├── databricks.yaml           # Databricks Asset Bundle (app resource + postgres binding)
├── .env                      # Environment variables (local, gitignored)
├── .env.example              # Template
└── pyproject.toml            # Python dependencies
```

## API Endpoints

- `GET /health` — Health check, returns `{"status": "ok"}`
- `GET /api/lakebase/data` — Query a Lakebase table
  - `table` (default: `information_schema.tables`) — must be in `schema.table` format
  - `limit` (default: `10`, max `1000`)
  - Returns: `{columns: [], data: []}`
  - Returns `503` if the database engine failed to initialize (check `LAKEBASE_ENDPOINT`)

The built React frontend is served from `/`.

## Available Commands

```bash
# One-time setup
uv run quickstart

# Start backend + built frontend
uv run start-app

# Run health checks
uv run preflight

# Deploy to Databricks Apps
uv run deploy

# Tear down the deployment (and local .databricks/ state)
uv run clean

```

## Development

### Backend

The FastAPI backend lives in `backend/app.py`, with database wiring in `backend/config/database.py`:

- Async SQLAlchemy engine over `asyncpg` with connection pooling and `pool_pre_ping`
- OAuth token minted at startup and refreshed in a background task every 40 minutes
- A `do_connect` event handler injects the current token as the connection password
- DNS fallback for local environments where corporate/VPN DNS can't resolve privatelink hostnames

### Frontend

The React frontend is in `frontend/src`. To modify:

1. Edit components in `src/`
2. Rebuild: `cd frontend && npm run build`
3. Or use the dev server: `uv run python -m scripts.start_app --dev`

## Deployment

The app deploys to **Databricks Apps** via Databricks Asset Bundles. The bundle ([databricks.yaml](databricks.yaml)) defines the app and binds it to the Lakebase database; [app.yaml](app.yaml) defines the runtime command and maps `LAKEBASE_ENDPOINT` from the resource binding.

### Teardown

Remove the deployed app, its compute, and the uploaded source files, then delete the local `.databricks/` bundle state:

```bash
uv run python clean
```

This runs `databricks bundle destroy` followed by removing `.databricks/`. It prompts for confirmation (skip with `--auto-approve`). The **Lakebase project/database is not touched** — it is referenced by the bundle, not created by it, so your data is safe.

### Schema permissions

The deployed app's service principal has `CAN_CONNECT_AND_CREATE` — it can create new objects but cannot access schemas owned by another role. **Deploy the app before running it locally** so the service principal creates and owns the schema. See the `databricks-lakebase` skill for recovery steps if you hit `permission denied for schema`.
