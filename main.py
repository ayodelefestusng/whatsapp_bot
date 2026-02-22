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


DATABASE_URL = os.getenv("DATABASE_URL")

# --- DEBUGGING PRINT ---
if DATABASE_URL is None:
    print("❌ ERROR: DATABASE_URL variable is missing from the environment!")
else:
    print(f"✅ DATABASE_URL found: {DATABASE_URL[:15]}...") 
# -----------------------

engine = create_async_engine(
    DATABASE_URL or "sqlite+aiosqlite:///:memory:", # Fallback to prevent crash if None
    pool_pre_ping=True,
    connect_args={"ssl": True} if DATABASE_URL and "mysql" in DATABASE_URL else {}
)




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
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ DATABASE: Tables created or verified successfully!")
    except Exception as e:
        print(f"❌ DATABASE ERROR on startup: {e}")

# 4. Webhook Logic
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        print(f"DEBUG: Received Data: {json.dumps(data)}") # View this in Railway Logs
        
        # Evolution API v2 often uses 'messages.upsert'. v1 uses 'MESSAGES_UPSERT'
        event = data.get("event", "").lower()
        if event != "messages.upsert":
            return {"status": "ignored", "event_received": event}

        msg_data = data.get('data', {})
        # Safety check: ensure it's not a message from the bot itself
        if msg_data.get('key', {}).get('fromMe'):
            return {"status": "ignored", "reason": "own_message"}

        sender = msg_data['key']['remoteJid'].split('@')[0]
        message_obj = msg_data.get('message', {})
        
        # Try different ways WhatsApp messages can arrive
        text = (
            message_obj.get('conversation') or 
            message_obj.get('extendedTextMessage', {}).get('text') or 
            ""
        ).lower().strip()

        async with AsyncSessionLocal() as db:
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
    except Exception as e:
        print(f"❌ WEBHOOK ERROR: {e}")
        return {"status": "error", "details": str(e)}

async def send_msg(number, text):
    try:
        base_url = os.getenv('EVO_URL').rstrip('/')
        instance = os.getenv('EVO_INSTANCE')
        url = f"{base_url}/message/sendText/{instance}"
        headers = {"apikey": os.getenv("EVO_KEY")}
        payload = {"number": number, "text": text, "delay": 1200}
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
            print(f"DEBUG: Evolution Response: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ SEND_MSG ERROR: {e}")

@app.get("/")
async def root():
    return {"status": "online", "database": "connected"}