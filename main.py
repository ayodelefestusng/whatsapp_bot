from fastapi import FastAPI, Request
from database import SessionLocal, UserState
import requests


import os
import json
import logging
import traceback
from typing import List, Optional, Any
from logging.handlers import RotatingFileHandler
# Create logs directory if it doesn't exist
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE = os.path.join(LOG_DIR, "payroll_log.log")

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        # Rotate after 5MB, keep 5 old log files
        RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5),
        logging.StreamHandler() # Also prints to your terminal
    ]
)

logger = logging.getLogger("WhatsappBot")
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
@app.post("/webhook")
async def handle_whatsapp(request: Request):
    data = await request.json()
    db = SessionLocal()
    
    try:
        # Evolution API sends events. We only care about new messages.
        if data.get("event") != "messages.upsert":
            return {"status": "ignored"}

        # Extract details for Evolution API structure
        message_data = data['data']
        sender = message_data['key']['remoteJid'].split('@')[0] # Gets '23480...'
        text = message_data.get('message', {}).get('conversation', '').lower()

        # State Machine Logic
        user = db.query(UserState).filter(UserState.phone_number == sender).first()
        if not user:
            user = UserState(phone_number=sender, state="idle")
            db.add(user)

        reply = ""
        if text == "apply":
            user.state = "leave_application" # Your requested state name
            user.step = "awaiting_reason"
            reply = "Starting your leave application. Please state the reason for leave."
        
        elif user.state == "leave_application":
            if user.step == "awaiting_reason":
                user.temp_data = json.dumps({"reason": text}) # JSON string for DB
                user.step = "awaiting_date"
                reply = "Got it. What is the start date (YYYY-MM-DD)?"
            elif user.step == "awaiting_date":
                # Finalizing application
                user.state = "idle"
                user.step = None
                reply = f"Thank you! Your leave request has been submitted."

        else:
            reply = "Welcome! Type 'apply' to start."

        db.commit()
        # Use Evolution API to send the reply
        send_evolution_response(sender, reply)

    except Exception as e:
        logger.error(f"Error: {traceback.format_exc()}")
    finally:
        db.close()
    
    return {"status": "success"}

def send_evolution_response(to_number, text):
    """
    Sends a message via YOUR Evolution API (Not Meta).
    """
    url = f"{os.getenv('EVO_URL')}/message/sendText/{os.getenv('EVO_INSTANCE')}"
    headers = {"apikey": os.getenv("AUTHENTICATION_API_KEY")}
    payload = {
        "number": to_number,
        "text": text
    }
    return requests.post(url, json=payload, headers=headers)