import os
from pathlib import Path
from dotenv import load_dotenv
from databricks.sdk import WorkspaceClient
import psycopg
from psycopg_pool import ConnectionPool
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

load_dotenv()

app = FastAPI()

# Enable CORS for frontend requests during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Databricks client for token generation (optional)
w = None
try:
    w = WorkspaceClient()
except (ValueError, Exception):
    pass

# Custom connection class with optional OAuth token generation
class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo='', **kwargs):
        # Try to generate fresh OAuth token if Databricks is configured
        if w and "ENDPOINT_NAME" in os.environ:
            try:
                endpoint_name = os.environ["ENDPOINT_NAME"]
                credential = w.postgres.generate_database_credential(endpoint=endpoint_name)
                kwargs['password'] = credential.token
                # Override user with the current Databricks identity (email for users,
                # client ID for service principals) so it always matches the OAuth token.
                kwargs['user'] = w.current_user.me().user_name
                return super().connect(conninfo, **kwargs)
            except Exception as e:
                print(f"Warning: OAuth token generation failed: {e}")

        # Fall back to PGPASSWORD if provided and not a placeholder
        if "PGPASSWORD" in os.environ:
            pw = os.environ["PGPASSWORD"]
            if pw and not pw.startswith("your-"):
                kwargs['password'] = pw
                return super().connect(conninfo, **kwargs)

        raise ValueError("No valid PostgreSQL password found. Set PGPASSWORD or ENDPOINT_NAME in .env")

# Configure connection parameters
username = os.environ["PGUSER"]
host = os.environ["PGHOST"]
port = os.environ.get("PGPORT", "5432")
database = os.environ["PGDATABASE"]
sslmode = os.environ.get("PGSSLMODE", "require")

# Create connection pool with automatic token rotation
pool = ConnectionPool(
    conninfo=f"dbname={database} user={username} host={host} port={port} sslmode={sslmode}",
    connection_class=OAuthConnection,
    min_size=1,
    max_size=10,
    open=True
)


@app.get("/api/lakebase/query")
async def query_lakebase(table: str = "information_schema.tables"):
    """Query Lakebase via the PostgreSQL endpoint with OAuth token"""
    try:
        with pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {table} LIMIT 10")
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return {
                    "columns": columns,
                    "data": [dict(zip(columns, row)) for row in rows]
                }
    except Exception as e:
        return {"error": str(e)}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


# Serve frontend
frontend_dir = Path(__file__).parent.parent / "frontend" / "dist"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {"message": "Frontend not built. Run 'npm run build' in the frontend directory"}


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)