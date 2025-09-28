from fastapi import FastAPI, Request, Response, BackgroundTasks
import os, logging, json
from dotenv import load_dotenv

import hashlib, pathlib, time

EVENT_LOG = pathlib.Path(".data/finnhub_events.jsonl")
EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)

_recent = set()         
_RECENT_TTL = 3600      
_seen_at = {}          

def _dedupe(body: bytes) -> bool:
    h = hashlib.sha256(body).hexdigest()
    now = time.time()

    if len(_recent) > 5000:
        stale = [k for k,t in _seen_at.items() if now - t > _RECENT_TTL]
        for k in stale:
            _recent.discard(k)
            _seen_at.pop(k, None)
    if h in _recent:
        return True
    _recent.add(h)
    _seen_at[h] = now
    return False

def _append_jsonl(payload: dict) -> None:
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")

def process_event(body_bytes: bytes):
    try:
        if _dedupe(body_bytes):
            logging.info("Finnhub event duplicate; skipped")
            return
        evt = json.loads(body_bytes.decode("utf-8") or "{}")
        _append_jsonl(evt) 


        etype = (evt.get("type") or evt.get("event") or "").lower()
        if etype:
            logging.info("Finnhub event type=%s", etype)
        else:
            logging.info("Finnhub event received (no 'type' field)")


    except Exception:
        logging.exception("Finnhub webhook processing failed")

load_dotenv()  
app = FastAPI()

SECRET = os.getenv("FINNHUB_WEBHOOK_SECRET", "")  

def process_event(body_bytes: bytes):
    """Do your real work here (enqueue, log, update DB, etc.)."""
    try:
        evt = json.loads(body_bytes.decode("utf-8") or "{}")

        logging.info("Finnhub event processed: %s", evt.get("type") or evt.keys())
    except Exception:
        logging.exception("Finnhub webhook processing failed")

@app.post("/webhook/finnhub")
async def finnhub_webhook(req: Request, bg: BackgroundTasks):

    header_secret = req.headers.get("x-finnhub-secret", "")
    if SECRET and header_secret != SECRET:

        return Response(status_code=401)

    body = await req.body()
    bg.add_task(process_event, body)
    return Response(status_code=204)  