"""Shared lazy service construction for MCP and the later executor."""
from .reader import MySQLRentalReader
from .reliability import RetryingRentalReader
from .service import RentalService


def build_service(*, reader=None, policy=None, attempt_observer=None) -> RentalService:
    if isinstance(reader, RetryingRentalReader):
        if ((policy is not None and policy != reader.policy)
                or (attempt_observer is not None and attempt_observer is not reader.attempt_observer)):
            raise ValueError("Conflicting retry policy or observer for an already wrapped reader.")
        return RentalService(reader)
    underlying = reader if reader is not None else MySQLRentalReader()
    return RentalService(RetryingRentalReader(underlying, policy, attempt_observer))
