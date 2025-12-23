import streamlit as st
from groq import Groq
from context import init_conversation as PATIENT_CONTEXT
from context_2 import init_conversation as DOCTOR_CONTEXT
from core.ocr_engine import extract_text_from_file
from pdf_reference_router import PDFReferenceRouter

import os
import uuid
import tempfile
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# ======================================================
# CONFIGURATION
# ======================================================

load_dotenv()

st.set_page_config(
    page_title="Oncology Assistant Chatbot",
    page_icon="💉",
    layout="wide"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

DOCTOR_ID = "dev_doc24"

llm_client = Groq(api_key=GROQ_API_KEY)
mongo_client = MongoClient(MONGO_URI)

db = mongo_client["onco_chatbot"]
chat_sessions = db.chat_sessions
chat_messages = db.chat_messages

pdf_router = PDFReferenceRouter(pdf_folder="pdfs")

# ======================================================
# DATABASE FUNCTIONS
# ======================================================

def create_session(user_type):
    session_id = str(uuid.uuid4())
    chat_sessions.insert_one({
        "_id": session_id,
        "user_type": user_type,
        "created_at": datetime.utcnow(),
        "last_active": datetime.utcnow()
    })
    return session_id


def save_message(session_id, role, content):
    chat_messages.insert_one({
        "session_id": session_id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow()
    })

    chat_sessions.update_one(
        {"_id": session_id},
        {"$set": {"last_active": datetime.utcnow()}}
    )

# ======================================================
# 🔹 NEW: CLINICAL CASE SUMMARY FUNCTIONS (DOCTOR MODE)
# ======================================================

def get_patient_conversation_text():
    """
    Extract ONLY user-provided clinical information.
    """
    texts = []
    for msg in st.session_state.llm_history:
        if msg["role"] == "user":
            texts.append(msg["content"])
    return "\n".join(texts)


def generate_case_summary(raw_conversation_text):
    """
    Generate structured doctor-ready case summary.
    """
    prompt = f"""
You are a clinical assistant.

From the conversation below, generate a STRUCTURED clinical case summary.

Use EXACTLY this format:

Patient Summary:
- Age:
- Gender:
- Key Symptoms:
- Duration:
- Red Flags (None / Mild / Moderate / Severe):
- Suggested Diagnostic Tests (non-prescriptive, guideline-based):
- Clinical Note (2–3 lines, professional medical language)

Rules:
- If information is missing, write "Not provided"
- Do NOT diagnose
- Do NOT prescribe
- Be concise

Conversation:
{raw_conversation_text}
"""

    response = llm_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=300
    )

    return response.choices[0].message.content

# ======================================================
# ROLE SELECTION (LOCKED PER SESSION)
# ======================================================

if "user_type" not in st.session_state:

    st.title("💉 Oncology Assistant Chatbot")
    st.subheader("Access Mode")

    id_name = st.text_input(
        "Enter Doctor ID (leave empty if you are a patient)",
        type="password"
    )

    if st.button("Continue"):

        if id_name == DOCTOR_ID:
            st.session_state.user_type = "doctor"
            st.session_state.system_prompt = DOCTOR_CONTEXT
            st.success("Doctor mode activated")
        else:
            st.session_state.user_type = "patient"
            st.session_state.system_prompt = PATIENT_CONTEXT
            st.info("Patient mode activated")

        st.session_state.session_id = create_session(
            st.session_state.user_type
        )

        st.session_state.llm_history = [
            {"role": "system", "content": st.session_state.system_prompt}
        ]
        st.session_state.ui_history = []

        st.rerun()

    st.stop()

# ======================================================
# LLM INTERACTION
# ======================================================

def ask_bot(user_input):

    save_message(st.session_state.session_id, "user", user_input)
    st.session_state.llm_history.append({
        "role": "user",
        "content": user_input
    })

    temperature = 0.1 if st.session_state.user_type == "doctor" else 0.3

    response = llm_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=st.session_state.llm_history,
        temperature=temperature,
        max_tokens=700
    )

    reply = response.choices[0].message.content

    save_message(st.session_state.session_id, "assistant", reply)
    st.session_state.llm_history.append({
        "role": "assistant",
        "content": reply
    })
    st.session_state.ui_history.append(("Bot", reply))

    return reply

# ======================================================
# UI
# ======================================================

st.title("💬 Oncology Assistant")
st.caption(f"Mode: **{st.session_state.user_type.upper()}**")

left, right = st.columns([1, 2])

# ------------------- FILE UPLOAD -------------------

with left:
    st.subheader("📄 Upload Medical Report")

    uploaded_file = st.file_uploader(
        "Upload PDF or Image",
        type=["pdf", "png", "jpg", "jpeg"]
    )

    if uploaded_file:
        temp_path = os.path.join(
            tempfile.gettempdir(),
            uploaded_file.name
        )

        with open(temp_path, "wb") as f:
            f.write(uploaded_file.read())

        extracted_text = extract_text_from_file(
            temp_path,
            langs=["en"],
            gpu=False
        )

        st.text_area(
            "Extracted Text",
            extracted_text,
            height=250
        )

        if st.button("Analyze Report"):
            st.session_state.ui_history.append(
                ("You", "[Uploaded a medical report]")
            )

            ask_bot(
                f"""
The following medical report was uploaded.
Interpret it safely and clearly.

Report Content:
{extracted_text}
"""
            )

# ------------------- CHAT + DOCTOR SUMMARY -------------------

with right:
    st.subheader("💬 Chat")

    user_message = st.text_input("Type your question")

    if st.button("Send") and user_message.strip():
        st.session_state.ui_history.append(("You", user_message))
        ask_bot(user_message)

        relevant_pdfs = pdf_router.find_relevant_pdfs(user_message)
        if relevant_pdfs:
            st.markdown("### 📚 Related Reference PDFs")
            for link in pdf_router.build_streamlit_links(relevant_pdfs):
                st.markdown(link)

    st.subheader("Conversation")
    for sender, message in st.session_state.ui_history:
        if sender == "You":
            st.markdown(f"🧑 **You:** {message}")
        else:
            st.markdown(f"🤖 **Bot:** {message}")

    # ==================================================
    # 🩺 DOCTOR-ONLY AUTO CASE SUMMARY
    # ==================================================

    if st.session_state.user_type == "doctor":
        st.divider()
        st.subheader("🩺 Auto-Generated Case Summary")

        if st.button("Generate Clinical Summary"):
            convo_text = get_patient_conversation_text()
            summary = generate_case_summary(convo_text)

            st.text_area(
                "Doctor-Ready Case Summary",
                summary,
                height=260
            )
            save_message(
                st.session_state.session_id,
                "assistant",
                f"Generated Clinical Summary:\n\n{summary}"
            )