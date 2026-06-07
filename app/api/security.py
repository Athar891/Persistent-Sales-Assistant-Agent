"""API-key authentication for the data + LLM endpoints.

A single shared key (the ``API_KEY`` setting) gates ``/chat`` and ``/reviews`` — the
endpoints that read/mutate user data or spend LLM budget. ``/health`` and ``/catalog``
stay open: the platform health-checks the former, and the latter is public pricing.

When no key is configured the guard allows every request, so local dev and tests run
keyless; ``validate_runtime_config`` refuses to boot production without one, so the open
default can never reach production silently.
"""

import secrets
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.api.deps import SettingsDep

API_KEY_HEADER = "X-API-Key"
_api_key_scheme = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


async def require_api_key(
    settings: SettingsDep,
    provided: Annotated[str | None, Security(_api_key_scheme)] = None,
) -> None:
    expected = settings.api_key
    if not expected:
        return  # auth disabled (dev/test only — production boot is guarded)
    # Constant-time compare so a wrong key can't be recovered by timing the response.
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid API key."
        )
