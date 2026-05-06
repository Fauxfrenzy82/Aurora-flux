"""
Database layer — Supabase client and schema management.
"""

from .supabase_client import db, Database

__all__ = ["db", "Database"]