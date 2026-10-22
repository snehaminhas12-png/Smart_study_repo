"""Smart Study News App: Flask web server and Gemini API proxy."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request, send_from_directory

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


@app.get("/api/health")
def health():
    return jsonify(ok=True, configured=bool(os.environ.get("GEMINI_API_KEY")))


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

