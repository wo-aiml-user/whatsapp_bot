
import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pymongo import MongoClient

from .model_config import get_llm
from src.whatsapp_client import fetch_messages_by_number, send_template_message, send_text_message, WhatsAppAPIError

load_dotenv('.env')

logger = logging.getLogger(__name__)


def format_conversation_history(messages: List[Dict[str, Any]]) -> str:
    """
    Format conversation history from MongoDB messages into a readable string
    """
    if not messages:
        return "No previous conversation history."
    
    formatted_history = []
    for msg in messages:
        timestamp = msg.get('timestamp', '')
        msg_type = msg.get('type', '')
        body = msg.get('body', '')
        from_number = msg.get('from', '')
        to_number = msg.get('to', '')
        if from_number and body:
            formatted_history.append(f"User: {body}")
        elif to_number and body:
            formatted_history.append(f"Assistant: {body}")
    history_str = "\n".join(formatted_history)
    try:
        logger.info("chat.history formatted=%s", history_str)
    except Exception:
        pass
    return history_str


def generate_response(user_message: str, phone_number: str) -> str:
    """
    Generate a response using the LLM with full conversation history context
    """
    try:
        history_messages = fetch_messages_by_number(phone_number, 0)
        try:
            logger.info("chat.history raw=%s", json.dumps(history_messages))
        except Exception:
            logger.info("chat.history raw(non-serializable)")
        conversation_history = format_conversation_history(history_messages)
        
        prompt_template = ChatPromptTemplate.from_template(
            "{system_prompt}\n\nConversation History:\n{history}\n\nCurrent User Message: {user_message}\n\nPlease respond as a helpful WhatsApp assistant:"
        )
        
        llm = get_llm()
        
        formatted_prompt = prompt_template.format_messages(
            system_prompt=(
                "You are a helpful WhatsApp assistant. You should respond to user messages in a friendly, helpful manner.\n"
                "Keep your responses concise and relevant to the user's query."
            ),
            history=conversation_history,
            user_message=user_message
        )
        
        prompt_text = "\n\n".join(getattr(m, "content", str(m)) for m in formatted_prompt)
        logger.info("LLM prompt (full):\n%s", prompt_text)
        response = llm.invoke(formatted_prompt)
        
        response_text = response.content if hasattr(response, 'content') else str(response)
        logger.info("LLM response (full):\n%s", response_text)
        return response_text
        
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "I apologize, but I'm having trouble processing your message right now. Please try again later."


def auto_respond_to_message(from_number: str, message_body: str) -> None:
    """
    Automatically generate and send a response to an incoming message.
    This function checks message history BEFORE the current message was stored.
    """
    try:
        logger.info("auto_respond start from=%s message=%s", from_number, message_body)
        history = fetch_messages_by_number(from_number, 0)
        user_message_count = 0
        for msg in history:
            msg_from = msg.get("from")
            if msg_from and str(msg_from) == from_number:
                user_message_count += 1
        
        logger.info("auto_respond user_message_count=%s for from_number=%s", user_message_count, from_number)
        if user_message_count == 0:
            logger.info("sending template (first contact) to=%s", from_number)
            resp = send_template_message(from_number)
            logger.info("auto_respond success (template) to=%s", from_number)
        else:
            logger.info("generating llm response to message from=%s (previous_message_count=%s)", from_number, user_message_count)
            llm_response = generate_response(message_body, from_number)
            logger.info("sending llm response to=%s body=%s", from_number, llm_response)
            resp = send_text_message(from_number, llm_response)
            logger.info("auto_respond success (llm) to=%s", from_number)
            
    except WhatsAppAPIError as e:
        logger.error("auto_respond whatsapp error from=%s error=%s", from_number, str(e))
    except Exception as e:
        logger.error("auto_respond general error from=%s error=%s", from_number, str(e))

