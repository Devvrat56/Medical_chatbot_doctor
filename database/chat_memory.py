from datetime import datetime
from database import chat_messages, chat_sessions

async def save_message(session_id: str, role: str, message: str):
    chat_data = {
        "session_id": session_id,
        "role": role,
        "message": message,
        "timestamp": datetime.utcnow()
    }

    await chat_messages.insert_one(chat_data)

    await chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"last_active": datetime.utcnow()}}
    )


async def get_conversation(session_id: str, limit: int = 20):
    cursor = chat_messages.find(
        {"session_id": session_id}
    ).sort("timestamp", 1).limit(limit)

    history = []
    async for msg in cursor:
        history.append({
            "role": msg["role"],
            "content": msg["message"]
        })

    return history
