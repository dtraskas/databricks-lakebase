# Lakebase Template

A minimal starter template for building applications with Databricks Lakebase. Includes a Python FastAPI backend serving a React frontend with OAuth token rotation for secure PostgreSQL connections.

## Features

- **FastAPI Backend**: High-performance Python backend with automatic CORS
- **Lakebase Integration**: Connect to Lakebase PostgreSQL endpoint with OAuth token rotation
- **React Frontend**: Modern React UI with Vite, served directly from the backend
- **OAuth Tokens**: Automatic token generation via Databricks SDK
- **Static Credentials**: Optional support for static PostgreSQL passwords

## Quick Start

### 1. Initialize the Project

```bash
uv run python -m scripts.quickstart
```

This will:
- Check prerequisites (Python 3.11+, Node.js, uv)
- Configure `.env` with your Lakebase connection details
- Install Python and frontend dependencies

### 2. Authenticate with Databricks (if using OAuth)

```bash
databricks auth login
```

This sets up credentials locally and the app will use them automatically.

### 3. Start the App

```bash
uv run python -m scripts.start_app
```

Visit `http://localhost:8000` to see your app.

**Optional**: Start with frontend dev server:
```bash
uv run python -m scripts.start_app --dev
```

## Environment Setup

Create a `.env` file with your Lakebase connection details:

```
PGHOST=your-endpoint.postgres.azuredatabricks.net
PGDATABASE=databricks_postgres
PGUSER=your_email@example.com
PGPORT=5432
PGSSLMODE=require

# Choose one authentication method:

# Option 1: OAuth (recommended)
ENDPOINT_NAME=projects/your-project/branches/main/endpoints/primary

# Option 2: Static password
PGPASSWORD=your-postgresql-password
```

## Project Structure

```
.
├── backend/
│   └── app.py              # FastAPI application
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # Main React component
│   │   ├── api.js          # API client
│   │   └── index.css       # Styling
│   ├── vite.config.js      # Vite configuration
│   ├── tailwind.config.js  # Tailwind CSS config
│   └── package.json
├── scripts/
│   ├── start_app.py        # Application launcher
│   ├── quickstart.py       # Setup wizard
│   └── preflight.py        # Health checks
├── .env                    # Environment variables (local)
├── .env.example            # Template
└── pyproject.toml          # Python dependencies
```

## API Endpoints

- `GET /health` - Health check
- `GET /api/lakebase/query` - Query the Lakebase PostgreSQL endpoint
  - Query parameter: `table` (default: `information_schema.tables`)
  - Returns: `{columns: [], data: []}`

Static frontend files are served from `/`.

## Authentication Methods

### OAuth Tokens (Recommended)

Set `ENDPOINT_NAME` and run `databricks auth login`. The app generates fresh tokens for each connection automatically.

```
ENDPOINT_NAME=projects/dev/branches/main/endpoints/primary
```

### Static Password

Set `PGPASSWORD` directly. Useful for local testing or service accounts.

```
PGPASSWORD=your-password
```

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

# Start backend directly
python -m backend.app

# Rebuild frontend
cd frontend && npm run build
```

## Development

### Backend

The FastAPI backend is in `backend/app.py`. Key features:

- OAuth connection class that generates fresh tokens
- Connection pooling with psycopg
- CORS middleware for frontend communication
- Static file serving for the built React app

### Frontend

The React frontend is in `frontend/src`. To modify:

1. Edit components in `src/`
2. Rebuild: `cd frontend && npm run build`
3. Or use dev server: `uv run python -m scripts.start_app --dev`

## Troubleshooting

### "Failed to fetch" in frontend

Make sure:
1. Backend is running: `python -m backend.app`
2. Frontend is built: `cd frontend && npm run build`
3. CORS is enabled (it is by default)

### "cannot configure default credentials" error

You need to authenticate with Databricks:
```bash
databricks auth login
```

Or set `PGPASSWORD` in `.env` for static credentials.

### Port already in use

The scripts will automatically find an available port. Or specify one:
```bash
uv run python -m scripts.start_app --backend-port 9000
```

## Deployment

### Building for Production

```bash
# Backend: already configured with uvicorn
# Frontend: build React app
cd frontend && npm run build
```

The built frontend is automatically served by the backend at `/`.

### Docker

Create a `Dockerfile` if deploying to containerized environments. The `app.yaml` and `manifest.yaml` files are for Databricks App deployments.

## Next Steps

1. Customize the frontend UI in `frontend/src/App.jsx`
2. Add more API endpoints in `backend/app.py`
3. Query different tables with the `/api/lakebase/query` endpoint
4. Deploy to your infrastructure

## License

MIT
