#!/usr/bin/env python3
#testing
import json
import os
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

from flask import Flask, jsonify, request, send_from_directory
import psycopg


ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "10000"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "")

app = Flask(__name__, static_folder=str(ROOT), static_url_path="")
DB_READY = False


def db_enabled() -> bool:
    return bool(DATABASE_URL)


def ai_enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)


def apply_cors(resp):
    if ALLOWED_ORIGIN:
        resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.after_request
def after_request(resp):
    return apply_cors(resp)


@app.route("/api/<path:_path>", methods=["OPTIONS"])
def api_options(_path):
    return apply_cors(app.response_class(status=204))


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL)


def init_db():
    global DB_READY
    if not db_enabled():
        return
    schema_path = ROOT / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    DB_READY = True


def ensure_db_ready():
    global DB_READY
    if DB_READY or not db_enabled():
        return
    init_db()


def call_anthropic(prompt: str, max_tokens: int) -> str:
    if not ai_enabled():
        raise RuntimeError("Missing ANTHROPIC_API_KEY environment variable")

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urlrequest.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urlrequest.urlopen(req, timeout=45) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic HTTP {exc.code}: {body}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Network error talking to Anthropic: {exc.reason}") from exc

    return raw.get("content", [{}])[0].get("text", "")


def insert_returning_id(sql: str, params: tuple):
    ensure_db_ready()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            new_id = cur.fetchone()[0]
        conn.commit()
    return new_id


def execute_sql(sql: str, params: tuple):
    ensure_db_ready()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/api/health")
def health():
    db_status = db_enabled()
    if db_enabled():
        try:
            ensure_db_ready()
            db_status = True
        except Exception:
            db_status = False
    return jsonify({
        "ok": True,
        "ai_enabled": ai_enabled(),
        "db_enabled": db_status,
        "build_version": "render"
    })


@app.post("/api/avatar-title")
def api_avatar_title():
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get("prompt") or "").strip()
    max_tokens = int(payload.get("max_tokens") or 80)
    if not prompt:
        return jsonify({"error": "Missing prompt"}), 400
    try:
        text = call_anthropic(prompt, max_tokens)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify({"text": text})


@app.post("/api/personalize-scene")
def api_personalize_scene():
    payload = request.get_json(silent=True) or {}
    prompt = (payload.get("prompt") or "").strip()
    max_tokens = int(payload.get("max_tokens") or 400)
    if not prompt:
        return jsonify({"error": "Missing prompt"}), 400
    try:
        text = call_anthropic(prompt, max_tokens)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    return jsonify({"text": text})


@app.post("/api/profile")
def api_profile():
    if not db_enabled():
        return jsonify({"error": "Database not configured"}), 503
    payload = request.get_json(silent=True) or {}
    survey = payload.get("survey") or {}
    setup = payload.get("setup") or {}
    survey_duration_ms = payload.get("surveyDurationMs")
    profile_id = insert_returning_id(
        """
        INSERT INTO participant_profiles (
          survey_json,
          setup_json,
          age_band,
          education,
          industry,
          occupation,
          player_wfh,
          partner_wfh,
          partner_commute,
          children_status,
          att_father,
          att_stigma,
          att_hours,
          survey_duration_ms,
          build_version
        )
        VALUES (
          %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            json.dumps(survey),
            json.dumps(setup),
            survey.get("age"),
            survey.get("education"),
            survey.get("industry"),
            survey.get("occupation"),
            survey.get("wfh"),
            survey.get("partnerWfh"),
            setup.get("partnerCommute"),
            survey.get("children"),
            survey.get("att_father"),
            survey.get("att_stigma"),
            survey.get("att_hours"),
            survey_duration_ms,
            setup.get("buildVersion"),
        ),
    )
    return jsonify({"profile_id": profile_id})


@app.post("/api/session-start")
def api_session_start():
    if not db_enabled():
        return jsonify({"error": "Database not configured"}), 503
    payload = request.get_json(silent=True) or {}
    session_id = insert_returning_id(
        """
        INSERT INTO play_sessions (
          profile_id,
          scenario_type,
          build_version,
          story_state_json
        )
        VALUES (%s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (
            payload.get("profileId"),
            payload.get("scenarioType"),
            payload.get("buildVersion"),
            json.dumps(payload.get("storyState") or {}),
        ),
    )
    return jsonify({"session_id": session_id})


@app.post("/api/scene-event")
def api_scene_event():
    if not db_enabled():
        return jsonify({"error": "Database not configured"}), 503
    payload = request.get_json(silent=True) or {}
    event_id = insert_returning_id(
        """
        INSERT INTO scene_events (
          session_id,
          scenario_type,
          scene_id,
          choice_id,
          response_time_ms,
          scene_shown_at,
          choice_submitted_at,
          meters_before_json,
          meters_after_json,
          story_state_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
        RETURNING id
        """,
        (
            payload.get("sessionId"),
            payload.get("scenarioType"),
            payload.get("sceneId"),
            payload.get("choiceId"),
            payload.get("responseTimeMs"),
            payload.get("sceneShownAt"),
            payload.get("choiceSubmittedAt"),
            json.dumps(payload.get("metersBefore") or {}),
            json.dumps(payload.get("metersAfter") or {}),
            json.dumps(payload.get("storyState") or {}),
        ),
    )
    return jsonify({"event_id": event_id})


@app.post("/api/session-end")
def api_session_end():
    if not db_enabled():
        return jsonify({"error": "Database not configured"}), 503
    payload = request.get_json(silent=True) or {}
    execute_sql(
        """
        UPDATE play_sessions
        SET ended_at = NOW(),
            ending_id = %s,
            ending_title = %s,
            failed = %s,
            final_meters_json = %s::jsonb,
            story_state_json = %s::jsonb,
            choices_json = %s::jsonb,
            meter_history_json = %s::jsonb
        WHERE id = %s
        """,
        (
            payload.get("endingId"),
            payload.get("endingTitle"),
            payload.get("failed"),
            json.dumps(payload.get("finalMeters") or {}),
            json.dumps(payload.get("storyState") or {}),
            json.dumps(payload.get("choices") or []),
            json.dumps(payload.get("meterHistory") or []),
            payload.get("sessionId"),
        ),
    )
    return jsonify({"ok": True})


@app.post("/api/post-survey")
def api_post_survey():
    if not db_enabled():
        return jsonify({"error": "Database not configured"}), 503
    payload = request.get_json(silent=True) or {}
    execute_sql(
        """
        INSERT INTO post_surveys (session_id, post_survey_json)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (session_id)
        DO UPDATE SET post_survey_json = EXCLUDED.post_survey_json,
                      submitted_at = NOW()
        """,
        (
            payload.get("sessionId"),
            json.dumps(payload.get("postSurvey") or {}),
        ),
    )
    return jsonify({"ok": True})


@app.get("/<path:path>")
def static_files(path):
    target = ROOT / path
    if target.exists() and target.is_file():
        return send_from_directory(ROOT, path)
    return send_from_directory(ROOT, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
