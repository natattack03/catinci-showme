"""
show_me_server.py — Catinci "Show Me" Tool Endpoint
---------------------------------------------------
Implements:
  - /show_me : stores the child's last request as the topic and sends SMS

The voice agent will:
  - read back `spoken` from /show_me

This MVP uses:
  - Flask
  - Twilio for SMS
  - In-memory session store per parent phone number

Everything is intentionally minimal and kid-safe.
"""

import os
from urllib.parse import quote

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from twilio.rest import Client


# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

load_dotenv()

app = Flask(__name__)
CORS(app)

# Environment variables
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")

# In-memory user state:
# SESSIONS = {
#    "+15551234567": {
#        "topic": "last user question or statement"
#    }
# }
SESSIONS = {}


# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------

def send_sms(to_number: str, message: str):
    """Send SMS via Twilio (or print if not configured)."""
    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        print("⚠️ Twilio not configured. Would send to:", to_number)
        print("--- SMS BODY ---")
        print(message)
        print("---------------")
        return

    client = Client(TWILIO_SID, TWILIO_TOKEN)
    client.messages.create(
        to=to_number,
        from_=TWILIO_FROM,
        body=message,
    )


# -------------------------------------------------------------------
# /show_me — send SMS with direct links (NO landing page)
# -------------------------------------------------------------------

@app.route("/show_me", methods=["POST"])
def show_me():
    """
    JSON:
    {
        "text": "can you show us?",
        "parent_phone": "+1555...."
    }
    """
    data = request.get_json(force=True) or {}
    raw_text = (data.get("text") or "").strip()
    text = raw_text.lower()
    parent_phone = (data.get("parent_phone") or "").strip()

    if not parent_phone:
        return jsonify({
            "spoken": "I need your grown-up's phone number first!"
        }), 200

    session_key = parent_phone
    session = SESSIONS.get(session_key, {})

    print(f"📸 /show_me for {session_key}: {raw_text}")

    show_me_triggered = any(
        key in text for key in ["show me", "show us", "can you show", "please show"]
    )

    if not show_me_triggered:
        SESSIONS[session_key] = {"topic": data.get("text", "")}
        return jsonify({"spoken": None}), 200

    topic = session.get("topic")
    if not topic:
        return jsonify({
            "spoken": "Ask me something first so I know what to show!"
        }), 200

    image_url = "https://www.google.com/search?tbm=isch&q=" + quote(f"{topic} for kids")
    video_url = "https://www.youtube.com/results?search_query=" + quote(f"{topic} for kids video")

    sms_body = (
        f"Here are kid-friendly pictures and videos about {topic}! 🌟\n\n"
        f"Images:\n{image_url}\n\n"
        f"Videos:\n{video_url}\n\n"
        f"- Catinci AI 🐾"
    )
    send_sms(parent_phone, sms_body)

    return jsonify({
        "spoken": f"I sent pictures and videos about {topic} to your grown-up!"
    }), 200


# -------------------------------------------------------------------
# health
# -------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}, 200


# -------------------------------------------------------------------
# run
# -------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
