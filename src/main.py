from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import logging
import uvicorn
load_dotenv('.env')

from utils.security import verify_webhook_token
from utils.chat import generate_response, auto_respond_to_message
from .whatsapp_client import (
    send_text_message,
    send_template_message,
    handle_webhook_event,
    store_inbound_messages,
    fetch_messages_by_number,
    WhatsAppAPIError,
)


app = FastAPI(title="WhatsApp API", version="1.0.0")

logger = logging.getLogger("api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class GetRequest(BaseModel):
    number: str
    limit: int = 0


class BulkGetRequest(BaseModel):
    numbers: List[str]
    limit: int = 0


class BulkInitiateRequest(BaseModel):
    numbers: List[str]


@app.post("/send")
async def initiate_bulk_conversations(body: BulkInitiateRequest) -> Dict[str, Any]:
    """
    Initiate conversations with contacts by sending template messages.
    Supports both single contact (array with one number) and bulk operations.
    Useful for campaigns, outreach, or starting individual conversations.
    """
    results = []
    successful = 0
    failed = 0
    
    logger.info("api.initiate-bulk start count=%s", len(body.numbers))
    
    for number in body.numbers:
        try:
            logger.info("api.initiate-bulk processing=%s", number)
            resp = send_template_message(number)
            results.append({
                "number": number,
                "success": True,
                "response": resp
            })
            successful += 1
            logger.info("api.initiate-bulk success=%s", number)
        except Exception as e:
            results.append({
                "number": number,
                "success": False,
                "error": str(e)
            })
            failed += 1
            logger.error("api.initiate-bulk failed=%s error=%s", number, str(e))
    
    logger.info("api.initiate-bulk done successful=%s failed=%s", successful, failed)
    return {
        "total": len(body.numbers),
        "successful": successful,
        "failed": failed,
        "results": results
    }


@app.post("/get")
async def get_bulk_endpoint(body: BulkGetRequest) -> Dict[str, Any]:
    """
    Retrieve messages from multiple phone numbers.
    Supports both single contact (array with one number) and bulk operations.
    """
    results = []
    total_messages = 0
    successful = 0
    failed = 0
    
    logger.info("api.get-bulk start numbers=%s limit=%s", len(body.numbers), body.limit)
    
    for number in body.numbers:
        try:
            logger.info("api.get-bulk processing=%s", number)
            items = fetch_messages_by_number(number, max(0, body.limit))
            results.append({
                "number": number,
                "success": True,
                "count": len(items),
                "messages": items
            })
            total_messages += len(items)
            successful += 1
            logger.info("api.get-bulk success=%s count=%s", number, len(items))
        except Exception as e:
            results.append({
                "number": number,
                "success": False,
                "error": str(e),
                "count": 0,
                "messages": []
            })
            failed += 1
            logger.error("api.get-bulk failed=%s error=%s", number, str(e))
    
    logger.info("api.get-bulk done successful=%s failed=%s total_messages=%s", successful, failed, total_messages)
    return {
        "total_numbers": len(body.numbers),
        "successful": successful,
        "failed": failed,
        "total_messages": total_messages,
        "results": results
    }


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
    print("=== INCOMING WEBHOOK ===")
    print(payload)
    print("=======================")
    
    msgs = handle_webhook_event(payload)
    
    stored = store_inbound_messages(msgs)
    logger.info("stored messages count=%s", stored)
    
    for msg in msgs:
        msg_type = msg.get("type")
        from_number = msg.get("from")
        message_body = msg.get("body")
        
        if msg_type in ["text", "button", "interactive"] and from_number and message_body:
            print(f"📱 INCOMING MESSAGE: From {from_number} - '{message_body}'")
            logger.info("processing incoming message from=%s type=%s body=%s", from_number, msg_type, message_body)
            auto_respond_to_message(from_number, message_body)
        else:
            logger.info("ignoring non-message webhook event type=%s from=%s", msg_type, from_number)
    
    logger.info("api.webhook receive done received=%s stored=%s", len(msgs), stored)
    return JSONResponse({"received": len(msgs), "stored": stored})
    


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)