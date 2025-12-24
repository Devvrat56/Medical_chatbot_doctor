from motor.motor_asyncio import AsyncIOMotorClient
import os

#MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
#DB_NAME = "chatbot_db"

client = AsyncIOMotorClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("DB_NAME", "chatbot_db")]

chat_sessions = db.chat_sessions
chat_messages = db.chat_messages
