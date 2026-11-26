from dataclasses import asdict

from channel.history import read_claim_boundary
from museum_support import EvidenceUnavailable, transaction
from program.session import read_session
from requests.admission import confirm_admission, resume_admission
from requests.fulfillment import settle_claim
from requests.ledger import read_claim, scan_version_claims


def claim_document(claim, *, review_needed=False):
    if claim.settlement is not None:
        status = 'settled'
    elif claim.admitted_after is None or review_needed:
        status = 'pending_review'
    else:
        status = 'pending'
    return {
        'request_id': claim.request_id,
        'version_id': claim.window.version_id,
        'first': claim.window.first,
        'last': claim.window.last,
        'status': status,
        'settlement': None if claim.settlement is None else asdict(claim.settlement),
    }


def refresh_claim(open_ledger, read_history, claim):
    if claim.settlement is not None or claim.admitted_after is None:
        return claim_document(claim)
    try:
        histories = read_history(claim.window.version_id)
    except EvidenceUnavailable:
        with open_ledger() as ledger:
            return claim_document(read_claim(ledger, claim.request_id), review_needed=True)
    with open_ledger() as ledger, transaction(ledger, write=True):
        current = read_claim(ledger, claim.request_id)
        return claim_document(settle_claim(ledger, current, histories))


def claim_read(open_ledger, register_boundary, read_history, request_id):
    claim = resume_admission(open_ledger, request_id, register_boundary)
    return refresh_claim(open_ledger, read_history, claim)


def list_open_claims(library, open_ledger, register_boundary, read_history, session_id):
    session = read_session(library, session_id)
    with open_ledger() as ledger:
        claims = scan_version_claims(ledger, session.version_id)
    result = []
    for claim in claims:
        if claim.settlement is None:
            current = claim_read(open_ledger, register_boundary, read_history, claim.request_id)
            if current['status'] != 'settled':
                result.append(current)
    return result


def read_version_claims(ledger, field, version_id, histories):
    # During capture, use only admissions visible at the field snapshot.
    claims = []
    for claim in scan_version_claims(ledger, version_id):
        if claim.admitted_after is None:
            boundary = read_claim_boundary(field, claim.request_id)
            claim = confirm_admission(ledger, claim, boundary)
        claims.append(settle_claim(ledger, claim, histories))
    return tuple(claims)
