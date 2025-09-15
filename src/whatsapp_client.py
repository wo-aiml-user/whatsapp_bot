"""
 WhatsApp Business API client for two core flows:
- Sending text messages to users
- Receiving webhook events and storing messages, then fetching them
"""

import os
import requests
import json
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config.env')

# Configuration
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')
GRAPH_API_BASE = os.getenv('GRAPH_API_BASE', 'https://graph.facebook.com/v22.0')

# Redis configuration (optional if using webhook storage)
REDIS_URL = os.getenv('REDIS_URL')
REDIS_INBOUND_LIST = os.getenv('REDIS_INBOUND_LIST', 'whatsapp:inbound:list')

# Logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class WhatsAppAPIError(Exception):
    """Custom exception for WhatsApp API errors"""
    pass


def _normalize_number(number: Optional[str]) -> Optional[str]:
    """Normalize phone numbers by keeping digits only (drops leading '+', spaces, etc)."""
    if not number:
        return number
    try:
        digits = ''.join(ch for ch in str(number) if ch.isdigit())
        return digits
    except Exception:
        return number


def _make_request(method: str, url: str, headers: Dict[str, str], data: Optional[Dict] = None) -> Dict[str, Any]:
    """Make HTTP request to WhatsApp API with error handling and logging"""
    try:
        logger.info("whatsapp.request start method=%s url=%s", method, url)
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=data)
        else:
            raise WhatsAppAPIError(f"Unsupported HTTP method: {method}")

        logger.info("whatsapp.response status=%s", response.status_code)
        response.raise_for_status()
        payload = response.json()
        logger.info("whatsapp.response ok keys=%s", list(payload.keys()))
        return payload
    except requests.exceptions.RequestException as e:
        logger.error("whatsapp.request error=%s", str(e))
        raise WhatsAppAPIError(f"API request failed: {str(e)}")


def send_message_text(to_number: str, message: str) -> Dict[str, Any]:
    """
    Send a free-form text message (24h session window required)
    """
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        raise WhatsAppAPIError("ACCESS_TOKEN and PHONE_NUMBER_ID must be set in environment")

    url = f"{GRAPH_API_BASE}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    to_number_norm = _normalize_number(to_number)
    body = {
        "messaging_product": "whatsapp",
        "to": to_number_norm,
        "type": "text",
        "text": {"body": message}
    }
    logger.info("whatsapp.send start to=%s normalized=%s", to_number, to_number_norm)
    result = _make_request('POST', url, headers, body)
    logger.info("whatsapp.send success message_id=%s", (result.get('messages', [{}])[0].get('id') if isinstance(result.get('messages'), list) else None))
    return result


def send_text_message(to_number: str, message: str) -> Dict[str, Any]:
    return send_message_text(to_number, message)


# removed: send_media_message and other non-core operations


# Webhook handling helpers
def handle_webhook_event(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse WhatsApp webhook payload into a list of message dicts.
    Each message dict minimally contains: from, to, timestamp, type, body, id, chat_id
    """
    logger.info("webhook.parse start")
    messages: List[Dict[str, Any]] = []
    entry_list = payload.get("entry", [])
    for entry in entry_list:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            msgs = value.get("messages", [])
            metadata = value.get("metadata", {})
            to_phone = metadata.get("display_phone_number") or metadata.get("phone_number_id")
            for i, msg in enumerate(msgs):
                from_ = _normalize_number(msg.get("from"))
                msg_id = msg.get("id")
                timestamp = msg.get("timestamp")
                msg_type = msg.get("type")
                body = None
                if msg_type == "text":
                    body = msg.get("text", {}).get("body")
                elif msg_type == "button":
                    body = msg.get("button", {}).get("text")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    body = interactive.get("nfm_reply", {}).get("body") or interactive.get("button_reply", {}).get("title")
                messages.append({
                    "id": msg_id,
                    "from": from_,
                    "to": _normalize_number(to_phone),
                    "timestamp": timestamp,
                    "type": msg_type,
                    "body": body,
                    "raw": msg
                })
    logger.info("webhook.parse done count=%s", len(messages))
    return messages


def store_inbound_messages(messages: List[Dict[str, Any]]) -> int:
    """Store inbound messages into Redis under per-number lists. Returns number stored."""
    if not REDIS_URL:
        return 0
    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=True)
        count = 0
        for m in messages:
            number = _normalize_number(m.get("from") or m.get("to"))
            if not number:
                logger.warning("webhook.store skip message without number")
                continue
            key = f"{REDIS_INBOUND_LIST}:{number}"
            client.lpush(key, json.dumps(m))
            count += 1
        logger.info("webhook.store success stored=%s", count)
        return count
    except Exception as e:
        logger.error("webhook.store error=%s", str(e))
        return 0


def fetch_latest_messages(limit: int = 20) -> List[Dict[str, Any]]:
    """Deprecated: Fetches from legacy flat list if present (kept for compatibility)."""
    if not REDIS_URL:
        return []
    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=True)
        if limit is None or limit <= 0:
            items = client.lrange(REDIS_INBOUND_LIST, 0, -1)
        else:
            items = client.lrange(REDIS_INBOUND_LIST, 0, max(0, limit - 1))
        result: List[Dict[str, Any]] = []
        for item in items:
            try:
                result.append(json.loads(item))
            except Exception:
                continue
        logger.info("messages.fetch(legacy) success count=%s limit=%s", len(result), limit)
        return result
    except Exception as e:
        logger.error("messages.fetch error=%s", str(e))
        return []


def fetch_messages_by_number(number: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch inbound messages for a specific phone number. If limit <= 0, return all."""
    if not REDIS_URL:
        return []
    try:
        import redis
        client = redis.from_url(REDIS_URL, decode_responses=True)
        number_norm = _normalize_number(number)
        key = f"{REDIS_INBOUND_LIST}:{number_norm}"
        if limit is None or limit <= 0:
            items = client.lrange(key, 0, -1)
        else:
            items = client.lrange(key, 0, max(0, limit - 1))
        result: List[Dict[str, Any]] = []
        for item in items:
            try:
                result.append(json.loads(item))
            except Exception:
                continue
        logger.info("messages.fetch success number=%s normalized=%s count=%s limit=%s", number, number_norm, len(result), limit)
        return result
    except Exception as e:
        logger.error("messages.fetch error number=%s error=%s", number, str(e))
        return []




 


 


 
