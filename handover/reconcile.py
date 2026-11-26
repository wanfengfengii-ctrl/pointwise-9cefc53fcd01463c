from dataclasses import dataclass

from catalog.lookup import read_release
from catalog.release import ReleasedSource
from channel.history import TakeHistory, read_session_takes, read_version_takes
from handover.provenance import OriginReference, resolve_play_origins
from program.session import read_session
from requests.fulfillment import find_qualifying_coverage
from requests.pending import claim_document, read_version_claims


@dataclass(frozen=True)
class HandoverFacts:
    session_id: str
    release: ReleasedSource
    takes: tuple[TakeHistory, ...]
    claims: tuple[dict, ...]
    origins: tuple[OriginReference, ...]


def reconcile_session(library, field, ledger, session_id):
    session = read_session(library, session_id)
    version_id = session.version_id
    released = read_release(library, version_id)
    own_takes = read_session_takes(field, session_id)
    version_takes = read_version_takes(field, version_id)
    claims = read_version_claims(ledger, field, version_id, version_takes)
    takes_by_id = {history.take.take_id: history for history in version_takes}
    evidence = {play.actual_id: play for history in own_takes for play in history.plays}
    for claim in claims:
        settlement = claim.settlement
        if settlement is None:
            continue
        history = takes_by_id.get(settlement.take_id)
        if history is None:
            raise RuntimeError('Settlement take is missing from its release history')
        coverage = find_qualifying_coverage(claim, (history,))
        if coverage is None or coverage.actual_ids != settlement.actual_ids:
            raise RuntimeError('Settlement does not match actual play evidence')
        ids = set(settlement.actual_ids)
        evidence.update((play.actual_id, play) for play in history.plays if play.actual_id in ids)
    origins = resolve_play_origins(library, version_id,
                                   (evidence[key] for key in sorted(evidence)))
    return HandoverFacts(session_id, released, own_takes,
                         tuple(claim_document(claim) for claim in claims), origins)
