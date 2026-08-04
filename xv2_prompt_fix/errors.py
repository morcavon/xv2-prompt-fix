class FixError(RuntimeError):
    """Expected, user-facing workflow error."""


class CancelledError(FixError):
    """Raised when the user cancels an active workflow."""
