"""Bind an OAuth callback to the account that owns the integration.

Both OAuth callbacks are public — they have to be, since the provider redirects
the browser to them — and ``validate_state()`` only proves *this server minted a
state in the last 10 minutes*, not *who* it was minted for. Nothing else stood
between an arbitrary caller and the single-user row:

    1. attacker opens /strava/authorize and gets a valid state
    2. attacker authorizes with their own Strava account
    3. the callback upserts row id=1 with the attacker's tokens

That destroys the owner's stored grant (re-authorization required) and repoints
the public portfolio at someone else's activity data.

Ownership is established on first authorization and enforced from then on, so no
configuration is needed for the common case. Setting the owner id explicitly is
supported for when the row has to be re-established from scratch.
"""

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_REJECTED = "This integration belongs to another account."


def enforce_owner(
    db: Session,
    model: type[Any],
    id_field: str,
    incoming_id: Any,
    configured_owner: Any | None,
    provider: str,
) -> None:
    """Reject the callback unless it belongs to the integration's owner.

    Args:
        db: Session used to look up the existing single-user row.
        model: The auth model (``StravaAuth`` / ``WakaTimeAuth``).
        id_field: Attribute holding the provider's account id on that model.
        incoming_id: Account id from the OAuth exchange being validated.
        configured_owner: Explicit owner id from settings, or ``None`` to fall
            back to whichever account authorized first.
        provider: Provider name, used in the log line only.

    Raises:
        HTTPException: 403 if the callback is for a different account.
    """
    if configured_owner is not None:
        if str(incoming_id) != str(configured_owner):
            logger.warning(
                "%s callback rejected: account %s is not the configured owner",
                provider, incoming_id,
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=_REJECTED)
        return

    # Trust on first use: the first account to authorize becomes the owner.
    existing = db.query(model).filter(model.id == 1).first()
    if existing is None:
        return

    owner_id = getattr(existing, id_field, None)
    if owner_id is not None and str(owner_id) != str(incoming_id):
        logger.warning(
            "%s callback rejected: account %s tried to replace owner %s",
            provider, incoming_id, owner_id,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=_REJECTED)
