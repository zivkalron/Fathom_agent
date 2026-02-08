"""
Fathom webhook endpoint for Vercel serverless.

Receives the `new-meeting-content-ready` event, verifies the HMAC signature,
normalizes the payload into the transcript JSON format the existing tools expect,
then runs summarize_with_gemini.py and log_to_airtable.py as subprocesses.

fetch_fathom_transcript.py is skipped — the webhook payload already contains
the full transcript.

Signature verification uses stdlib only (hmac, hashlib, base64).

Environment variables (set in Vercel dashboard):
    FATHOM_WEBHOOK_SECRET   — the whsec_... value from webhook registration
    GOOGLE_GEMINI_API_KEY   — forwarded to subprocess
    AIRTABLE_API_KEY        — forwarded to subprocess
    AIRTABLE_BASE_ID        — forwarded to subprocess
    AIRTABLE_MEETINGS_TABLE — optional, defaults to "Meetings"
    AIRTABLE_TASKS_TABLE    — optional, defaults to "Tasks"
"""

import hmac
import hashlib
import base64
import json
import os
import sys
import time
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# tools/ is a sibling of api/ at the project root.
# __file__ = api/webhook.py  →  .parent = api/  →  .parent.parent = project root
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"

# Vercel's writable filesystem. We nest .tmp inside /tmp so that
# Path(".tmp") in the tool scripts resolves correctly when cwd="/tmp".
TMP_DIR = Path("/tmp/.tmp")

TIMESTAMP_TOLERANCE = 300  # 5 minutes


# ---------------------------------------------------------------------------
# SIGNATURE VERIFICATION
# ---------------------------------------------------------------------------
# Fathom uses the standard-webhooks (svix) signing convention:
#   signed_content = "{webhook-id}.{webhook-timestamp}.{raw_body}"
#   secret_bytes   = base64.b64decode( secret.removeprefix("whsec_") )
#   expected_sig   = base64.b64encode( HMAC-SHA256(secret_bytes, signed_content) )
#   webhook-signature header: space-separated "v1,{sig}" entries
# ---------------------------------------------------------------------------


def verify_signature(raw_body: bytes, headers: dict) -> bool:
    """Verify the Fathom webhook HMAC-SHA256 signature. Never raises."""
    secret_raw = os.environ.get("FATHOM_WEBHOOK_SECRET", "")
    if not secret_raw:
        print("ERROR: FATHOM_WEBHOOK_SECRET not set", file=sys.stderr)
        return False

    msg_id        = headers.get("webhook-id", "")
    msg_timestamp = headers.get("webhook-timestamp", "")
    msg_signature = headers.get("webhook-signature", "")

    if not all([msg_id, msg_timestamp, msg_signature]):
        print("ERROR: Missing required signature headers", file=sys.stderr)
        return False

    # --- Timestamp freshness — reject replays older than 5 min ---
    try:
        ts = int(msg_timestamp)
    except ValueError:
        print("ERROR: webhook-timestamp is not an integer", file=sys.stderr)
        return False

    if abs(int(time.time()) - ts) > TIMESTAMP_TOLERANCE:
        print(f"ERROR: Timestamp {ts} outside {TIMESTAMP_TOLERANCE}s tolerance", file=sys.stderr)
        return False

    # --- Decode secret (strip whsec_ prefix, base64-decode) ---
    try:
        secret_bytes = base64.b64decode(secret_raw.removeprefix("whsec_"))
    except Exception as e:
        print(f"ERROR: Failed to decode webhook secret: {e}", file=sys.stderr)
        return False

    # --- Compute expected signature ---
    signed_content = f"{msg_id}.{msg_timestamp}.{raw_body.decode('utf-8')}"
    expected = base64.b64encode(
        hmac.new(secret_bytes, signed_content.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    # --- Compare against each v1 signature in the header ---
    # Multiple entries are space-separated; multiple may exist during secret rotation.
    for entry in msg_signature.split(" "):
        parts = entry.split(",", 1)  # split on first comma only
        if len(parts) == 2 and parts[0] == "v1":
            if hmac.compare_digest(expected, parts[1]):
                return True

    print("ERROR: No matching v1 signature found", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# PAYLOAD NORMALIZATION
# ---------------------------------------------------------------------------
# Webhook field  →  transcript file field (what the tools read)
#   meeting_title   →  title
#   created_at      →  date
#   url             →  (used to extract recording_id)
#   transcript      →  transcript   (kept verbatim — nested speaker objects
#                                     are required by format_attendees)
#   (derived)       →  participants (deduplicated display_name list, used by
#                                     format_transcript_for_gemini for the
#                                     PARTICIPANTS header in the Gemini prompt)
# ---------------------------------------------------------------------------


def extract_recording_id(payload: dict) -> str:
    """
    Parse recording_id from the payload's url field.
    URL formats:
      - https://app.fathom.video/recordings/{recording_id}
      - https://fathom.video/calls/{call_id}
    Fallback: epoch timestamp (unique enough for single-user cadence).
    """
    url = payload.get("url", "")
    if url:
        segments = urlparse(url).path.strip("/").split("/")
        # Handle both /recordings/{id} and /calls/{id} formats
        if len(segments) >= 2 and segments[-2] in ("recordings", "calls") and segments[-1]:
            print(f"Extracted recording_id: {segments[-1]}")
            return segments[-1]

    fallback = str(int(time.time()))
    print(f"WARNING: Could not parse recording_id from url '{url}', using fallback: {fallback}", file=sys.stderr)
    return fallback


def normalize_payload(payload: dict) -> tuple:
    """
    Map webhook payload → transcript JSON shape the existing tools consume.
    Returns (normalized_dict, recording_id).
    """
    recording_id = extract_recording_id(payload)
    transcript   = payload.get("transcript", [])

    # Deduplicate speaker names for the Gemini prompt PARTICIPANTS header
    seen        = set()
    participants = []
    for seg in transcript:
        speaker = seg.get("speaker", {})
        name = speaker.get("display_name", "Unknown") if isinstance(speaker, dict) else str(speaker)
        if name not in seen:
            seen.add(name)
            participants.append(name)

    normalized = {
        "title":        payload.get("meeting_title", "Untitled Meeting"),
        "date":         payload.get("created_at", ""),
        "participants": participants,
        "transcript":   transcript,   # verbatim — nested speaker objects intact
    }
    return normalized, recording_id


# ---------------------------------------------------------------------------
# SUBPROCESS ORCHESTRATION
# ---------------------------------------------------------------------------
# Both tools run with cwd="/tmp" so their internal Path(".tmp") resolves to
# /tmp/.tmp/.  All file arguments are absolute paths.
# ---------------------------------------------------------------------------


def run_step(label: str, cmd: list, env: dict) -> None:
    """Run a subprocess step. Raises subprocess.CalledProcessError on failure."""
    print(f"--- {label} ---")
    print(f"  cmd: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd="/tmp",           # Path(".tmp") in tools → /tmp/.tmp/
        env=env,
        capture_output=True,
        text=True,
        timeout=270,          # margin under Vercel's 300s hard kill
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr
        )


def run_pipeline(recording_id: str, transcript_path: str) -> None:
    """Execute summarize → log_to_airtable."""
    env = os.environ.copy()

    # Fail fast on missing env vars before spawning subprocesses
    for var in ("GOOGLE_GEMINI_API_KEY", "AIRTABLE_API_KEY", "AIRTABLE_BASE_ID"):
        if not env.get(var):
            raise EnvironmentError(f"Required env var {var} is not set")

    summary_path = f"/tmp/.tmp/summary_{recording_id}.json"

    # Step 1: Summarize with Gemini (Hebrew summary + action items)
    run_step("summarize_with_gemini", [
        sys.executable,
        str(TOOLS_DIR / "summarize_with_gemini.py"),
        transcript_path,
    ], env)

    # Verify output exists before proceeding
    if not Path(summary_path).exists():
        raise FileNotFoundError(f"Summary file not produced at {summary_path}")

    # Step 2: Log meeting + tasks to Airtable
    run_step("log_to_airtable", [
        sys.executable,
        str(TOOLS_DIR / "log_to_airtable.py"),
        summary_path,
        transcript_path,
    ], env)


# ---------------------------------------------------------------------------
# HTTP HANDLER
# ---------------------------------------------------------------------------
# Vercel Python serverless: the class MUST be named `handler` and extend
# BaseHTTPRequestHandler.  Vercel auto-discovers it by name.
# ---------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Health-check endpoint — useful to verify the deployment is live."""
        self._json(200, {"status": "ok"})

    def do_POST(self):
        # --- Read raw body BEFORE parsing (required for signature verification) ---
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._json(400, {"error": "Empty body"})
            return
        raw_body = self.rfile.read(length)

        # --- Verify HMAC signature ---
        sig_headers = {
            "webhook-id":        self.headers.get("webhook-id", ""),
            "webhook-timestamp": self.headers.get("webhook-timestamp", ""),
            "webhook-signature": self.headers.get("webhook-signature", ""),
        }
        if not verify_signature(raw_body, sig_headers):
            self._json(401, {"error": "Invalid signature"})
            return

        # --- Parse JSON ---
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as e:
            print(f"ERROR: Malformed JSON: {e}", file=sys.stderr)
            self._json(400, {"error": "Malformed JSON"})
            return

        # --- Normalize and extract recording_id ---
        normalized, recording_id = normalize_payload(payload)
        print(f"Processing: title='{normalized['title']}' recording_id='{recording_id}'")

        # --- Ensure /tmp/.tmp/ exists ---
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        # --- Save normalized transcript to disk ---
        transcript_path = str(TMP_DIR / f"transcript_{recording_id}.json")
        try:
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2, ensure_ascii=False)
            print(f"Saved transcript → {transcript_path}")
        except Exception as e:
            print(f"ERROR: Failed to write transcript: {e}", file=sys.stderr)
            self._json(500, {"error": "Failed to save transcript"})
            return

        # --- Run the pipeline (summarize → log) ---
        try:
            run_pipeline(recording_id, transcript_path)

        except EnvironmentError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            self._json(500, {"error": str(e)})
            return
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            self._json(500, {"error": str(e)})
            return
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Pipeline step failed (exit {e.returncode})", file=sys.stderr)
            self._json(500, {"error": f"Pipeline step failed: {e.stderr}"})
            return
        except subprocess.TimeoutExpired:
            print("ERROR: Subprocess timed out", file=sys.stderr)
            self._json(504, {"error": "Processing timed out"})
            return
        except Exception as e:
            print(f"ERROR: Unexpected: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self._json(500, {"error": "Unexpected error"})
            return

        # --- 200 only on full success (non-2xx triggers Fathom retry) ---
        self._json(200, {
            "status":       "ok",
            "recording_id": recording_id,
            "title":        normalized["title"],
        })

    # --- helpers ---

    def _json(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def log_message(self, format, *args):
        # Suppress BaseHTTPRequestHandler's default stderr noise;
        # we log explicitly via print() which Vercel captures.
        pass
