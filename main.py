from fastapi import FastAPI, Request
import httpx
import os
import json
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Text
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()
# This pulls the URI from your Railway Variables
DATABASE_URL = os.getenv("DATABASE_URL")
# Database Setup
# engine = create_engine(os.getenv("DATABASE_URL"))
load_dotenv()

# This pulls the URI from your Railway Variables
DATABASE_URL = os.getenv("DATABASE_URL")

# Create the Engine for Aiven MySQL
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True, # Checks if connection is alive before using it
)

AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        # This creates the table if it doesn't exist
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully!")
    
class UserState(Base):
    __tablename__ = "user_states"
    id = Column(Integer, primary_key=True)
    phone_number = Column(String(20), unique=True)
    state = Column(String(50))
    step = Column(String(50))
    temp_data = Column(Text)

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    
    # Check if it's a message event
    if data.get("event") != "messages.upsert":
        return {"status": "ignored"}

    msg_data = data['data']
    sender = msg_data['key']['remoteJid'].split('@')[0]
    text = msg_data.get('message', {}).get('conversation', '').lower()

    db = SessionLocal()
    user = db.query(UserState).filter(UserState.phone_number == sender).first()
    if not user:
        user = UserState(phone_number=sender, state="idle")
        db.add(user)

    reply = ""
    # Logic: Start Leave Application
    if text == "apply":
        user.state = "leave_application" # State name as requested
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

    db.commit()
    db.close()

    # Send message back via Evolution API
    await send_msg(sender, reply)
    return {"status": "success"}

async def send_msg(number, text):
    url = f"{os.getenv('EVO_URL')}/message/sendText/{os.getenv('EVO_INSTANCE')}"
    headers = {"apikey": os.getenv("EVO_KEY")}
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"number": number, "text": text}, headers=headers)



@app.get("/")
async def root():
    return {"status": "online", "message": "WhatsApp Bot is active and waiting for webhooks"}