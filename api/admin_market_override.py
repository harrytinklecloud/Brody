from http.server import BaseHTTPRequestHandler
from datetime import UTC, datetime, timedelta

from api._brody import empty_response, json_response, read_json, require_admin, upsert_setting


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        empty_response(self)

    def do_POST(self):
        user = require_admin(self)
        if not user:
            return
        payload = read_json(self)
        minutes = max(1, int(payload.get("minutes") or 15))
        upsert_setting("force_open_until", (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat())
        return json_response(self, {"ok": True})
