from http.server import BaseHTTPRequestHandler

from api._brody import empty_response, json_response, read_json, require_admin, table_insert


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        empty_response(self)

    def do_POST(self):
        user = require_admin(self)
        if not user:
            return
        payload = read_json(self)
        message = (payload.get("message") or "").strip()
        table_insert("brody_announcements", [{"message": message}])
        return json_response(self, {"ok": True})
