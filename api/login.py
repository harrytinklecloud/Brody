from http.server import BaseHTTPRequestHandler

from api._brody import get_user_by_username, hash_password, issue_token, json_response, read_json, empty_response


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        empty_response(self)

    def do_POST(self):
        payload = read_json(self)
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        user = get_user_by_username(username)
        if not user or user["password_hash"] != hash_password(password) or user.get("banned"):
            return json_response(self, {"error": "Invalid username or password"}, 401)
        return json_response(self, {"token": issue_token(user["id"])})
