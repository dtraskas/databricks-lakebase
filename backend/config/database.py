import asyncio
import logging
import os
import socket
import ssl
import subprocess
from typing import AsyncGenerator

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv
from sqlalchemy import URL, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()
logger = logging.getLogger(__name__)

DB_PORT = 5432
POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT = 30
POOL_RECYCLE = 3600  # recycle connections before the ~1h OAuth token expires
COMMAND_TIMEOUT = 10
TOKEN_REFRESH_INTERVAL = 40 * 60  # refresh every 40 minutes (tokens expire after 1 hour)

# Global state
engine: AsyncEngine | None = None
AsyncSessionLocal: sessionmaker | None = None
workspace_client: WorkspaceClient | None = None
endpoint_name: str | None = None
_current_token: list[str] = [""]  # mutable container so the do_connect closure sees updates
token_refresh_task: asyncio.Task | None = None


def _resolve_connection_target(hostname: str) -> tuple[str, ssl.SSLContext]:
    """Return (host_or_ip, ssl_context) for hostname.

    Falls back to querying 8.8.8.8 when local DNS cannot resolve Databricks
    privatelink hostnames (common on macOS with corporate/VPN DNS).
    """
    try:
        socket.getaddrinfo(hostname, DB_PORT, type=socket.SOCK_STREAM)
        return hostname, ssl.create_default_context()
    except socket.gaierror:
        pass

    logger.warning("Local DNS cannot resolve %r — falling back to 8.8.8.8", hostname)
    result = subprocess.run(
        ["dig", "+short", "@8.8.8.8", hostname],
        capture_output=True, text=True, timeout=10,
    )
    ips = [
        line.strip() for line in result.stdout.splitlines()
        if line.strip() and "." in line and not line.strip().endswith(".")
    ]
    if not ips:
        raise RuntimeError(f"Cannot resolve {hostname!r}: local and public DNS both failed")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # cert chain still verified (CERT_REQUIRED stays set)
    return ips[0], ctx


def _generate_token() -> str:
    return workspace_client.postgres.generate_database_credential(endpoint_name).token


async def _refresh_token_background():
    """Refresh the Postgres OAuth token before it expires."""
    while True:
        await asyncio.sleep(TOKEN_REFRESH_INTERVAL)
        try:
            _current_token[0] = _generate_token()
        except Exception as e:
            logger.error("Token refresh failed: %s", e)


def init_engine():
    """Initialize the async SQLAlchemy engine for the Lakebase Postgres endpoint.

    Reads from env vars that work in both environments:
      LAKEBASE_ENDPOINT  endpoint resource path (required)
      PGHOST             hostname — auto-injected on Databricks Apps; resolved locally
      PGDATABASE         database name (default: databricks_postgres)
      PGUSER             connecting role (defaults to the current Databricks user)

    Locally these come from .env via load_dotenv(); on Databricks Apps they are
    auto-injected from the postgres resource binding.
    """
    global engine, AsyncSessionLocal, workspace_client, endpoint_name

    try:
        workspace_client = WorkspaceClient()

        endpoint_name = os.environ.get("LAKEBASE_ENDPOINT")
        if not endpoint_name:
            raise RuntimeError("LAKEBASE_ENDPOINT environment variable is required")

        # On Databricks Apps, PGHOST is auto-injected from the postgres resource binding.
        # Locally, resolve it from the endpoint resource path.
        host = os.environ.get("PGHOST")
        if not host:
            endpoint = workspace_client.postgres.get_endpoint(endpoint_name)
            host = endpoint.status.hosts.host

        target_host, ssl_ctx = _resolve_connection_target(host)

        _current_token[0] = _generate_token()

        database_name = os.environ.get("PGDATABASE", "databricks_postgres")
        username = os.environ.get("PGUSER") or workspace_client.current_user.me().user_name

        url = URL.create(
            drivername="postgresql+asyncpg",
            username=username,
            password="",  # set by the do_connect event handler
            host=target_host,
            port=DB_PORT,
            database=database_name,
        )

        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            echo=False,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_recycle=POOL_RECYCLE,
            connect_args={
                "command_timeout": COMMAND_TIMEOUT,
                "server_settings": {"application_name": "lakebase_app"},
                "ssl": ssl_ctx,
            },
        )

        @event.listens_for(engine.sync_engine, "do_connect")
        def provide_token(dialect, conn_rec, cargs, cparams):
            cparams["password"] = _current_token[0]

        AsyncSessionLocal = sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info("Database engine initialized: %s @ %s", database_name, host)

    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        raise RuntimeError(f"Failed to initialize database: {e}") from e


async def start_token_refresh():
    global token_refresh_task
    if token_refresh_task is None or token_refresh_task.done():
        token_refresh_task = asyncio.create_task(_refresh_token_background())


async def stop_token_refresh():
    global token_refresh_task
    if token_refresh_task and not token_refresh_task.done():
        token_refresh_task.cancel()
        try:
            await token_refresh_task
        except asyncio.CancelledError:
            pass


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Engine not initialized; call init_engine() first")
    async with AsyncSessionLocal() as session:
        yield session


async def database_health() -> bool:
    """Return True if the database accepts a simple query."""
    if engine is None:
        return False
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            return True
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return False
