from dataclasses import dataclass

from museum_support import identity
from program.windows import resolve_window


@dataclass(frozen=True)
class ClaimWindow:
    version_id: int
    first: int
    last: int


def validate_claim_window(library, version_id, first, last):
    version_id = identity(version_id)
    window = resolve_window(library, version_id, first, last)
    return ClaimWindow(version_id, window.first, window.last)
