# Catinci “Show Me” Tool
Voice-first “show me” feature for the Catinci kid-friendly assistant. Kids ask for pictures/videos; the service remembers the topic per parent and sends kid-safe search links to the parent via SMS. Built with Flask + Twilio. No database.
## What it does
- Stores the latest topic per `parent_phone`.
- If the child later says “show me” (or similar), it reuses the stored topic and sends SMS with Google Images and YouTube search links.
- Filters obvious gore/scary terms before building search queries; falls back to a generic kid-safe query if needed.
- Returns a short `spoken` string for the voice agent to read verbatim.
## API
### POST `/show_me`
**Body (JSON):**
```json
{
  "text": "<child utterance>",
  "parent_phone": "+15551234567"
}
```
**Behavior:**
- If `text` matches a “show me” phrase, it uses the last stored topic for that parent and sends SMS links.
- Otherwise, it stores `text` as the topic for that parent and returns `{"spoken": null}` (no SMS yet).
- If `parent_phone` is missing, returns a friendly error.
**Responses (JSON):**
- SMS sent: `{"spoken": "I sent pictures and videos about \"<topic>\" to your grown-up!"}`
- Need topic: `{"spoken": "Can you tell me what you want to see first, little explorer?"}`
- Missing phone: `{"spoken": "I couldn't find a phone number for your grown-up."}`
### GET `/health`
`{"status": "ok"}`
## Safety/filtering
- “Show me” detection covers common variants (e.g., “show me,” “let me see,” “show the pictures”).
- Blocklist drops obvious gore/graphic terms before building search URLs.
- If all words are removed, falls back to `science facts for kids`.
## Notes on voice-agent behavior
- Local curl tests hit `/show_me` correctly and the stored topic/SMS flow works as expected.
- In live voice-agent tests, the agent has occasionally hallucinated or rewrote the child’s request before calling the tool. Example: the child said “show me volcano pictures,” but the agent sent `text: "show me unicorn pictures"` to `/show_me`, so the parent received unicorn links. Still trying to find a foolproof solution!!!!
## Environment
Create a `.env` (or set env vars) with:
- `TWILIO_SID`
- `TWILIO_TOKEN`
- `TWILIO_FROM` (Twilio phone number, E.164)
## Install & Run (local)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python show_me_server.py  # uses PORT or defaults to 5002
```
## Example calls
Store a topic (no SMS yet):
```bash
curl -X POST http://127.0.0.1:5002/show_me \
  -H "Content-Type: application/json" \
  -d '{"text":"I want to see volcano pictures","parent_phone":"+15551234567"}'
```
Trigger send using prior topic:
```bash
curl -X POST http://127.0.0.1:5002/show_me \
  -H "Content-Type: application/json" \
  -d '{"text":"show me","parent_phone":"+15551234567"}'
```
## ElevenLabs integration notes
- Tool name suggestion: `show_me`.
- Pass `text` (child utterance) and `parent_phone` to `/show_me`.
- The agent should speak the `spoken` field verbatim; if `spoken` is null, the agent stays quiet.
## Project structure
- `show_me_server.py` — Flask app, Twilio SMS send, in-memory session state.
- `requirements.txt` — dependencies.
- `README.md` — this doc.
