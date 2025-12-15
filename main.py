import streamlit as st
from groq import Groq
from context import init_conversation
from core.ocr_engine import extract_text_from_file
import tempfile
import os
import uuid
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# ---------------------------- CONFIG ----------------------------

st.set_page_config(
    page_title="Oncology Assistant Chatbot",
    page_icon="💉",
    layout="wide"
)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------------------- MONGODB CONFIG ----------------------------

mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client["onco_chatbot"]
chat_sessions = db.chat_sessions
chat_messages = db.chat_messages


def create_new_session():
    session_id = str(uuid.uuid4())
    session_data = {
        "_id": session_id,
        "created_at": datetime.utcnow(),
        "last_active": datetime.utcnow(),
        "status": "active"
    }
    chat_sessions.insert_one(session_data)
    return session_id


def save_message(session_id, role, message):
    chat_messages.insert_one({
        "session_id": session_id,
        "role": role,
        "message": message,
        "timestamp": datetime.utcnow()
    })

    chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"last_active": datetime.utcnow()}}
    )


def load_conversation(session_id):
    cursor = chat_messages.find(
        {"session_id": session_id}
    ).sort("timestamp", 1)

    history = [{"role": "system", "content": init_conversation}]
    display = []

    for msg in cursor:
        history.append({
            "role": msg["role"],
            "content": msg["message"]
        })

        sender = "You" if msg["role"] == "user" else "Bot"
        display.append((sender, msg["message"]))

    return history, display


# ---------------------------- SESSION INIT ----------------------------

if "session_id" not in st.session_state:
    st.session_state.session_id = create_new_session()

if "history" not in st.session_state:
    st.session_state.history, st.session_state.chat_display = load_conversation(
        st.session_state.session_id
    )

# ---------------------------- CHATBOT FUNCTION ----------------------------

def ask_onco_bot(message):

    # Save user message
    save_message(st.session_state.session_id, "user", message)

    st.session_state.history.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=st.session_state.history,
        temperature=0.2,
        max_tokens=600
    )

    reply = response.choices[0].message.content

    # Save assistant reply
    save_message(st.session_state.session_id, "assistant", reply)

    st.session_state.history.append({"role": "assistant", "content": reply})
    st.session_state.chat_display.append(("Bot", reply))

    return reply


# ---------------------------- STREAMLIT UI ----------------------------

st.title("💉 Oncology Assistant Chatbot")
st.write("Upload medical reports (PDF/Image) or ask questions directly.")

left, right = st.columns([1, 2])

with left:
    st.subheader("📄 Upload Report")

    uploaded = st.file_uploader(
        "Upload PDF or Image Report",
        type=["pdf", "png", "jpg", "jpeg"]
    )

    if uploaded is not None:
        st.info("Extracting text from file... Please wait.")

        temp_path = os.path.join(tempfile.gettempdir(), uploaded.name)

        with open(temp_path, "wb") as f:
            f.write(uploaded.read())

        extracted_text = extract_text_from_file(temp_path, langs=["en"], gpu=False)

        st.subheader("📄 Extracted Text")
        st.text_area("Extracted Content:", extracted_text, height=250)

        if st.button("🔍 Analyse Report"):
            st.session_state.chat_display.append(("You", "[Uploaded a medical report]"))

            reply = ask_onco_bot(
                f"The patient uploaded this medical report. Please interpret it:\n\n{extracted_text}"
            )

            st.success("Interpretation Ready!")


with right:
    st.subheader("💬 Chat with Oncology Assistant")

    user_input = st.text_input("Type your message here:")

    if st.button("Send"):
        if user_input.strip():
            st.session_state.chat_display.append(("You", user_input))
            ask_onco_bot(user_input)

    st.subheader("Conversation")
    for sender, msg in st.session_state.chat_display:
        if sender == "You":
            st.markdown(f"🧑 **You:** {msg}")
        else:
            st.markdown(f"🤖 **Bot:** {msg}")
