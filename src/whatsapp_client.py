

import os
import requests
import json
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection

# Load environment variables
load_dotenv('config.env')

# Configuration
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')
GRAPH_API_BASE = os.getenv('GRAPH_API_BASE', 'https://graph.facebook.com/v22.0')

# MongoDB configuration
MONGO_URI = os.getenv('MONGO_URI')
DATABASE_NAME = os.getenv('DATABASE_NAME', 'chat_db')
COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'user_chat')

_mongo_client: Optional[MongoClient] = None
_mongo_collection: Optional[Collection] = None


def _get_collection() -> Optional[Collection]:
    global _mongo_client, _mongo_collection
    if _mongo_collection is not None:
        return _mongo_collection
    if not MONGO_URI:
        logger.warning("MongoDB not configured: MONGO_URI missing")
        return None
    try:
        _mongo_client = MongoClient(MONGO_URI)
        _mongo_collection = _mongo_client[DATABASE_NAME][COLLECTION_NAME]
        return _mongo_collection
    except Exception as e:
        logger.error("mongo.connect error=%s", str(e))
        return None

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


def _make_request(method: str, url: str, headers: Dict[str, str], data: Optional[Dict] = None) -> Dict[str, Any]:
    """Make HTTP request to WhatsApp API with error handling and logging"""
    try:
        safe_headers = dict(headers)
        if "Authorization" in safe_headers:
            safe_headers["Authorization"] = "***REDACTED***"
        logger.info("whatsapp.request start method=%s url=%s headers=%s", method, url, safe_headers)
        if data is not None:
            try:
                logger.info("whatsapp.request payload=%s", json.dumps(data))
            except Exception:
                logger.info("whatsapp.request payload(non-serializable)")
        if method.upper() == 'GET':
            response = requests.get(url, headers=headers)
        elif method.upper() == 'POST':
            response = requests.post(url, headers=headers, json=data)
        else:
            raise WhatsAppAPIError(f"Unsupported HTTP method: {method}")

        logger.info("whatsapp.response status=%s", response.status_code)
        response.raise_for_status()
        payload = response.json()
        try:
            logger.info("whatsapp.response payload=%s", json.dumps(payload))
        except Exception:
            logger.info("whatsapp.response payload(non-serializable)")
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
    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message}
    }
    logger.info("whatsapp.send start (text) to=%s body=%s", to_number, message)
    result = _make_request('POST', url, headers, body)
    logger.info("whatsapp.send success message_id=%s", (result.get('messages', [{}])[0].get('id') if isinstance(result.get('messages'), list) else None))
    return result


def send_text_message(to_number: str, message: str) -> Dict[str, Any]:
    return send_message_text(to_number, message)


def send_template_message(
    to_number: str,
    template_name: str = "hello_world",
    language_code: str = "en_US",
    components: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Send a template message using a pre-approved template.
    Default sends the standard 'hello_world' template.
    """
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        raise WhatsAppAPIError("ACCESS_TOKEN and PHONE_NUMBER_ID must be set in environment")

    url = f"{GRAPH_API_BASE}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    if components:
        body["template"]["components"] = components

    logger.info("whatsapp.send_template start to=%s template=%s body=%s", to_number, template_name, body)
    result = _make_request("POST", url, headers, body)
    logger.info(
        "whatsapp.send_template success message_id=%s",
        (result.get("messages", [{}])[0].get("id") if isinstance(result.get("messages"), list) else None),
    )
    return result



# Webhook handling helpers
def handle_webhook_event(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse WhatsApp webhook payload into a list of message dicts.
    Each message dict minimally contains: from, to, timestamp, type, body, id, chat_id
    """
    try:
        logger.info("webhook.receive raw_payload=%s", json.dumps(payload))
    except Exception:
        logger.info("webhook.receive raw_payload(non-serializable)")
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
                from_ = msg.get("from")
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
                    "to": to_phone,
                    "timestamp": timestamp,
                    "type": msg_type,
                    "body": body,
                    "raw": msg
                })
    try:
        logger.info("webhook.parse done count=%s messages=%s", len(messages), json.dumps(messages))
    except Exception:
        logger.info("webhook.parse done count=%s (messages non-serializable)", len(messages))
    return messages


def store_inbound_messages(messages: List[Dict[str, Any]]) -> int:
    """Store inbound messages into MongoDB. Returns number stored."""
    collection = _get_collection()
    if collection is None:
        return 0
    try:
        docs: List[Dict[str, Any]] = []
        for m in messages:
            from_number = m.get("from")
            to_number = m.get("to")
            if not from_number and not to_number:
                logger.warning("webhook.store skip message without addresses")
                continue
            doc = dict(m)
            doc["from"] = from_number
            doc["to"] = to_number
            doc["participant_numbers"] = [n for n in [from_number, to_number] if n]
            docs.append(doc)
        if not docs:
            return 0
        try:
            logger.info("mongo.insert_many docs=%s", json.dumps(docs))
        except Exception:
            logger.info("mongo.insert_many docs(non-serializable)")
        result = collection.insert_many(docs)
        count = len(result.inserted_ids)
        logger.info("webhook.store(mongo) success stored=%s", count)
        return count
    except Exception as e:
        logger.error("webhook.store(mongo) error=%s", str(e))
        return 0


def fetch_latest_messages(limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch latest messages across collection (primarily for diagnostics)."""
    collection = _get_collection()
    if collection is None:
        return []
    try:
        cursor = collection.find({}, sort=[("timestamp", -1)])
        if limit and limit > 0:
            cursor = cursor.limit(limit)
        results = [
            {k: v for k, v in doc.items() if k != "_id"}
            for doc in cursor
        ]
        try:
            logger.info("messages.fetch_latest(mongo) success count=%s limit=%s results=%s", len(results), limit, json.dumps(results))
        except Exception:
            logger.info("messages.fetch_latest(mongo) success count=%s limit=%s (results non-serializable)", len(results), limit)
        return results
    except Exception as e:
        logger.error("messages.fetch_latest(mongo) error=%s", str(e))
        return []


def fetch_messages_by_number(number: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Fetch messages for a specific phone number from MongoDB. Newest first. If limit <= 0, return all."""
    collection = _get_collection()
    if collection is None:
        return []
    try:
        query = {"participant_numbers": number}
        logger.info("messages.fetch(mongo) query=%s", json.dumps(query))
        cursor = collection.find(query, sort=[("timestamp", -1)])
        if limit and limit > 0:
            cursor = cursor.limit(limit)
        results = [
            {k: v for k, v in doc.items() if k != "_id"}
            for doc in cursor
        ]
        try:
            logger.info("messages.fetch(mongo) success number=%s count=%s limit=%s results=%s", number, len(results), limit, json.dumps(results))
        except Exception:
            logger.info("messages.fetch(mongo) success number=%s count=%s limit=%s (results non-serializable)", number, len(results), limit)
        return results
    except Exception as e:
        logger.error("messages.fetch(mongo) error number=%s error=%s", number, str(e))
        return []