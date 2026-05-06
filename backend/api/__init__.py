"""
API module — REST and WebSocket server.
"""

from .server import app, current_state, broadcast, get_system_status

__all__ = [
    "app",
    "current_state",
    "broadcast",
    "get_system_status",
]