
import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from langchain.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from pymongo import MongoClient

from .model_config import get_llm
from src.whatsapp_client import fetch_messages_by_number

load_dotenv('config.env')

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
        history_messages = fetch_messages_by_number(phone_number, 0)  # 0 means no limit
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

