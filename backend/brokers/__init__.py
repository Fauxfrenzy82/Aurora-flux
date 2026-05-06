"""
Broker integration module — Deriv WebSocket bridge.
"""

from .deriv_client import deriv, DerivClient

__all__ = ["deriv", "DerivClient"]