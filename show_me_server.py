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
# Helper constants
# -------------------------------------------------------------------

SHOW_ME_PHRASES = [
    "show me",
    "show us",
    "can you show",
    "can u show",
    "please show",
    "show it",
    "i want to see",
    "let me see",
    "i wanna see",
    "can i see",
    "show the pictures",
    "show the picture",
    "show the video",
    "show me the pictures",
    "show me the video",
]

# Very simple keyword filter to avoid obviously gory/scary queries.
BLOCKED_KEYWORDS = [
    "graphic",
    "gore",
    "injury",
    "blood",
    "surgery",
    "open heart",
    "open brain",
    "amputation",
    "dead body",
    "corpse",
    "autopsy",
    "morgue",
    "crime scene",
]


def sanitize_topic_for_search(topic: str) -> str:
    """
    Take the raw topic string (usually the kid's last question) and
    remove obviously problematic words before building search queries.
    If everything gets stripped and the topic would become empty, fall
    back to a generic kid-safe query.
    """
    if not topic:
        return "science facts for kids"

    # Split into words and drop any that contain blocked substrings
    safe_words = []
    for word in topic.split():
        w_lower = word.lower()
        if any(bad in w_lower for bad in BLOCKED_KEYWORDS):
            continue
        safe_words.append(word)

    safe_topic = " ".join(safe_words).strip()

    if not safe_topic:
        # Fallback if we stripped everything
        safe_topic = "science facts for kids"

    return safe_topic


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

    show_me_triggered = any(phrase in text for phrase in SHOW_ME_PHRASES)

    if not show_me_triggered:
        SESSIONS[session_key] = {"topic": data.get("text", "")}
        return jsonify({"spoken": None}), 200

    topic = session.get("topic", "").strip()
    if not topic:
        return jsonify({
            "spoken": "Ask me something first so I know what to show!"
        }), 200

    quoted_topic = f"\"{topic}\""

    # Sanitize the topic for search, but keep the original topic for spoken text.
    safe_topic = sanitize_topic_for_search(topic)

    # Opinionated, kid-focused query templates
    image_query = f"{safe_topic} explained for kids diagram cartoon"
    video_query = f"{safe_topic} video for kids learning"

    # Google Images with SafeSearch enabled
    image_url = (
        "https://www.google.com/search?tbm=isch&safe=active&q=" + quote(image_query)
    )

    # YouTube search; no explicit safe parameter, rely on the kid-focused query
    video_url = (
        "https://www.youtube.com/results?search_query=" + quote(video_query)
    )

    sms_body = (
        f"📸 Here are kid-friendly pictures and videos about {quoted_topic}!\n\n"
        f"🖼️ Images:\n{image_url}\n\n"
        f"🎥 Videos:\n{video_url}\n\n"
        f"— Catinci AI 🐾"
    )

    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        print("⚠️ Twilio not configured. Would send to:", parent_phone)
        print("--- SMS BODY ---")
        print(sms_body)
        print("---------------")
    else:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            to=parent_phone,
            from_=TWILIO_FROM,
            body=sms_body,
        )

    return jsonify({
        "spoken": f"I sent pictures and videos about {quoted_topic} to your grown-up!"
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
