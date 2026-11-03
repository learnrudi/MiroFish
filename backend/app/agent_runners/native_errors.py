"""Errors crossing the local/remote execution boundary."""


class TransportUnavailable(RuntimeError):
    """Remote outcome is unknown; reconcile the same task/key, never resubmit anew."""
