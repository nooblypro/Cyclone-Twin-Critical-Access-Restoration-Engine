"""
Persistence Repository Factory for Cyclone Twin
Instantiates the configured persistence engine (SQLite vs In-Memory Fallback).
"""

import os
import logging
from typing import Optional

from .repository import PersistenceRepository
from .sqlite_repository import SQLitePersistenceRepository
from .in_memory_repository import InMemoryPersistenceRepository

logger = logging.getLogger("cyclone_twin.persistence.factory")

_persistence_singleton: Optional[PersistenceRepository] = None


def get_persistence_repository(
    db_path: Optional[str] = None,
    force_new: bool = False,
) -> PersistenceRepository:
    """
    Factory function returning active PersistenceRepository instance.
    Defaults to SQLite storage with safe in-memory fallback.
    """
    global _persistence_singleton

    if _persistence_singleton is not None and not force_new:
        return _persistence_singleton

    mode = os.getenv("CYCLONE_TWIN_PERSISTENCE", "sqlite").lower().strip()

    if mode == "in_memory":
        logger.info("[PERSISTENCE FACTORY] Initialized InMemoryPersistenceRepository (explicit config)")
        repo = InMemoryPersistenceRepository()
    else:
        try:
            repo = SQLitePersistenceRepository(db_path=db_path)
            if not repo.active:
                logger.warning("[PERSISTENCE FACTORY] SQLite inactive, falling back to InMemoryPersistenceRepository")
                repo = InMemoryPersistenceRepository()
        except Exception as err:
            logger.warning(f"[PERSISTENCE FACTORY] SQLite exception '{err}', falling back to InMemoryPersistenceRepository")
            repo = InMemoryPersistenceRepository()

    if not force_new:
        _persistence_singleton = repo

    return repo
