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
    logger.info("Received webhook request")
    data = await request.json()
    db = SessionLocal()
    
    try:
        # 1. Extract message details
        message = data['entry'][0]['changes'][0]['value']['messages'][0]
        sender = message['from']
        text = message['text']['body'].lower()

        # 2. Fetch or Create User State
        user = db.query(UserState).filter(UserState.phone_number == sender).first()
        if not user:
            user = UserState(phone_number=sender)
            db.add(user)
            db.commit()

        # 3. State Machine Logic
        reply = ""
        
        if text == "apply":
            user.state = "leave_application" # Using your specific state name
            user.step = "awaiting_reason"
            reply = "Starting your leave application. Please state the reason for leave."
        
        elif user.state == "leave_application":
            if user.step == "awaiting_reason":
                user.data = {"reason": text}
                user.step = "awaiting_date"
                reply = "Got it. What is the start date (YYYY-MM-DD)?"
            elif user.step == "awaiting_date":
                user.data["date"] = text
                user.state = "idle" # Reset after finishing
                user.step = None
                reply = f"Thank you! Your leave for '{user.data['reason']}' on {text} has been submitted."

        else:
            reply = "Welcome! Type 'apply' to start a leave application."

        # 4. Save changes and Send reply
        db.commit()
        send_whatsapp_response(sender, reply)

    except Exception as e:
        logger.error(f"Error processing message: {e}")
    
    return {"status": "success"}
PHONE_NUMBER_ID = "1234567890"
ACCESS_TOKEN = "your_access_token"
def send_whatsapp_response(to_number, text):
    """
    Sends a message back to the user via Meta's Graph API.
    """
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()