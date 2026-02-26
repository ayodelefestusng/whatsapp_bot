from fastapi import FastAPI, Request
import httpx
import os
import json
import re
from sqlalchemy import Column, Integer, String, Text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# load_dotenv()

# # Ensure a MySQL DBAPI is available. If `MySQLdb` (mysqlclient) is missing,
# # try to use `pymysql` as a drop-in replacement so SQLAlchemy can import
# # the `MySQLdb` module name.
# try:
#     import MySQLdb  # noqa: F401
# except Exception:
#     try:
#         import pymysql
#         pymysql.install_as_MySQLdb()
#         print("ℹ️ Using pymysql as MySQLdb shim")
#     except Exception as e:
#         print(f"⚠️ MySQLdb import failed and pymysql is not available: {e}")

# app = FastAPI()


# DATABASE_URL = os.getenv("DATABASE_URL")

# # --- DEBUGGING PRINT ---
# if DATABASE_URL is None:
#     print("❌ ERROR: DATABASE_URL variable is missing from the environment!")
# else:
#     print(f"✅ DATABASE_URL found: {DATABASE_URL[:15]}...") 
# # -----------------------

# # engine = create_async_engine(
# #     DATABASE_URL or "sqlite+aiosqlite:///:memory:", # Fallback to prevent crash if None
# #     pool_pre_ping=True,
# #     connect_args={"ssl": True} if DATABASE_URL and "mysql" in DATABASE_URL else {}
# # )

# # Prepare async-capable DATABASE_URL. SQLAlchemy async engines require an async DBAPI
# # (aiomysql or asyncmy) for MySQL. If the provided DATABASE_URL references a sync driver
# # (e.g., mysql:// or mysql+mysqldb://), try to convert it to use an async driver.
# engine_url = DATABASE_URL

# if engine_url and engine_url.startswith("mysql"):
#     # Prefer aiomysql, fallback to asyncmy if available
#     async_driver = None
#     try:
#         import aiomysql  # type: ignore
#         async_driver = "aiomysql"
#     except Exception:
#         try:
#             import asyncmy  # type: ignore
#             async_driver = "asyncmy"
#         except Exception:
#             async_driver = None

#     if async_driver:
#         # Replace scheme prefix with async driver variant, e.g. mysql:// -> mysql+aiomysql://
#         engine_url = re.sub(r"^mysql(\+[^:]*)?:", f"mysql+{async_driver}:", engine_url)
#         print(f"ℹ️ Using async MySQL driver: {async_driver}")
#     else:
#         msg = (
#             "No async MySQL driver is installed. Install one with: `pip install aiomysql` "
#             "or `pip install asyncmy`.\n" 
#             "If you prefer to use sqlite for local development, set `DATABASE_URL` to a "
#             "`sqlite+aiosqlite:///:memory:` (or similar) in your environment."
#         )
#         print(f"⚠️ {msg}")
#         # Fail fast so the deployer or developer sees a clear message rather than silently
#         # falling back to sqlite. This prevents accidental use of an unintended DB.
#         raise RuntimeError(msg)

# engine = create_async_engine(
#     engine_url,
#     echo=False,
#     # connect_args={
#     #     "ssl": True,
#     #     "connect_timeout": 10
#     # } if engine_url.startswith("mysql+") else {}
#     connect_args={"connect_timeout": 10} if engine_url.startswith("mysql+") else {}
# )

# AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
# Base = declarative_base()

# # 2. State Model
# class UserState(Base):
#     __tablename__ = "user_states"
#     id = Column(Integer, primary_key=True)
#     phone_number = Column(String(20), unique=True)
#     state = Column(String(50))
#     step = Column(String(50))
#     temp_data = Column(Text)

# # 3. Automatic Table Creation
# @app.on_event("startup")
# async def startup():
#     try:
#         async with engine.begin() as conn:
#             await conn.run_sync(Base.metadata.create_all)
#         print("✅ DATABASE: Tables created or verified successfully!")
#     except Exception as e:
#         print(f"❌ DATABASE ERROR on startup: {e}")

# # 4. Webhook Logic
# @app.post("/webhook")
# async def webhook(request: Request):
#     try:
#         data = await request.json()
#         print(f"DEBUG: Received Data: {json.dumps(data)}") # View this in Railway Logs
        
#         # Evolution API v2 often uses 'messages.upsert'. v1 uses 'MESSAGES_UPSERT'
#         event = data.get("event", "").lower()
#         if event != "messages.upsert":
#             return {"status": "ignored", "event_received": event}

#         msg_data = data.get('data', {})
#         # Safety check: ensure it's not a message from the bot itself
#         if msg_data.get('key', {}).get('fromMe'):
#             return {"status": "ignored", "reason": "own_message"}

#         sender = msg_data['key']['remoteJid'].split('@')[0]
#         message_obj = msg_data.get('message', {})
        
#         # Try different ways WhatsApp messages can arrive
#         text = (
#             message_obj.get('conversation') or 
#             message_obj.get('extendedTextMessage', {}).get('text') or 
#             ""
#         ).lower().strip()

#         async with AsyncSessionLocal() as db:
#             result = await db.execute(select(UserState).filter(UserState.phone_number == sender))
#             user = result.scalars().first()

#             if not user:
#                 user = UserState(phone_number=sender, state="idle")
#                 db.add(user)

#             reply = ""
#             if text == "apply":
#                 user.state = "leave_application"
#                 user.step = "awaiting_reason"
#                 reply = "Starting your leave application. Why do you need leave?"
            
#             elif user.state == "leave_application":
#                 if user.step == "awaiting_reason":
#                     user.temp_data = json.dumps({"reason": text})
#                     user.step = "awaiting_date"
#                     reply = "Got it. What is the start date (YYYY-MM-DD)?"
#                 elif user.step == "awaiting_date":
#                     user.state = "idle"
#                     user.step = None
#                     reply = "Thank you! Your leave request has been recorded."

#             if reply:
#                 await db.commit()
#                 await send_msg(sender, reply)

#         return {"status": "success"}
#     except Exception as e:
#         print(f"❌ WEBHOOK ERROR: {e}")
#         return {"status": "error", "details": str(e)}

# async def send_msg(number, text):
#     try:
#         base_url = os.getenv('EVO_URL').rstrip('/')
#         instance = os.getenv('EVO_INSTANCE')
#         url = f"{base_url}/message/sendText/{instance}"
#         headers = {"apikey": os.getenv("EVO_KEY")}
#         payload = {"number": number, "text": text, "delay": 1200}
        
#         async with httpx.AsyncClient() as client:
#             resp = await client.post(url, json=payload, headers=headers)
#             print(f"DEBUG: Evolution Response: {resp.status_code} - {resp.text}")
#     except Exception as e:
#         print(f"❌ SEND_MSG ERROR: {e}")
app=FastAPI()
@app.get("/")
async def root():
    return {"status": "online", "database": "connected"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    return {"status": "success"}


#Utility Endpointsd   

@app.get("/utility/")
def read_root():
    return {"message": "Hello from ATB AI!"}
