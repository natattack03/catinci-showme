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
# We keep this dict to reuse the last topic per parent when the child says "show me".
SESSIONS = {}


# -------------------------------------------------------------------
# Helper constants
# -------------------------------------------------------------------

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
    data = request.get_json(force=True) or {}
    text_raw = data.get("text", "") or ""
    text = text_raw.strip()
    lower_text = text.lower()
    parent_phone = (data.get("parent_phone") or "").strip()

    SHOW_ME_PHRASES = [
        "show me",
        "show us",
        "can you show",
        "can u show",
        "please show",
        "show it",
        "can i see",
        "can we see",
        "let me see",
        "i want to see",
        "i wanna see",
        "show the pictures",
        "show the picture",
        "show the video",
        "show me the pictures",
        "show me the video",
    ]

    def is_show_me_like(s: str) -> bool:
        s = s.strip().lower()
        if not s:
            return False
        for phrase in SHOW_ME_PHRASES:
            if phrase in s:
                return True
        return "show" in s and ("me" in s or "us" in s)

    if not parent_phone:
        return jsonify({
            "spoken": "I couldn't find a phone number for your grown-up."
        }), 200

    if not text:
        return jsonify({
            "spoken": "Can you tell me what you want to see first, little explorer?"
        }), 200

    session = SESSIONS.get(parent_phone, {})

    if is_show_me_like(text):
        topic = (session.get("topic") or text).strip()
    else:
        topic = text
        if topic:
            SESSIONS[parent_phone] = {"topic": topic}

    safe_topic = sanitize_topic_for_search(topic)
    image_query = f"{safe_topic} explained for kids diagram cartoon"
    video_query = f"{safe_topic} video for kids learning"

    image_url = (
        "https://www.google.com/search?tbm=isch&safe=active&q=" + quote(image_query)
    )
    video_url = (
        "https://www.youtube.com/results?search_query=" + quote(video_query)
    )

    quoted_topic = f"\"{topic}\""
    sms_body = (
        f"📸 Here are kid-friendly pictures and videos about {quoted_topic}!\n\n"
        f"🖼️ Images:\n{image_url}\n\n"
        f"🎥 Videos:\n{video_url}\n\n"
        f"— Catinci AI 🐾"
    )

    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            to=parent_phone,
            from_=TWILIO_FROM,
            body=sms_body,
        )
    except Exception as e:
        print(f"[SHOW_ME] Twilio SMS error: {e}")

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
