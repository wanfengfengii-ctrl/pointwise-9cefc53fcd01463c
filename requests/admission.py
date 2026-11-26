from museum_support import EvidenceUnavailable, token, transaction
from requests.ledger import read_claim, save_admission, save_pending_review
from requests.range_check import validate_claim_window


def confirm_admission(ledger, claim, boundary):
    if boundary is None:
        return claim
    expected = (claim.window.version_id, claim.window.first, claim.window.last)
    if (boundary.request_id != claim.request_id
            or (boundary.version_id, boundary.first, boundary.last) != expected):
        raise RuntimeError('Admission evidence does not identify this request')
    return save_admission(ledger, claim.request_id, boundary.after_actual_id)


def resume_admission(open_ledger, request_id, register_boundary):
    request_id = token(request_id)
    with open_ledger() as ledger:
        claim = read_claim(ledger, request_id)
    if claim.admitted_after is not None:
        return claim
    try:
        boundary = register_boundary(claim)
    except EvidenceUnavailable:
        with open_ledger() as ledger:
            return read_claim(ledger, request_id)
    with open_ledger() as ledger, transaction(ledger, write=True):
        return confirm_admission(ledger, claim, boundary)


def admit(library, open_ledger, register_boundary, request_id, version_id, first, last):
    request_id = token(request_id)
    window = validate_claim_window(library, version_id, first, last)
    # The request identity is durable before the field can establish its order.
    with open_ledger() as ledger, transaction(ledger, write=True):
        save_pending_review(ledger, request_id, window)
    return resume_admission(open_ledger, request_id, register_boundary)
