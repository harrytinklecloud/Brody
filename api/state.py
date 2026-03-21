from http.server import BaseHTTPRequestHandler

from api._brody import empty_response, json_response, require_user, snapshot_for_user


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        empty_response(self)

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        return json_response(self, snapshot_for_user(user))
