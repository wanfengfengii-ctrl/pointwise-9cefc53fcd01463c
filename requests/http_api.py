from museum_support import Reply


class ClaimHttpHandler:
    def __init__(self, application):
        self.application = application

    def __call__(self, request):
        app = self.application
        body = request.body
        match request.method, request.parts:
            case 'POST', ('claims',):
                return Reply(app.admit_claim(body.get('request_id'), body.get('version_id'),
                                             body.get('first'), body.get('last')))
            case 'GET', ('claims', request_id):
                return Reply(app.read_claim(request_id))
            case 'GET', ('sessions', session_id, 'claims', 'open'):
                return Reply(app.open_claims(session_id))
            case _:
                return None


def build_claim_handler(application):
    return ClaimHttpHandler(application)
