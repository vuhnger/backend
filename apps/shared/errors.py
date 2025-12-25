"""
Secure Error Handling

Provides utilities for handling errors securely without leaking sensitive information.
"""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


def log_and_sanitize_error(
    error: Exception,
    context: str,
    user_message: Optional[str] = None
) -> tuple[str, str]:
    """
    Log full error details server-side and return sanitized message for client.

    Args:
        error: The exception that occurred
        context: Description of what operation failed (e.g., "Token exchange")
        user_message: Optional custom message to show user. If None, uses generic message.

    Returns:
        Tuple of (sanitized_message, error_id) for client response
    """
    # Generate unique error ID for correlation
    error_id = str(uuid.uuid4())[:8]

    # Log full error server-side
    logger.error(
        f"{context} failed [{error_id}]: {type(error).__name__}: {str(error)}",
        exc_info=True
    )

    # Return sanitized message for client
    if user_message:
        sanitized = f"{user_message} (Error ID: {error_id})"
    else:
        sanitized = f"{context} failed. Please try again later. (Error ID: {error_id})"

    return sanitized, error_id
