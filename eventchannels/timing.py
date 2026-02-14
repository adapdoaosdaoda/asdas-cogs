"""Centralized timing constants and policy functions for EventChannels cog.

This module provides a single source of truth for all timing-related business rules,
avoiding magic numbers scattered throughout the codebase.
"""

from datetime import datetime, timedelta, timezone

# =============================================================================
# Timing Constants - Single Source of Truth
# =============================================================================

# Minutes before deletion to show warning message
WARNING_MINUTES = 15

# Default hours after event start to delete channels
DEFAULT_DELETION_HOURS = 4

# Hours to extend deletion when user reacts with clock emoji
EXTENSION_HOURS = 4

# Default minutes before event start to create channels
DEFAULT_CREATION_MINUTES = 15


# =============================================================================
# Policy Functions
# =============================================================================

def calculate_delete_time(start_time: datetime, deletion_hours: int) -> datetime:
    """Calculate when channels should be deleted based on event start time.

    Args:
        start_time: Event start time (should be timezone-aware UTC)
        deletion_hours: Hours after event start to delete channels

    Returns:
        Timezone-aware datetime when channels should be deleted
    """
    return start_time + timedelta(hours=deletion_hours)


def calculate_warning_time(delete_time: datetime) -> datetime:
    """Calculate when to send the deletion warning message.

    Warning is sent WARNING_MINUTES before deletion.

    Args:
        delete_time: When channels will be deleted (timezone-aware UTC)

    Returns:
        Timezone-aware datetime when warning should be sent
    """
    return delete_time - timedelta(minutes=WARNING_MINUTES)


def calculate_extended_delete_time(current_delete_time: datetime) -> datetime:
    """Calculate new deletion time after user extends with clock reaction.

    Args:
        current_delete_time: Current scheduled deletion time (timezone-aware UTC)

    Returns:
        New deletion time extended by EXTENSION_HOURS
    """
    return current_delete_time + timedelta(hours=EXTENSION_HOURS)


def format_default_warning_message() -> str:
    """Generate the default archiving warning message using timing constants.

    Returns:
        Formatted warning message string
    """
    return (
        f"These channels will be archived in {WARNING_MINUTES} minutes. "
        f"React with to extend archiving by {EXTENSION_HOURS} hours."
    )


def format_extension_message(user_mention: str, delete_time: datetime) -> str:
    """Format the extension notification message.

    Args:
        user_mention: Discord mention string for the user who extended
        delete_time: When channels will now be archived (timezone-aware UTC)

    Returns:
        Formatted extension notification string
    """
    timestamp = int(delete_time.timestamp())
    return (
        f"\n\n⏰ **Extended by {user_mention}**: Archiving postponed by {EXTENSION_HOURS} hours. "
        f"Channels will now be archived <t:{timestamp}:R>."
    )
