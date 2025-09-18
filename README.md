
# WhatsApp Cloud API – FastAPI Server

Minimal FastAPI service for WhatsApp Cloud API with automated messaging:
- Initiate conversations: Client App → POST /initiate-bulk → WhatsApp Cloud API → Users
- Receive & Auto-respond: User → WhatsApp → Webhook → AI Response → User
- Fetch conversation history: Client App → POST /get → MongoDB

Logging is enabled for all messaging flows with automatic LLM-powered responses.

## Features

- **Automated Messaging**: Incoming messages trigger automatic AI-powered responses
- **Conversation Initiation**: Send template messages to start conversations (single or bulk)
- **Smart Response Logic**: Template messages for new contacts, AI responses for existing conversations
- **Message Storage**: Store and retrieve conversation history in MongoDB
- **Structured Logging**: Comprehensive logs for all messaging operations
- **LLM Integration**: Google Gemini LLM for generating contextual responses
- **Status Filtering**: Process actual messages while ignoring delivery/read receipts

## Prerequisites

1. WhatsApp Business Account and Facebook Developer account
2. A WhatsApp business phone number (Sandbox or production)
3. System User Access Token with WhatsApp permissions
4. Phone Number ID and (optionally) Business Account ID
5. Python 3.10+
6. MongoDB (local Docker or service)
7. Google API Key for Gemini LLM

## Quick Start

1) Install dependencies
```bash
pip install -r requirements.txt
```

2) Configure environment in `.env` (copy from `.env.example`)
```bash
cp .env.example .env
# Then edit .env with your actual values
```
```ini
ACCESS_TOKEN=YOUR_GRAPH_ACCESS_TOKEN
PHONE_NUMBER_ID=YOUR_PHONE_NUMBER_ID
BUSINESS_ACCOUNT_ID=YOUR_WABA_ID
GRAPH_API_BASE=https://graph.facebook.com/v22.0
VERIFY_TOKEN=YOUR_VERIFY_TOKEN
MONGO_URI=mongodb://localhost:27017
DATABASE_NAME=chat_db
COLLECTION_NAME=user_chat
GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY
```

3) Run MongoDB
- Docker (recommended):
```bash
docker run -d --name mongo -p 27017:27017 mongo:6
```
- Native (Windows): Use MongoDB Community Edition or compatible alternatives.

4) Run the API
```bash
uvicorn src.main:app --reload
```

## Exposing Webhook (ngrok or alternatives)

The webhook must be reachable from Meta. Use a tunnel for local development:

- ngrok
```bash
ngrok http 8080
```
Take the HTTPS URL (e.g., https://abc123.ngrok.io). Your webhook endpoints will be:
- Verification: GET https://abc123.ngrok.io/webhook
- Receiver: POST https://abc123.ngrok.io/webhook

Alternatives: `cloudflared tunnel`, `localtunnel`, etc.

## WhatsApp Cloud API Setup (Meta Dashboard)

1. Go to Meta Developers → Your App → WhatsApp → Configuration
2. Set Callback URL: your public `/webhook` URL (e.g., https://abc123.ngrok.io/webhook)
3. Set Verify Token: must match `VERIFY_TOKEN` in `.env`
4. Click Verify; Meta will call GET /webhook with hub params
5. Subscribe to message fields for your phone number (messages, messages.status as needed)

Verification flow:
- Meta sends GET /webhook with query params:
  - hub.mode=subscribe, hub.verify_token=YOUR_TOKEN, hub.challenge=random
- Server validates token and returns `hub.challenge` with 200 OK

## Data Model and Storage

- Incoming messages are parsed and normalized (phone numbers are digits-only)
- Stored in MongoDB in the specified database and collection
- Messages include: id, from, to, timestamp, type, body, and raw payload
- Fetching messages retrieves from MongoDB by phone number, sorted by timestamp (newest first)

## API Endpoints

### POST /initiate-bulk
Initiate conversations by sending template messages to one or more contacts. Supports both single contact and bulk operations.

Request JSON:
```json
{
  "numbers": ["919216598210", "919876543210"]
}
```

For single contact:
```json
{
  "numbers": ["919216598210"]
}
```

Response:
```json
{
  "total": 2,
  "successful": 1,
  "failed": 1,
  "results": [
    {
      "number": "919216598210",
      "success": true,
      "response": { /* WhatsApp API response */ }
    },
    {
      "number": "919876543210",
      "success": false,
      "error": "Invalid phone number"
    }
  ]
}
```

Sample cURL:
```bash
curl -X POST http://localhost:8080/initiate-bulk \
  -H "Content-Type: application/json" \
  -d '{"numbers":["919216598210"]}'
```

PowerShell:
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/initiate-bulk" `
  -ContentType "application/json" `
  -Body '{"numbers":["919216598210"]}'
```

### POST /get
Fetch messages for a specific number (digits-only or with `+`, both accepted).

Request JSON:
```json
{
  "number": "+919216598210",
  "limit": 20
}
```
- `limit` = 0 returns all available messages; otherwise, limits to specified number

Response JSON:
```json
{
  "count": 2,
  "messages": [
    {
      "id": "wamid.XXX",
      "from": "919216598210",
      "to": "15551713917",
      "timestamp": "1757936743",
      "type": "text",
      "body": "Hello",
      "raw": { /* original WhatsApp payload snippet */ }
    }
  ]
}
```

### POST /get-bulk
Fetch messages from multiple phone numbers. Supports both single contact and bulk operations.

Request JSON:
```json
{
  "numbers": ["+919216598210", "+919876543210"],
  "limit": 10
}
```

For single contact:
```json
{
  "numbers": ["+919216598210"],
  "limit": 20
}
```

Response JSON:
```json
{
  "total_numbers": 2,
  "successful": 1,
  "failed": 1,
  "total_messages": 5,
  "results": [
    {
      "number": "919216598210",
      "success": true,
      "count": 5,
      "messages": [/* message objects */]
    },
    {
      "number": "919876543210",
      "success": false,
      "error": "No messages found",
      "count": 0,
      "messages": []
    }
  ]
}
```

### GET /webhook (Verification)
Meta calls this once during webhook setup. The server checks `VERIFY_TOKEN` and echoes the challenge.

### POST /webhook
Receives incoming messages from WhatsApp (Meta). Automatically:
1. Parses and stores messages in MongoDB
2. Filters out status updates (read receipts, delivery confirmations)
3. Generates and sends AI responses for actual text messages
4. Sends template messages for first-time contacts

You do not call this directly; Meta calls it after configuration and subscription.

**Automatic Response Logic:**
- **New Contact**: Sends template message on first interaction
- **Existing Contact**: Generates AI response using conversation history
- **Status Updates**: Logged but ignored (no response sent)

## Example Webhook Payload (Inbound Message)

Meta sends a payload similar to:
```json
{
  "entry": [
    {
      "changes": [
        {
          "value": {
            "metadata": { "display_phone_number": "15551713917", "phone_number_id": "123456" },
            "contacts": [ { "wa_id": "919216598210" } ],
            "messages": [
              {
                "from": "919216598210",
                "id": "wamid.XXX",
                "timestamp": "1757936743",
                "type": "text",
                "text": { "body": "Good" }
              }
            ]
          }
        }
      ]
    }
  ]
}
