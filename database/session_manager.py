import uuid
from datetime import datetime
from database import chat_sessions

async def create_session(user_id: str):
    session_id = str(uuid.uuid4())

    session_data = {
        "_id": session_id,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "last_active": datetime.utcnow(),
        "status": "active"
    }

    await chat_sessions.insert_one(session_data)
    return session_id


async def update_session_activity(session_id: str):
    await chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"last_active": datetime.utcnow()}}
    )
