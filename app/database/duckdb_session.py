import logging
from pathlib import Path

from config.settings import settings
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)


class DuckDBConnection:
    def __init__(self, db_path: str = None, read_only: bool = False):
        self._db_path = db_path or settings.DUCKDB_PATH
        self._engine = None
        self._session_factory = None
        self._read_only = read_only
        logger.info(f"Initializing DuckDB connection: path={self._db_path}, " f"read_only={read_only}")

    def _create_engine(self):
        if self._db_path == ":memory:":
            connection_string = "duckdb:///:memory:"
        else:
            db_path = Path(self._db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured directory exists: {db_path.parent}")

            connection_string = f"duckdb:///{self._db_path}"

        logger.info(f"Creating DuckDB engine: {connection_string}")

        self._engine = create_engine(
            connection_string,
            connect_args={
                "read_only": self._read_only,
            },
            poolclass=NullPool,
            echo=False,
        )

        @event.listens_for(self._engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            logger.debug(f"DuckDB connection established: read_only={self._read_only}")

        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
        )

    def get_engine(self):
        if self._engine is None:
            self._create_engine()
            if not self._read_only:
                self._initialize_schema()
        return self._engine

    def get_session(self) -> Session:
        if self._session_factory is None:
            self._create_engine()
            if not self._read_only:
                self._initialize_schema()
        return self._session_factory()

    def _initialize_schema(self):
        try:
            logger.info("Initializing DuckDB schema using raw SQL")
            with self._engine.connect() as connection:
                for stmt in ("INSTALL json", "LOAD json"):
                    try:
                        connection.execute(text(stmt))
                    except Exception:
                        pass

                connection.execute(text("CREATE SEQUENCE IF NOT EXISTS events_id_seq START 1"))

                connection.execute(
                    text(
                        """
                    CREATE TABLE IF NOT EXISTS events(
                        id BIGINT PRIMARY KEY DEFAULT nextval('events_id_seq'),
                        event_id VARCHAR(36) UNIQUE NOT NULL,
                        occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        user_id VARCHAR(100) NOT NULL,
                        event_type  VARCHAR(100) NOT NULL,
                        properties  JSON NOT NULL,
                        created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        is_archived BOOLEAN NOT NULL DEFAULT FALSE
                    )
                """
                    )
                )

                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_events_user_occurred ON events (user_id, occurred_at)")
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_events_type_occurred ON events (event_type, occurred_at)")
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_events_user_type_occurred ON events (user_id, event_type, occurred_at)"
                    )
                )
                connection.execute(
                    text("CREATE INDEX IF NOT EXISTS ix_events_archived_occurred ON events (is_archived, occurred_at)")
                )

                connection.commit()
            logger.info("DuckDB schema initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing DuckDB schema: {e}", exc_info=True)
            raise

    def close(self):
        if self._engine:
            logger.info("Closing DuckDB connection")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None


_duckdb_write_conn: DuckDBConnection | None = None
_duckdb_read_conn: DuckDBConnection | None = None


def get_duckdb_engine():
    global _duckdb_write_conn
    if _duckdb_write_conn is None:
        _duckdb_write_conn = DuckDBConnection(read_only=False)
    return _duckdb_write_conn.get_engine()


def get_duckdb_session() -> Session:
    global _duckdb_write_conn
    if _duckdb_write_conn is None:
        _duckdb_write_conn = DuckDBConnection(read_only=False)
    return _duckdb_write_conn.get_session()


def get_duckdb_read_engine():
    global _duckdb_read_conn
    if _duckdb_read_conn is None:
        _duckdb_read_conn = DuckDBConnection(read_only=True)
    return _duckdb_read_conn.get_engine()


def get_duckdb_read_session() -> Session:
    global _duckdb_read_conn
    if _duckdb_read_conn is None:
        _duckdb_read_conn = DuckDBConnection(read_only=True)
    return _duckdb_read_conn.get_session()


def close_duckdb():
    global _duckdb_write_conn, _duckdb_read_conn

    if _duckdb_write_conn:
        _duckdb_write_conn.close()
        _duckdb_write_conn = None

    if _duckdb_read_conn:
        _duckdb_read_conn.close()
        _duckdb_read_conn = None

    logger.info("All DuckDB connections closed")


def get_duckdb_connection() -> DuckDBConnection:
    logger.warning("get_duckdb_connection() is deprecated, use get_duckdb_session() instead")
    global _duckdb_write_conn
    if _duckdb_write_conn is None:
        _duckdb_write_conn = DuckDBConnection(read_only=False)
    return _duckdb_write_conn


def get_duckdb():
    logger.warning("get_duckdb() is deprecated, use get_duckdb_read_session() instead")
    return get_duckdb_read_session()
