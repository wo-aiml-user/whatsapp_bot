from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import logging
import uvicorn
load_dotenv('config.env')

from auth.security import verify_webhook_token
from .whatsapp_client import (
    send_text_message,
    handle_webhook_event,
    store_inbound_messages,
    fetch_latest_messages,
    fetch_messages_by_number,
    WhatsAppAPIError,
)


app = FastAPI(title="WhatsApp API", version="1.0.0")

# Basic structured logging
logger = logging.getLogger("api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class SendRequest(BaseModel):
    number: str
    text: str

class GetRequest(BaseModel):
    number: str
    limit: int = 0


@app.post("/send")
async def send_endpoint(body: SendRequest) -> Dict[str, Any]:
    try:
        logger.info("api.send start to=%s", body.number)
        resp = send_text_message(body.number, body.text)
        logger.info("api.send success")
        return {"success": True, "response": resp}
    except WhatsAppAPIError as e:
        logger.error("api.send error=%s", str(e))
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/get")
async def get_endpoint(body: GetRequest) -> Dict[str, Any]:
    logger.info("api.get start number=%s limit=%s", body.number, body.limit)
    items = fetch_messages_by_number(body.number, max(0, body.limit))
    logger.info("api.get success number=%s count=%s", body.number, len(items))
    return {"count": len(items), "messages": items}


@app.get("/webhook")
async def webhook_verify(mode: Optional[str] = Query(None, alias="hub.mode"),
                        token: Optional[str] = Query(None, alias="hub.verify_token"),
                        challenge: Optional[str] = Query(None, alias="hub.challenge")):
    if verify_webhook_token(mode, token):
        return PlainTextResponse(content=challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/webhook")
async def webhook_receive(request: Request):
    payload = await request.json()
    logger.info("api.webhook receive start")
    msgs = handle_webhook_event(payload)
    stored = store_inbound_messages(msgs)
    logger.info("api.webhook receive done received=%s stored=%s", len(msgs), stored)
    return JSONResponse({"received": len(msgs), "stored": stored})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


