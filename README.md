# WhatsApp Cloud API – FastAPI Server

Minimal FastAPI service for WhatsApp Cloud API with two core operations:
- Send message: Client App → POST /send → WhatsApp Cloud API → User
- Receive message: User → WhatsApp → Webhook → FastAPI /webhook → Redis → Client fetches via POST /get

Logging is enabled for sending and receiving flows.

## Features

- Send text messages via WhatsApp Cloud API
- Receive inbound messages via webhook and store in Redis per phone number
- Fetch messages by phone number (with optional limit)
- Structured logs to stdout for requests, responses, and storage/fetch

## Prerequisites

1. WhatsApp Business Account and Facebook Developer account
2. A WhatsApp business phone number (Sandbox or production)
3. System User Access Token with WhatsApp permissions
4. Phone Number ID and (optionally) Business Account ID
5. Python 3.10+
6. Redis (local Docker or service)

## Quick start

1) Install dependencies
```bash
pip install -r requirements.txt
```

2) Configure environment in `config.env`
```ini
ACCESS_TOKEN=YOUR_GRAPH_ACCESS_TOKEN
PHONE_NUMBER_ID=YOUR_PHONE_NUMBER_ID
BUSINESS_ACCOUNT_ID=YOUR_WABA_ID
GRAPH_API_BASE=https://graph.facebook.com/v22.0

# Webhook verification token (set the same in Meta Developer dashboard)
VERIFY_TOKEN=MY_VERIFY_TOKEN

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_INBOUND_LIST=whatsapp:inbound:list
```

3) Run Redis
- Docker (recommended):
```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```
- Native (Windows): use Memurai or Redis for Windows alternatives.

4) Run the API
```bash
uvicorn src.main:app --reload
```

## Exposing webhook (ngrok or alternatives)

The webhook must be reachable from Meta. Use a tunnel for local development:

- ngrok
```bash
ngrok http 8000
```
Take the HTTPS URL (e.g., https://abc123.ngrok.io). Your webhook endpoints will be:
- Verification: GET https://abc123.ngrok.io/webhook
- Receiver: POST https://abc123.ngrok.io/webhook

Alternatives: `cloudflared tunnel`, `localtunnel`, etc.

## WhatsApp Cloud API setup (Meta dashboard)

1. Go to Meta Developers → Your App → WhatsApp → Configuration
2. Set Callback URL: your public `/webhook` URL (e.g., https://abc123.ngrok.io/webhook)
3. Set Verify Token: must match `VERIFY_TOKEN` in `config.env`
4. Click Verify; Meta will call GET /webhook with hub params
5. Subscribe to message fields for your phone number (messages, messages.status as needed)

Verification flow:
- Meta sends GET /webhook with query params:
  - hub.mode=subscribe, hub.verify_token=YOUR_TOKEN, hub.challenge=random
- Server validates token and returns `hub.challenge` with 200 OK

## Data model and storage

- Incoming messages are parsed and normalized (phone numbers are digits-only)
- Stored in Redis per-number list key: `<REDIS_INBOUND_LIST>:<number>`
  - Example: `whatsapp:inbound:list:919316318214`
- Fetching messages reads from that per-number list

## API endpoints

### POST /send
Send a text message to a user.

Request JSON:
```json
{
  "number": "919216598210",
  "text": "Hello from FastAPI"
}
```

Responses:
- 200 OK on success (includes WhatsApp response)
- 400 Bad Request on WhatsApp API errors

Sample cURL (PowerShell users see below):
```bash
curl -X POST http://localhost:8000/send \
  -H "Content-Type: application/json" \
  -d '{"number":"919216598210","text":"Hello"}'
```

PowerShell:
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/send" `
  -ContentType "application/json" `
  -Body '{"number":"919216598210","text":"Hello"}'
```

### POST /webhook
Receives incoming messages from WhatsApp (Meta). Parses and stores messages to Redis per number.

You do not call this directly; Meta calls it after configuration and subscription.

### GET /webhook (verification)
Meta calls this once when you press Verify. The server checks `VERIFY_TOKEN` and echoes the challenge.

### POST /get
Fetch messages for a specific number (digits-only or with `+`, both accepted).

Request JSON:
```json
{
  "number": "+919216598210",
  "limit": 0
}
```
- `limit` = 0 (or omitted) returns all available messages for that number

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

## Example webhook payload (inbound message)

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
```

Our server normalizes and stores it under `whatsapp:inbound:list:919316318214`.


## Troubleshooting

- 401/403 during webhook verify: Ensure `VERIFY_TOKEN` matches dashboard, use current public URL
- 200 OK but zero messages when fetching:
  - Ensure you are posting to `/get` (POST, not GET)
  - Use digits-only number or include `+` (server normalizes internally)
  - Verify Redis is running and `REDIS_URL` is correct
  - Check logs for `webhook.store success` and `messages.fetch success`
- WhatsApp API errors when sending:
  - Verify `ACCESS_TOKEN` and `PHONE_NUMBER_ID`
  - Respect 24-hour user-initiated session window

## License

This project is provided as-is for development purposes. Ensure compliance with WhatsApp and Meta API policies.
