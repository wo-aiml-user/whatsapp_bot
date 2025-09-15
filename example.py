#!/usr/bin/env python3
"""
Example usage of WhatsApp MCP Server

This script demonstrates how to use the WhatsApp client functions
to send text or template messages via the WhatsApp Business API.
"""

import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config.env')

# Required vars
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
GRAPH_API_BASE = "https://graph.facebook.com/v22.0"


class WhatsAppAPIError(Exception):
    """Custom error for WhatsApp API failures"""
    pass


def send_text_message(to_number: str, message: str):
    """Send a free-form text message (only works in 24h session window)"""
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
    resp = requests.post(url, headers=headers, json=body)
    if not resp.ok:
        raise WhatsAppAPIError(f"{resp.status_code}: {resp.text}")
    return resp.json()


def send_template_message(to_number: str):
    """Send the default hello_world template"""
    url = f"{GRAPH_API_BASE}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"}
        }
    }
    resp = requests.post(url, headers=headers, json=body)
    if not resp.ok:
        raise WhatsAppAPIError(f"{resp.status_code}: {resp.text}")
    return resp.json()


def prompt_and_send_text():
    """Prompt for phone number and message, then send text"""
    print("\nSend Text Message")
    print("-" * 20)
    number = input("Enter phone number with country code (no +): ").strip()
    text = input("Enter message text: ").strip()
    if not number or not text:
        print("❌ Both phone number and message are required")
        return False
    try:
        result = send_text_message(number, text)
        print("✅ Text sent! Response:", result)
        return True
    except WhatsAppAPIError as e:
        print("❌ Error:", e)
        return False


def prompt_and_send_template():
    """Prompt for phone number, then send template"""
    print("\nSend Template Message (hello_world)")
    print("-" * 30)
    number = input("Enter phone number with country code (no +): ").strip()
    if not number:
        print("❌ Phone number required")
        return False
    try:
        result = send_template_message(number)
        print("✅ Template sent! Response:", result)
        return True
    except WhatsAppAPIError as e:
        print("❌ Error:", e)
        return False


def interactive_mode():
    """Interactive menu"""
    print("\nInteractive Mode")
    print("=" * 20)
    print("Enter 'quit' to exit")

    while True:
        print("\n1. Send text message")
        print("2. Send template message (hello_world)")
        print("3. Quit")
        choice = input("\nEnter your choice (1-3): ").strip()
        if choice == '1':
            prompt_and_send_text()
        elif choice == '2':
            prompt_and_send_template()
        elif choice == '3' or choice.lower() == 'quit':
            print("Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 1-3.")


def main():
    """Main function"""
    print("WhatsApp MCP Server - Example Usage")
    print("=" * 40)

    if not ACCESS_TOKEN or ACCESS_TOKEN.startswith("YOUR_"):
        print("❌ Please configure your environment variables in config.env first!")
        return

    print("✅ Environment configured.")
    # Run once
    prompt_and_send_text()
    # Ask for interactive mode
    try_interactive = input("\nOpen interactive mode? (y/n): ").strip().lower()
    if try_interactive in ['y', 'yes']:
        interactive_mode()


if __name__ == "__main__":
    main()
