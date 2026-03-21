from http.server import BaseHTTPRequestHandler

from api._brody import (
    delete_holding,
    empty_response,
    get_stock_by_symbol,
    get_user_by_id,
    json_response,
    market_is_open,
    read_json,
    record_history_point,
    require_user,
    snapshot_for_user,
    table_insert,
    table_select,
    table_update,
    update_or_create_holding,
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        empty_response(self)

    def do_POST(self):
        user = require_user(self)
        if not user:
            return

        payload = read_json(self)
        symbol = payload.get("symbol")
        side = payload.get("side")
        shares = float(payload.get("shares") or 0)

        if shares <= 0:
            return json_response(self, {"error": "Shares must be greater than zero"}, 400)
        if side not in {"buy", "sell"}:
            return json_response(self, {"error": "Invalid trade side"}, 400)
        if not market_is_open():
            return json_response(self, {"error": "Market is closed"}, 400)

        user = get_user_by_id(user["id"])
        stock = get_stock_by_symbol(symbol)
        if not stock:
            return json_response(self, {"error": "Unknown symbol"}, 404)

        price = float(stock["price"])
        total = round(price * shares, 2)
        holding_rows = table_select("brody_holdings", {"user_id": f"eq.{user['id']}", "stock_id": f"eq.{stock['id']}"})
        holding = holding_rows[0] if holding_rows else None

        if side == "buy":
            if float(user["cash"]) < total:
                return json_response(self, {"error": "Not enough cash"}, 400)
            current_shares = float(holding["shares"]) if holding else 0.0
            current_avg = float(holding["avg_cost"]) if holding else 0.0
            next_shares = current_shares + shares
            next_avg = ((current_shares * current_avg) + total) / next_shares
            table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) - total, 2)})
            update_or_create_holding(user["id"], stock["id"], round(next_shares, 2), round(next_avg, 2))
        else:
            if not holding or float(holding["shares"]) < shares:
                return json_response(self, {"error": "Not enough shares"}, 400)
            next_shares = round(float(holding["shares"]) - shares, 2)
            table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) + total, 2)})
            if next_shares <= 0:
                delete_holding(user["id"], stock["id"])
            else:
                table_update(
                    "brody_holdings",
                    {"user_id": f"eq.{user['id']}", "stock_id": f"eq.{stock['id']}"},
                    {"shares": next_shares},
                )

        table_insert("brody_trades", [{
            "user_id": user["id"],
            "stock_id": stock["id"],
            "side": side,
            "shares": round(shares, 2),
            "price": round(price, 2),
        }])
        latest_user = get_user_by_id(user["id"])
        record_history_point(user["id"], snapshot_for_user(latest_user)["market"]["summary"]["portfolio_value"])
        return json_response(self, {"ok": True})
