import hashlib
import json
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import certifi
from flask import Flask, jsonify, request


APP = Flask(__name__)
LOCK = threading.Lock()
PT = ZoneInfo("America/Los_Angeles")
TICK_SECONDS = 5
STARTING_CASH = 10_000.0
SESSIONS = {}


def load_env():
    root = os.path.dirname(os.path.dirname(__file__))
    env_path = os.path.join(root, ".env.local")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "")
BRODY_PORT = int(os.environ.get("BRODY_PORT", "8787"))
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


@APP.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


def utc_now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def supabase_headers(prefer=None):
    headers = {
        "apikey": SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def supabase_request(method, path, query=None, body=None, prefer=None):
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError("Missing Supabase configuration")

    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query, doseq=True)}"

    payload = None if body is None else json.dumps(body).encode("utf-8")
    request_obj = urllib.request.Request(
        url,
        data=payload,
        headers=supabase_headers(prefer=prefer),
        method=method,
    )

    try:
        with urllib.request.urlopen(request_obj, context=SSL_CONTEXT) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8")
        try:
            parsed = json.loads(detail)
            message = parsed.get("message") or parsed.get("error") or parsed.get("hint") or detail
        except json.JSONDecodeError:
            message = detail or str(error)
        raise RuntimeError(message) from error


def table_select(table, filters=None, columns="*"):
    query = {"select": columns}
    if filters:
        query.update(filters)
    return supabase_request("GET", table, query=query)


def table_insert(table, rows, returning=False):
    prefer = "return=representation" if returning else "return=minimal"
    return supabase_request("POST", table, body=rows, prefer=prefer)


def table_update(table, filters, values, returning=False):
    query = {}
    query.update(filters)
    prefer = "return=representation" if returning else "return=minimal"
    return supabase_request("PATCH", table, query=query, body=values, prefer=prefer)


def table_delete(table, filters):
    return supabase_request("DELETE", table, query=filters, prefer="return=minimal")


def get_user_by_username(username):
    rows = table_select("brody_users", {"username": f"eq.{username}"})
    return rows[0] if rows else None


def get_user_by_id(user_id):
    rows = table_select("brody_users", {"id": f"eq.{user_id}"})
    return rows[0] if rows else None


def get_stock_by_symbol(symbol):
    rows = table_select("brody_stocks", {"symbol": f"eq.{symbol}"})
    return rows[0] if rows else None


def get_all_stocks():
    return table_select("brody_stocks", {"order": "symbol.asc"})


def get_all_users():
    return table_select("brody_users", {"order": "username.asc"})


def get_holdings_for_user(user_id):
    return table_select(
        "brody_holdings",
        {"user_id": f"eq.{user_id}"},
        columns="user_id,stock_id,shares,avg_cost,brody_stocks(symbol,name,sector,price,last_close)",
    )


def get_trade_history(user_id):
    return table_select(
        "brody_trades",
        {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "30"},
        columns="side,shares,price,created_at,brody_stocks(symbol)",
    )


def get_history_points(user_id):
    rows = table_select(
        "brody_history_points",
        {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "20"},
        columns="value",
    )
    return list(reversed([float(row["value"]) for row in rows]))


def get_latest_announcement():
    rows = table_select("brody_announcements", {"order": "created_at.desc", "limit": "1"})
    return rows[0]["message"] if rows else ""


def get_setting(key, default=None):
    rows = table_select("brody_settings", {"key": f"eq.{key}"})
    if not rows:
        return default
    value = rows[0]["value"]
    return value if value is not None else default


def set_setting(key, value):
    table_insert("brody_settings", [{"key": key, "value": value}], returning=False)


def upsert_setting(key, value):
    existing = table_select("brody_settings", {"key": f"eq.{key}"})
    if existing:
        table_update("brody_settings", {"key": f"eq.{key}"}, {"value": value})
    else:
        table_insert("brody_settings", [{"key": key, "value": value}])


def issue_token(user_id):
    token = secrets.token_hex(24)
    SESSIONS[token] = user_id
    return token


def auth_user():
    header = request.headers.get("Authorization", "")
    token = header.replace("Bearer ", "")
    user_id = SESSIONS.get(token)
    if not user_id:
        return None
    return get_user_by_id(user_id)


def require_user():
    user = auth_user()
    if not user or user.get("banned"):
        return None, (jsonify({"error": "Unauthorized"}), 401)
    return user, None


def require_admin():
    user, error = require_user()
    if error:
        return None, error
    if not user.get("is_admin"):
        return None, (jsonify({"error": "Admin access required"}), 403)
    return user, None


def market_is_open():
    forced_until = get_setting("force_open_until", "")
    if forced_until:
        try:
            if datetime.fromisoformat(forced_until) > datetime.now(UTC):
                return True
        except ValueError:
            pass
    now = datetime.now(PT)
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=8, minute=55, second=0, microsecond=0)
    close_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
    return open_time <= now <= close_time


def compute_portfolio(user):
    holdings = get_holdings_for_user(user["id"])
    cash = float(user["cash"])
    market_value = 0.0
    unrealized_pl = 0.0
    allocations = []
    serialized = []
    for row in holdings:
        stock = row["brody_stocks"]
        shares = float(row["shares"])
        avg_cost = float(row["avg_cost"])
        price = float(stock["price"])
        value = shares * price
        pl = value - (shares * avg_cost)
        market_value += value
        unrealized_pl += pl
        allocations.append({"label": stock["symbol"], "value": round(value, 2)})
        serialized.append({
            "symbol": stock["symbol"],
            "name": stock["name"],
            "shares": shares,
            "avg_cost": avg_cost,
            "price": price,
            "market_value": round(value, 2),
            "unrealized_pl": round(pl, 2),
        })
    portfolio_value = cash + market_value
    return {
        "cash": round(cash, 2),
        "market_value": round(market_value, 2),
        "portfolio_value": round(portfolio_value, 2),
        "unrealized_pl": round(unrealized_pl, 2),
        "holdings_count": len(serialized),
        "holdings": serialized,
        "allocations": allocations,
    }


def compute_leaderboard():
    users = [user for user in get_all_users() if not user.get("banned")]
    board = []
    for user in users:
        portfolio = compute_portfolio(user)
        board.append({
            "username": user["username"],
            "portfolio_value": portfolio["portfolio_value"],
            "holdings_count": portfolio["holdings_count"],
            "is_admin": bool(user["is_admin"]),
        })
    board.sort(key=lambda item: item["portfolio_value"], reverse=True)
    return board


def record_history_point(user_id, value):
    table_insert("brody_history_points", [{
        "user_id": user_id,
        "value": round(value, 2),
    }])


def record_history_for_all_users():
    for user in get_all_users():
        if not user.get("banned"):
            record_history_point(user["id"], compute_portfolio(user)["portfolio_value"])


def snapshot_for_user(user):
    stocks = get_all_stocks()
    portfolio = compute_portfolio(user)
    leaderboard = compute_leaderboard()
    rank = next((index + 1 for index, item in enumerate(leaderboard) if item["username"] == user["username"]), len(leaderboard))
    trade_rows = get_trade_history(user["id"])
    history_points = get_history_points(user["id"])
    movers = []
    for stock in stocks:
      price = float(stock["price"])
      last_close = float(stock["last_close"])
      change_pct = round(((price - last_close) / max(last_close, 0.01)) * 100, 2)
      movers.append({
          "symbol": stock["symbol"],
          "name": stock["name"],
          "change_pct": change_pct,
      })
    movers.sort(key=lambda item: abs(item["change_pct"]), reverse=True)

    basis = max(portfolio["market_value"], 1)
    summary = {
        **portfolio,
        "rank": rank,
        "history": history_points,
        "unrealized_pct": round((portfolio["unrealized_pl"] / basis) * 100, 2) if portfolio["holdings_count"] else 0.0,
    }

    return {
        "me": {
            "username": user["username"],
            "is_admin": bool(user["is_admin"]),
        },
        "market": {
            "market_open": market_is_open(),
            "announcement": get_latest_announcement(),
            "stocks": [
                {
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "sector": stock["sector"],
                    "price": round(float(stock["price"]), 2),
                    "change_pct": round(((float(stock["price"]) - float(stock["last_close"])) / max(float(stock["last_close"]), 0.01)) * 100, 2),
                }
                for stock in stocks
            ],
            "portfolio": portfolio,
            "summary": summary,
            "leaderboard": leaderboard,
            "movers": movers[:8],
            "trade_history": [
                {
                    "side": row["side"],
                    "shares": float(row["shares"]),
                    "price": float(row["price"]),
                    "symbol": row["brody_stocks"]["symbol"],
                    "created_at": row["created_at"],
                }
                for row in trade_rows
            ],
            "admin": {
                "users": [
                    {
                        "username": row["username"],
                        "cash": float(row["cash"]),
                        "is_admin": bool(row["is_admin"]),
                        "banned": bool(row["banned"]),
                    }
                    for row in get_all_users()
                ]
            },
        },
    }


def update_or_create_holding(user_id, stock_id, shares, avg_cost):
    rows = table_select("brody_holdings", {"user_id": f"eq.{user_id}", "stock_id": f"eq.{stock_id}"})
    if rows:
        table_update(
            "brody_holdings",
            {"user_id": f"eq.{user_id}", "stock_id": f"eq.{stock_id}"},
            {"shares": shares, "avg_cost": avg_cost},
        )
    else:
        table_insert("brody_holdings", [{
            "user_id": user_id,
            "stock_id": stock_id,
            "shares": shares,
            "avg_cost": avg_cost,
        }])


def delete_holding(user_id, stock_id):
    table_delete("brody_holdings", {"user_id": f"eq.{user_id}", "stock_id": f"eq.{stock_id}"})


def tick_prices_forever():
    while True:
        time.sleep(TICK_SECONDS)
        try:
            if not market_is_open():
                continue
            with LOCK:
                stocks = get_all_stocks()
                for stock in stocks:
                    current = float(stock["price"])
                    drift = (secrets.randbelow(701) - 350) / 10000.0
                    next_price = max(1.0, round(current * (1 + drift), 2))
                    table_update(
                        "brody_stocks",
                        {"id": f"eq.{stock['id']}"},
                        {"price": next_price, "updated_at": utc_now()},
                    )
                record_history_for_all_users()
        except Exception:
            continue


@APP.route("/api/<path:_path>", methods=["OPTIONS"])
def options_handler(_path):
    return ("", 204)


@APP.post("/api/login")
def login():
    payload = request.get_json(force=True)
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = get_user_by_username(username)
    if not user or user["password_hash"] != hash_password(password) or user.get("banned"):
        return jsonify({"error": "Invalid username or password"}), 401
    token = issue_token(user["id"])
    return jsonify({"token": token})


@APP.get("/api/state")
def state_endpoint():
    user, error = require_user()
    if error:
        return error
    with LOCK:
        payload = snapshot_for_user(user)
    return jsonify(payload)


@APP.post("/api/trade")
def trade():
    user, error = require_user()
    if error:
        return error

    payload = request.get_json(force=True)
    symbol = payload.get("symbol")
    side = payload.get("side")
    shares = float(payload.get("shares") or 0)
    if shares <= 0:
        return jsonify({"error": "Shares must be greater than zero"}), 400
    if side not in {"buy", "sell"}:
        return jsonify({"error": "Invalid trade side"}), 400
    if not market_is_open():
        return jsonify({"error": "Market is closed"}), 400

    with LOCK:
        user = get_user_by_id(user["id"])
        stock = get_stock_by_symbol(symbol)
        if not stock:
            return jsonify({"error": "Unknown symbol"}), 404
        price = float(stock["price"])
        total = round(price * shares, 2)
        holding_rows = table_select("brody_holdings", {"user_id": f"eq.{user['id']}", "stock_id": f"eq.{stock['id']}"})
        holding = holding_rows[0] if holding_rows else None

        if side == "buy":
            if float(user["cash"]) < total:
                return jsonify({"error": "Not enough cash"}), 400
            current_shares = float(holding["shares"]) if holding else 0.0
            current_avg = float(holding["avg_cost"]) if holding else 0.0
            next_shares = current_shares + shares
            next_avg = ((current_shares * current_avg) + total) / next_shares
            table_update("brody_users", {"id": f"eq.{user['id']}"}, {"cash": round(float(user["cash"]) - total, 2)})
            update_or_create_holding(user["id"], stock["id"], round(next_shares, 2), round(next_avg, 2))
        else:
            if not holding or float(holding["shares"]) < shares:
                return jsonify({"error": "Not enough shares"}), 400
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
        record_history_point(user["id"], compute_portfolio(get_user_by_id(user["id"]))["portfolio_value"])

    return jsonify({"ok": True})


@APP.post("/api/admin/announcement")
def announcement():
    _, error = require_admin()
    if error:
        return error
    payload = request.get_json(force=True)
    message = (payload.get("message") or "").strip()
    with LOCK:
        table_insert("brody_announcements", [{"message": message}])
    return jsonify({"ok": True})


@APP.post("/api/admin/market-override")
def market_override():
    _, error = require_admin()
    if error:
        return error
    minutes = max(1, int((request.get_json(force=True).get("minutes") or 15)))
    with LOCK:
        upsert_setting("force_open_until", (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat())
    return jsonify({"ok": True})


@APP.post("/api/admin/bulk-action")
def bulk_action():
    admin, error = require_admin()
    if error:
        return error
    action = (request.get_json(force=True).get("action") or "").strip()
    with LOCK:
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
            return jsonify({"error": "Unknown admin action"}), 400
        record_history_for_all_users()
    return jsonify({"ok": True})


def main():
    threading.Thread(target=tick_prices_forever, daemon=True).start()
    APP.run(host="0.0.0.0", port=BRODY_PORT, debug=False)


if __name__ == "__main__":
    main()
