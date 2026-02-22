from fastapi import FastAPI, Request
import httpx
import os
import json
from sqlalchemy import Column, Integer, String, Text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# 1. Database Setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# 2. State Model
class UserState(Base):
    __tablename__ = "user_states"
    id = Column(Integer, primary_key=True)
    phone_number = Column(String(20), unique=True)
    state = Column(String(50))
    step = Column(String(50))
    temp_data = Column(Text)

# 3. Automatic Table Creation
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully!")

# 4. Webhook Logic (Async Version)
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    
    if data.get("event") != "messages.upsert":
        return {"status": "ignored"}

    msg_data = data['data']
    # Handle cases where message or conversation might be missing
    sender = msg_data['key']['remoteJid'].split('@')[0]
    message_obj = msg_data.get('message', {})
    text = (message_obj.get('conversation') or message_obj.get('extendedTextMessage', {}).get('text') or "").lower()

    async with AsyncSessionLocal() as db:
        # Use select() for Async queries
        result = await db.execute(select(UserState).filter(UserState.phone_number == sender))
        user = result.scalars().first()

        if not user:
            user = UserState(phone_number=sender, state="idle")
            db.add(user)

        reply = ""
        if text == "apply":
            user.state = "leave_application"
            user.step = "awaiting_reason"
            reply = "Starting your leave application. Why do you need leave?"
        
        elif user.state == "leave_application":
            if user.step == "awaiting_reason":
                user.temp_data = json.dumps({"reason": text})
                user.step = "awaiting_date"
                reply = "Got it. What is the start date (YYYY-MM-DD)?"
            elif user.step == "awaiting_date":
                user.state = "idle"
                user.step = None
                reply = "Thank you! Your leave request has been recorded."

        if reply:
            await db.commit()
            await send_msg(sender, reply)

    return {"status": "success"}

async def send_msg(number, text):
    # Ensure URL doesn't have double slashes
    base_url = os.getenv('EVO_URL').rstrip('/')
    url = f"{base_url}/message/sendText/{os.getenv('EVO_INSTANCE')}"
    headers = {"apikey": os.getenv("EVO_KEY")}
    payload = {"number": number, "text": text}
    
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)

@app.get("/")
async def root():
    return {"status": "online", "message": "WhatsApp Bot is active"}