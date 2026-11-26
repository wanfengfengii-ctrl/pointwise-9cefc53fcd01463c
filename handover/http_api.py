from dataclasses import asdict

from catalog.intake import register_draft
from catalog.lookup import read_release, read_segment
from catalog.release import release
from handover.close import archive
from handover.retrieve import archive_read
from museum_support import Reply, path_integer
from program.issue import program_issue


class DeskHttpHandler:
    def __init__(self, application):
        self.application = application

    def __call__(self, request):
        app = self.application
        body = request.body
        match request.method, request.parts:
            case 'POST', ('drafts',):
                with app.library() as library:
                    return Reply(asdict(register_draft(library, body)))
            case 'POST', ('releases',):
                with app.library() as library:
                    return Reply(asdict(release(library, body.get('recording_id'), body.get('revision'))))
            case 'GET', ('releases', version_id):
                with app.library() as library:
                    return Reply(asdict(read_release(library, path_integer(version_id))))
            case 'GET', ('releases', version_id, 'segments', number):
                with app.library() as library:
                    return Reply(asdict(read_segment(library, path_integer(version_id), path_integer(number))))
            case 'POST', ('lineups',):
                with app.library() as library:
                    return Reply(asdict(program_issue(library, body.get('session_id'), body.get('version_id'),
                                                       body.get('first'), body.get('last'))))
            case 'GET', ('lineups', lineup_id):
                return Reply(asdict(app.lineup(path_integer(lineup_id))))
            case 'POST', ('archives',):
                with app.library() as library, app.field() as field, app.ledger() as ledger:
                    return Reply(asdict(archive(library, field, ledger,
                                                body.get('session_id'), body.get('request_id'))))
            case 'GET', ('archives', archive_id):
                with app.ledger() as ledger:
                    return Reply(asdict(archive_read(ledger, path_integer(archive_id))))
            case _:
                return None


def build_desk_handler(application):
    return DeskHttpHandler(application)
