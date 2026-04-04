"""Shared UTC time utilities.

Centralized _utc_now() / _utcnow() to eliminate duplication across:
- app/domain/entities/provider.py
- app/domain/entities/policy.py
- app/domain/entities/log_entry.py
- app/infrastructure/database/models.py
- app/infrastructure/database/repositories.py
"""

from __future__ import annotations

import datetime


def _utc_now() -> datetime.datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.datetime.now(datetime.timezone.utc)


# Alias for modules that use the shorter name (_utcnow)
_utcnow = _utc_now
