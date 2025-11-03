from .auth import router as auth_router
from .events import router as events_router
from .stats import router as stats_router

__all__ = ["events_router", "stats_router", "auth_router"]
