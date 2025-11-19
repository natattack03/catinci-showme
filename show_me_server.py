"""
show_me_server.py — Catinci "Show Me" Feature
---------------------------------------------
Implements:
  - /answer  : main Q&A endpoint. LLM returns spoken text + topic + visual queries
  - /show_me : sends SMS with Google Images + YouTube links (NO landing page)

The voice agent will:
  - read back `spoken` from /answer
  - read back `spoken` from /show_me

This MVP uses:
  - Flask
  - Gemini (via google.generativeai)
  - Twilio for SMS
  - In-memory session store per user

Everything is intentionally minimal and kid-safe.
"""

import os
import re
from datetime import datetime
from urllib.parse import urlencode

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from twilio.rest import Client
import google.generativeai as genai


# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

load_dotenv()

app = Flask(__name__)
CORS(app)

# Environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("⚠️ WARNING: GEMINI_API_KEY not set.")

# In-memory user state:
# SESSIONS[user_id] = {
#   "current_topic": "...",
#   "image_query": "...",
#   "video_query": "...",
#   "last_question": "...",
#   "updated_at": <datetime>
# }
SESSIONS = {}


# -------------------------------------------------------------------
# Helper functions
# -------------------------------------------------------------------

SHOW_TRIGGERS = [
    r"\bshow me\b",
    r"\bshow us\b",
    r"\bcan you show\b",
    r"\blet me see\b",
    r"\blet us see\b",
    r"\bsend (me|us) pictures\b",
    r"\bwhat does that look like\b",
]


def is_show_request(text: str) -> bool:
    """Detects if user says something like 'show us' / 'show me'."""
    if not text:
        return False
    t = text.lower()
    return any(re.search(p, t) for p in SHOW_TRIGGERS)


def extract_topic_from_utterance(text: str):
    """
    Detect patterns like:
      'show me stars in iceland'
      'can you show us whale belly buttons'
    Returns the extracted topic (str) or None.
    """
    if not text:
        return None

    t = text.lower().strip()

    m = re.search(r"can you show (me|us)\s+(.+)", t)
    if m:
        return m.group(2).strip(" ?.!,")
    
    m = re.search(r"show (me|us)\s+(.+)", t)
    if m:
        return m.group(2).strip(" ?.!,")
    
    return None


def google_images_url(query: str) -> str:
    return "https://www.google.com/search?tbm=isch&q=" + urlencode({"": query})[1:]


def youtube_url(query: str) -> str:
    return "https://www.youtube.com/results?search_query=" + urlencode({"": query})[1:]


def ensure_kid_friendly_image_query(query: str) -> str:
    """
    Force image searches to carry a kid-friendly marker in the text.
    """
    q = (query or "").strip()
    if not q:
        return "kid friendly images for kids"

    lower = q.lower()
    if "kid friendly" not in lower and "for kids" not in lower:
        q = f"kid friendly {q}"
    return q


def ensure_kid_friendly_video_query(query: str) -> str:
    """
    Force video searches to clearly indicate they are for kids.
    """
    q = (query or "").strip()
    if not q:
        return "fun educational videos for kids"

    lower = q.lower()
    if "for kids" not in lower and "kid friendly" not in lower:
        q = f"{q} for kids"
    return q


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


def call_gemini(question: str, forced_topic: str = None) -> str:
    """
    Call the LLM to generate:
      - spoken answer
      - [TOPIC: ...]
      - [IMAGE_QUERY: ...]
      - [VIDEO_QUERY: ...]
    """

    base_prompt = """
You are Catinci, a friendly kid-safe tutor.

Instructions:
1. Answer the child warmly in a short spoken paragraph.
2. Identify a clear simple TOPIC (like "whale belly buttons").
3. Generate safe, kid-friendly queries for images + videos.
4. Video queries will be searched on normal YouTube (not YouTube Kids) so always include "for kids" or "kid friendly" in the video query text.

Your answer must end with EXACTLY:

[TOPIC: <topic>]
[IMAGE_QUERY: <image search query>]
[VIDEO_QUERY: <video search query>]

Query rules:
- Use simple kid-friendly phrases ("for kids", "kid friendly").
- Avoid scary, violent, graphic terms.
"""

    if forced_topic:
        hint = f"\nThe child/parent explicitly requested visuals for this topic: {forced_topic}\n"
    else:
        hint = ""

    full_prompt = f"""{base_prompt}
User said: "{question}"
{hint}
Now provide spoken answer + the 3 required tag lines.
"""

    model = genai.GenerativeModel("models/gemini-2.5-flash")
    response = model.generate_content(full_prompt)
    return response.text or ""


def parse_llm_output(raw: str):
    """
    Extract:
      - spoken (everything before tags)
      - topic
      - image_query
      - video_query
    """
    t = raw or ""

    topic = re.search(r"\[TOPIC:(.*?)\]", t, re.IGNORECASE | re.DOTALL)
    image_q = re.search(r"\[IMAGE_QUERY:(.*?)\]", t, re.IGNORECASE | re.DOTALL)
    video_q = re.search(r"\[VIDEO_QUERY:(.*?)\]", t, re.IGNORECASE | re.DOTALL)

    topic = topic.group(1).strip() if topic else None
    image_q = image_q.group(1).strip() if image_q else None
    video_q = video_q.group(1).strip() if video_q else None

    # spoken = everything before first tag
    first_tag = len(t)
    for m in (topic, image_q, video_q):
        if isinstance(m, str):  # skip
            continue
    for tag in ["[TOPIC:", "[IMAGE_QUERY:", "[VIDEO_QUERY:"]:
        pos = t.find(tag)
        if pos != -1:
            first_tag = min(first_tag, pos)

    spoken = t[:first_tag].strip()

    return spoken, topic, image_q, video_q


# -------------------------------------------------------------------
# /answer — main Q&A endpoint
# -------------------------------------------------------------------

@app.route("/answer", methods=["POST"])
def answer():
    """
    JSON:
    {
      "user_id": "...",
      "text": "Why do whales have belly buttons?"
    }
    """
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id", "anonymous")
    text = (data.get("text") or "").strip()

    print(f"🧒 /answer from {user_id}: {text}")

    # If user's question *is a show request* ("can you show me whales?")
    forced_topic = extract_topic_from_utterance(text)

    try:
        raw = call_gemini(text, forced_topic=forced_topic)
        spoken, topic, image_q, video_q = parse_llm_output(raw)

        # fallback logic
        topic = topic or forced_topic or text[:50]
        image_q = ensure_kid_friendly_image_query(image_q or topic)
        video_q = ensure_kid_friendly_video_query(video_q or f"{topic} videos")

        # store session state
        SESSIONS[user_id] = {
            "current_topic": topic,
            "image_query": image_q,
            "video_query": video_q,
            "last_question": text,
            "updated_at": datetime.utcnow(),
        }

        return jsonify({
            "spoken": spoken,
            "topic": topic,
            "image_query": image_q,
            "video_query": video_q,
        })

    except Exception as e:
        print("❌ Error in /answer:", e)
        return jsonify({"spoken": "I’m having a little trouble thinking right now."})


# -------------------------------------------------------------------
# /show_me — send SMS with direct links (NO landing page)
# -------------------------------------------------------------------

@app.route("/show_me", methods=["POST"])
def show_me():
    """
    JSON:
    {
       "user_id": "...",
       "text": "can you show us?",
       "parent_phone": "+1555...."
    }
    """
    data = request.get_json(force=True) or {}
    user_id = data.get("user_id", "anonymous")
    text = (data.get("text") or "").strip()
    parent_phone = (data.get("parent_phone") or "").strip()

    print(f"📸 /show_me from {user_id}: {text}")

    if not is_show_request(text):
        return jsonify({"spoken": "If you'd like pictures or videos, just say 'show us'!"})

    session = SESSIONS.get(user_id, {})

    # detect if user said "show me whales" directly
    utter_topic = extract_topic_from_utterance(text)

    if utter_topic:
        topic = utter_topic
        image_q = ensure_kid_friendly_image_query(topic)
        video_q = ensure_kid_friendly_video_query(f"{topic} videos")
    else:
        topic = session.get("current_topic") or "what we were talking about"
        image_q = ensure_kid_friendly_image_query(session.get("image_query") or topic)
        video_q = ensure_kid_friendly_video_query(session.get("video_query") or f"{topic} videos")

    # build links
    image_url = google_images_url(image_q)
    video_url = youtube_url(video_q)

    # send SMS
    if parent_phone:
        emoji = "🌋" if "volcano" in topic.lower() else "🌟"
        sms = (
            f"Here are kid-friendly pictures and videos about {topic}!\n"
            f"Images: {image_url}\n\n"
            f"Videos: {video_url}\n\n"
            "- Catinci AI 🌟"
        )
        send_sms(parent_phone, sms)
    else:
        print("⚠️ No parent_phone provided; skipping SMS.")

    spoken = (
        f"Sure! I found kid-friendly pictures and videos about {topic}. "
        "I sent them to your grown-up!"
    )

    return jsonify({
        "spoken": spoken,
        "image_url": image_url,
        "video_url": video_url
    })


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
