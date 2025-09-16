import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv('config.env')

VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')


def verify_webhook_token(mode: Optional[str], token: Optional[str]) -> bool:
    if mode != 'subscribe':
        return False
    return bool(VERIFY_TOKEN) and token == VERIFY_TOKEN



