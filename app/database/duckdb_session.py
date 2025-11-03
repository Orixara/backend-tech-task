import os
import duckdb

from config.settings import settings


class DuckDBConnection:
    def __init__(self):
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._db_path = str(settings.duckdb_path_absolute)

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            self._conn = duckdb.connect(self._db_path)
            self._initialize_schema()

        return self._conn

    def _initialize_schema(self):
        self._conn.execute("""
           CREATE TABLE IF NOT EXISTS events(
               event_id    VARCHAR PRIMARY KEY,
               occurred_at TIMESTAMP NOT NULL,
               user_id     VARCHAR   NOT NULL,
               event_type  VARCHAR   NOT NULL,
               properties  JSON,
               created_at  TIMESTAMP NOT NULL,
               archived_at TIMESTAMP NOT NULL
           )
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_occurred_at
            ON events (occurred_at)
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_type
            ON events (event_type)
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id
            ON events (user_id)
        """)

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


_duckdb_connection: DuckDBConnection | None = None


def get_duckdb_connection() -> DuckDBConnection:
    global _duckdb_connection
    if _duckdb_connection is None:
        _duckdb_connection = DuckDBConnection()
    return _duckdb_connection


def get_duckdb() -> duckdb.DuckDBPyConnection:
    return get_duckdb_connection().get_connection()


def close_duckdb():
    global _duckdb_connection
    if _duckdb_connection:
        _duckdb_connection.close()
        _duckdb_connection = None