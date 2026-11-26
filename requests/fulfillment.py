from dataclasses import dataclass

from channel.history import TakeHistory
from requests.ledger import Claim, Settlement, save_settlement


@dataclass(frozen=True)
class Coverage:
    take_id: int
    actual_ids: tuple[int, ...]


def find_qualifying_coverage(claim: Claim, histories: tuple[TakeHistory, ...]):
    boundary = claim.admitted_after
    if boundary is None:
        return None
    responsible = None
    if claim.transfer is not None:
        # A transferred claim can only be settled by the receiving session,
        # with the window's first segment actually played after the transfer.
        responsible = claim.transfer.to_session_id
        boundary = max(boundary, claim.transfer.after_actual_id)
    window = claim.window
    required = window.last - window.first + 1
    for history in histories:
        take = history.take
        if take.version_id != window.version_id:
            continue
        if responsible is not None and take.session_id != responsible:
            continue
        selected = tuple(play for play in history.plays if window.first <= play.number <= window.last)
        if len(selected) != required or selected[0].actual_id <= boundary:
            continue
        start_position = selected[0].position
        if all(play.number == window.first + offset and play.position == start_position + offset
               for offset, play in enumerate(selected)):
            return Coverage(take.take_id, tuple(play.actual_id for play in selected))
    return None


def settle_claim(ledger, claim, histories):
    if claim.settlement is not None:
        return claim
    coverage = find_qualifying_coverage(claim, histories)
    if coverage is None:
        return claim
    settlement = Settlement(claim.request_id, coverage.take_id, coverage.actual_ids)
    return save_settlement(ledger, settlement)
