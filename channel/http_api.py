from dataclasses import asdict

from museum_support import Reply, identity, path_integer, token


class ChannelHttpHandler:
    def __init__(self, application):
        self.application = application

    def __call__(self, request):
        body = request.body
        app = self.application
        match request.method, request.parts:
            case 'POST', ('takes',):
                take = app.start(body.get('lineup_id'), body.get('request_id'))
                return Reply({'take_id': take.take_id, 'lineup_id': take.lineup_id,
                              'session_id': take.session_id, 'version_id': take.version_id})
            case 'POST', ('takes', take_id, 'steps'):
                take_id = identity(path_integer(take_id))
                original = token(body.get('request_id'))
                app.observe('before_actual', original)
                actual = app.step(take_id, original)
                drop = bool(app.observe('after_actual', original))
                return Reply(asdict(actual), drop=drop)
            case 'POST', ('takes', take_id, 'stop'):
                return Reply(asdict(app.stop(identity(path_integer(take_id)), body.get('request_id'))))
            case 'GET', ('takes', take_id):
                return Reply(asdict(app.take_history(identity(path_integer(take_id)))))
            case _:
                return None


def build_channel_handler(application):
    return ChannelHttpHandler(application)
