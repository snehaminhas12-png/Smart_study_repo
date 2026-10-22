"""Smart Study News App: Flask web server and Gemini API proxy."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from collections import defaultdict, deque
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request, send_from_directory
from pywebpush import WebPushException, webpush

ROOT = Path(__file__).resolve().parent


def load_local_env_file() -> None:
    """Read local .env values without replacing variables already set by the host."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name and name not in os.environ:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in (chr(34), chr(39)):
                value = value[1:-1]
            os.environ[name] = value


load_local_env_file()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
MAX_BODY_BYTES = 12_000
RATE_LIMIT = 10
RATE_WINDOW_SECONDS = 60
_request_times: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(ROOT / "subscriptions.sqlite3")))
_push_lock = threading.Lock()


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _init_push_db():
    with _db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS push_subscriptions (
            endpoint TEXT PRIMARY KEY, subscription TEXT NOT NULL, reminder_time TEXT NOT NULL,
            timezone TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, sent_date TEXT NOT NULL DEFAULT ''
        )""")


_init_push_db()


@app.get("/")
@app.get("/login")
@app.get("/subjects")
def home():
    return send_from_directory(ROOT, "index.html", max_age=0)


@app.get("/styles.css")
def styles():
    return send_from_directory(ROOT, "styles.css", max_age=3600)


@app.get("/app.js")
def javascript():
    return send_from_directory(ROOT, "app.js", max_age=0)


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(ROOT, "manifest.webmanifest", mimetype="application/manifest+json", max_age=3600)


@app.get("/service-worker.js")
def service_worker():
    response = send_from_directory(ROOT, "service-worker.js", max_age=0)
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.get("/icon.svg")
def app_icon():
    return send_from_directory(ROOT, "icon.svg", mimetype="image/svg+xml", max_age=3600)


@app.get("/api/health")
def health():
    return jsonify(ok=True, configured=bool(os.environ.get("GEMINI_API_KEY")), push_configured=bool(os.environ.get("VAPID_PUBLIC_KEY") and os.environ.get("VAPID_PRIVATE_KEY")))


@app.get("/api/push/public-key")
def push_public_key():
    key = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
    if not key or not os.environ.get("VAPID_PRIVATE_KEY", "").strip():
        return jsonify(error="Push notifications are not configured on the server."), 503
    return jsonify(publicKey=key)


@app.post("/api/push/subscribe")
def push_subscribe():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON request."), 400
    subscription = data.get("subscription")
    reminder_time = _text(data.get("time"), 5)
    timezone = _text(data.get("timezone"), 80)
    endpoint = subscription.get("endpoint") if isinstance(subscription, dict) else ""
    if not isinstance(endpoint, str) or not endpoint.startswith("https://") or len(endpoint) > 2000:
        return jsonify(error="A valid push subscription is required."), 400
    if len(reminder_time) != 5 or reminder_time[2] != ":" or not reminder_time[:2].isdigit() or not reminder_time[3:].isdigit() or int(reminder_time[:2]) > 23 or int(reminder_time[3:]) > 59:
        return jsonify(error="Choose a valid reminder time."), 400
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return jsonify(error="A valid phone time zone is required."), 400
    with _db() as db:
        db.execute("""INSERT INTO push_subscriptions(endpoint,subscription,reminder_time,timezone,active,sent_date)
            VALUES(?,?,?,?,1,'') ON CONFLICT(endpoint) DO UPDATE SET
            subscription=excluded.subscription, reminder_time=excluded.reminder_time,
            timezone=excluded.timezone, active=1""",
            (endpoint, json.dumps(subscription), reminder_time, timezone))
    return jsonify(ok=True)


@app.post("/api/push/unsubscribe")
def push_unsubscribe():
    data = request.get_json(silent=True)
    endpoint = data.get("endpoint", "") if isinstance(data, dict) else ""
    if isinstance(endpoint, str):
        with _db() as db:
            db.execute("UPDATE push_subscriptions SET active=0 WHERE endpoint=?", (endpoint,))
    return jsonify(ok=True)


def _send_due_pushes():
    public_key = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
    private_key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not public_key or not private_key:
        return
    with _push_lock, _db() as db:
        subscriptions = db.execute("SELECT * FROM push_subscriptions WHERE active=1").fetchall()
        for row in subscriptions:
            try:
                local_now = datetime.now(ZoneInfo(row["timezone"]))
            except (ZoneInfoNotFoundError, ValueError):
                continue
            if local_now.strftime("%H:%M") < row["reminder_time"] or row["sent_date"] == local_now.date().isoformat():
                continue
            try:
                webpush(
                    subscription_info=json.loads(row["subscription"]),
                    data=json.dumps({"title": "A little study time?", "body": "Your daily study reminder is ready. Open Daylight for a bite-sized discovery."}),
                    vapid_private_key=private_key,
                    vapid_claims={"sub": os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")},
                    ttl=3600,
                )
                db.execute("UPDATE push_subscriptions SET sent_date=? WHERE endpoint=?", (local_now.date().isoformat(), row["endpoint"]))
            except WebPushException as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status in (404, 410):
                    db.execute("UPDATE push_subscriptions SET active=0 WHERE endpoint=?", (row["endpoint"],))
                else:
                    app.logger.warning("Could not deliver a scheduled push notification: %s", error)
            except (ValueError, TypeError, KeyError):
                app.logger.warning("A stored push subscription could not be read; disabling it.")
                db.execute("UPDATE push_subscriptions SET active=0 WHERE endpoint=?", (row["endpoint"],))


def _start_push_scheduler():
    if os.environ.get("DISABLE_PUSH_SCHEDULER") == "1":
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    scheduler.add_job(_send_due_pushes, "interval", minutes=1, id="daily-study-push", max_instances=1, coalesce=True)
    scheduler.start()


_start_push_scheduler()


def _rate_limit_exceeded(client_ip: str) -> bool:
    """Simple per-client burst limit to protect the demo's Gemini quota."""
    now = time.monotonic()
    with _rate_lock:
        calls = _request_times[client_ip]
        while calls and now - calls[0] > RATE_WINDOW_SECONDS:
            calls.popleft()
        if len(calls) >= RATE_LIMIT:
            return True
        calls.append(now)
        return False


def _text(value: object, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


@app.post("/api/generate")
def generate():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return jsonify(error="Gemini is not configured on the server yet."), 503

    client_ip = request.access_route[0] if request.access_route else (request.remote_addr or "unknown")
    if _rate_limit_exceeded(client_ip):
        response = jsonify(error="Too many requests. Wait a minute and try again.")
        response.status_code = 429
        response.headers["Retry-After"] = str(RATE_WINDOW_SECONDS)
        return response

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON request."), 400

    topic = _text(data.get("topic"), 100)
    subject = _text(data.get("subject"), 100) or "General study"
    if not topic:
        return jsonify(error="A topic is required."), 400

    previous = data.get("previousFacts", [])
    if not isinstance(previous, list):
        previous = []
    previous = [_text(item, 300) for item in previous[-5:]]
    if data.get("simplify") is True:
        instruction = "Explain the idea in one simple, memorable sentence for a student. Use plain language."
    else:
        instruction = "Write one accurate and memorable study fact in one or two short sentences for a student. Avoid markdown."

    prompt = (
        "You are a careful study companion. "
        f"Subject: {subject}. Topic: {topic}. {instruction} "
        f"Do not repeat these recent facts: {json.dumps(previous, ensure_ascii=False)}. "
        "Return only the fact."
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 160},
    }).encode("utf-8")
    upstream = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=payload,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )

    try:
        with urlopen(upstream, timeout=30) as result:
            response_data = json.loads(result.read().decode("utf-8"))
        parts = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        fact = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if not fact:
            return jsonify(error="Gemini returned an empty answer."), 502
        return jsonify(fact=fact)
    except HTTPError as error:
        if error.code == 429:
            return jsonify(error="Gemini's free-tier request limit was reached. Try again later."), 429
        if error.code in (400, 401, 403):
            app.logger.warning("Gemini rejected a request with status %s", error.code)
            return jsonify(error="Gemini rejected the request. Check the server API key and model settings."), 502
        app.logger.warning("Gemini returned status %s", error.code)
        return jsonify(error="Gemini could not generate a study fact right now."), 502
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, IndexError, TypeError):
        app.logger.exception("Gemini request failed")
        return jsonify(error="Could not reach Gemini right now."), 502


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="The request is too large."), 413


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    print(f"Smart Study is running at http://127.0.0.1:{port}/login")
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set yet; the app will use sample facts.")
    app.run(host="0.0.0.0", port=port, debug=False)

