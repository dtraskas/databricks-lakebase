# Lakebase Template

A minimal starter template for building applications with Databricks Lakebase. A Python FastAPI backend serves a React frontend and connects to a Lakebase (Autoscaling Postgres) endpoint using OAuth tokens that are refreshed automatically in the background.

## Features

- **FastAPI Backend**: Async Python backend with SQLAlchemy + asyncpg connection pooling
- **Lakebase Integration**: Connects to a Lakebase Postgres endpoint with automatic OAuth token rotation
- **React Frontend**: Modern React UI with Vite, served directly from the backend
- **OAuth Tokens**: Fresh credentials minted via the Databricks SDK and refreshed every 40 minutes
- **Deploy-first workflow**: Ships to Databricks Apps via Databricks Asset Bundles (DABs)

## Quick Start

### 1. Initialize the Project

```bash
uv run python -m scripts.quickstart
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
uv run python -m scripts.start_app
```

Visit `http://localhost:8000` to see your app.

**Optional**: Start with the frontend dev server (Vite hot reload):
```bash
uv run python -m scripts.start_app --dev
```

## Environment Variables

A single set of variables works for both local development and Databricks deployment. Copy `.env.example` to `.env` (gitignored) and fill in your values.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LAKEBASE_ENDPOINT` | **Yes** | — | Endpoint resource path. Locally it resolves the host and mints OAuth tokens; on deploy it is injected from the postgres resource binding via `valueFrom` in `app.yaml`. |
| `PGDATABASE` | No | `databricks_postgres` | Postgres database name. |
| `PGUSER` | No | current Databricks user | Connecting Postgres role. On deploy the platform injects the app's service principal client ID. |
| `PGHOST` | No | resolved from endpoint | Lakebase hostname. Auto-injected on Databricks Apps; resolved locally from `LAKEBASE_ENDPOINT`. |

> **Local vs. deploy:** Locally these come from `.env` via `load_dotenv()`. On Databricks Apps, `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGSSLMODE` are auto-injected from the postgres resource binding — but `LAKEBASE_ENDPOINT` is **not**, so `app.yaml` maps it explicitly with `valueFrom`. Authentication is always OAuth; there is no static-password option.

Find the endpoint path with:
```bash
databricks postgres list-endpoints projects/<project>/branches/<branch>
```

Example `.env`:
```
LAKEBASE_ENDPOINT=projects/dev-instance/branches/production/endpoints/primary
PGDATABASE=databricks_postgres
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
uv run python -m scripts.quickstart

# Start backend + built frontend
uv run python -m scripts.start_app

# Start with frontend dev server (Vite hot reload)
uv run python -m scripts.start_app --dev

# Run health checks
uv run python -m scripts.preflight

# Deploy to Databricks Apps
uv run python -m scripts.deploy

# Start backend directly
python -m backend.app

# Rebuild frontend
cd frontend && npm run build
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

```bash
# 1. Build the frontend
cd frontend && npm run build && cd ..

# 2. Deploy the bundle (uploads source + updates the app spec)
databricks bundle deploy --profile <PROFILE>

# 3. Deploy the app itself so it restarts with the new config
databricks apps deploy lakebase \
  --source-code-path "/Workspace/Users/<you>/.bundle/lakebase/dev/files" \
  --profile <PROFILE>
```

Or use the helper: `uv run python -m scripts.deploy --profile <PROFILE>`.

> **Important:** `databricks bundle deploy` updates the app spec but does **not** restart the running container. Environment-variable changes only take effect after `databricks apps deploy` (or a stop/start). The `LAKEBASE_ENDPOINT` mapping in `app.yaml` uses `valueFrom: lakebase-postgres` (the resource name) — for an Autoscaling Lakebase resource this resolves to the endpoint path.

### Schema permissions

The deployed app's service principal has `CAN_CONNECT_AND_CREATE` — it can create new objects but cannot access schemas owned by another role. **Deploy the app before running it locally** so the service principal creates and owns the schema. See the `databricks-lakebase` skill for recovery steps if you hit `permission denied for schema`.
