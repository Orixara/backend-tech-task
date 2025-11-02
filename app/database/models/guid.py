from typing import Any, Optional
from uuid import UUID

from sqlalchemy import CHAR, TypeDecorator, Dialect
from sqlalchemy.dialects.postgresql import UUID as PostgreSQL_UUID
from sqlalchemy.sql.type_api import TypeEngine, _T


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgreSQL_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_literal_param(
        self, value: Optional[_T], dialect: Dialect
    ) -> str:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value) if isinstance(value, UUID) else str(UUID(value))

    def process_result_value(
        self, value: Optional[Any], dialect: Dialect
    ) -> Optional[_T]:
        if value is None:
            return value
        return value if isinstance(value, UUID) else UUID(value)
