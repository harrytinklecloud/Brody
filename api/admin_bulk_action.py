from http.server import BaseHTTPRequestHandler

from api._brody import (
    STARTING_CASH,
    compute_leaderboard,
    empty_response,
    get_all_users,
    get_user_by_id,
    get_user_by_username,
    json_response,
    read_json,
    record_history_point,
    require_admin,
    snapshot_for_user,
    table_delete,
    table_update,
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        empty_response(self)

    def do_POST(self):
        admin = require_admin(self)
        if not admin:
            return

        action = (read_json(self).get("action") or "").strip()
        users = get_all_users()

        if action == "give_500k_all":
            for user in users:
                table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) + 500000, 2)})
        elif action == "give_10m_all":
            for user in users:
                table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) + 10000000, 2)})
        elif action == "double_cash_all":
            for user in users:
                table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) * 2, 2)})
        elif action == "halve_cash_all":
            for user in users:
                table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) * 0.5, 2)})
        elif action == "tax_all_20":
            for user in users:
                table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) * 0.8, 2)})
        elif action == "take_all_cash":
            for user in users:
                if not user["is_admin"]:
                    table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": 0})
        elif action == "wipe_all_holdings":
            table_delete("brody_holdings", {"stock_id": "gte.0"})
        elif action == "reset_all_players":
            table_delete("brody_holdings", {"stock_id": "gte.0"})
            table_delete("brody_trades", {"id": "gte.0"})
            for user in users:
                table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": STARTING_CASH})
        elif action == "steal_from_richest":
            board = [entry for entry in compute_leaderboard() if entry["username"] != admin["username"]]
            if board:
                target = get_user_by_username(board[0]["username"])
                stolen = round(float(target["cash"]) * 0.35, 2)
                table_update("brody_users", {"id": f"eq.{target['id']}"}, {"cash": round(float(target["cash"]) - stolen, 2)})
                latest_admin = get_user_by_id(admin["id"])
                table_update("brody_users", {"id": f"eq.{latest_admin['id']}"}, {"cash": round(float(latest_admin["cash"]) + stolen, 2)})
        else:
            return json_response(self, {"error": "Unknown admin action"}, 400)

        for user in get_all_users():
            latest = get_user_by_id(user["id"])
            record_history_point(user["id"], snapshot_for_user(latest)["market"]["summary"]["portfolio_value"])
        return json_response(self, {"ok": True})
