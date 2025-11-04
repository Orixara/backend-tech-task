from uuid import UUID
from sqlalchemy import TypeDecorator, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQL_UUID
from sqlalchemy.types import CHAR


class UniversalUUID(TypeDecorator):
    impl = CHAR(36)
    cache_ok = True

    python_type = UUID


    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PostgreSQL_UUID(as_uuid=True))
        elif dialect.name == 'duckdb':
            return dialect.type_descriptor(String(36))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value

        if not isinstance(value, UUID):
            try:
                value = UUID(value)
            except (ValueError, AttributeError):
                raise ValueError(f"Invalid UUID value: {value}")

        if dialect.name == 'postgresql':
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value

        if isinstance(value, UUID):
            return value

        try:
            return UUID(value)
        except (ValueError, AttributeError):
            raise ValueError(f"Cannot convert to UUID: {value}")

    def process_literal_param(self, value, dialect):
        if value is None:
            return "NULL"
        return f"'{str(value)}'"

    @property
    def python_type(self):
        return UUID
