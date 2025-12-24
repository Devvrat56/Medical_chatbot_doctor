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
from fpdf import FPDF

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
# DATABASE HELPERS
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
# CLINICAL SUMMARY HELPERS
# ======================================================

def get_patient_conversation_text():
    return "\n".join(
        msg["content"]
        for msg in st.session_state.llm_history
        if msg["role"] == "user"
    )


def generate_case_summary(raw_text):
    prompt = f"""
You are generating a DOCTOR-READY clinical case summary.

Use EXACT format:

Patient Summary:
- Age:
- Gender:
- Key Symptoms:
- Duration:
- Red Flags (None / Mild / Moderate / Severe):
- Suggested Diagnostic Tests (non-prescriptive):
- Guideline Reference:
- Clinical Note (2–3 lines)

Rules:
- Missing info → "Not provided"
- No diagnosis
- No prescription
- Guideline reference must be:
  NCCN Guidelines / WHO Clinical Guidance / ASCO-ESMO

Conversation:
{raw_text}
"""

    response = llm_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=300
    )

    return response.choices[0].message.content


def export_summary_to_pdf(summary_text, doctor_name, reg_id):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=11)

    for line in summary_text.split("\n"):
        pdf.multi_cell(0, 8, line)

    pdf.ln(10)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "Doctor Approval", ln=True)

    pdf.set_font("Arial", size=11)
    pdf.cell(0, 8, f"Doctor Name: {doctor_name}", ln=True)
    pdf.cell(0, 8, f"Registration ID: {reg_id or 'Not Provided'}", ln=True)
    pdf.cell(0, 8, f"Signed On: {datetime.now().strftime('%d %b %Y %H:%M')}", ln=True)

    path = f"/tmp/clinical_summary_{uuid.uuid4().hex}.pdf"
    pdf.output(path)
    return path

# ======================================================
# ROLE SELECTION
# ======================================================

if "user_type" not in st.session_state:

    st.title("💉 Oncology Assistant Chatbot")
    st.subheader("Access Mode")

    doc_id = st.text_input(
        "Enter Doctor ID (leave empty if you are a patient)",
        type="password"
    )

    if st.button("Continue"):

        if doc_id == DOCTOR_ID:
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
# CHAT FUNCTION
# ======================================================

def ask_bot(user_input):
    save_message(st.session_state.session_id, "user", user_input)
    st.session_state.llm_history.append(
        {"role": "user", "content": user_input}
    )

    response = llm_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=st.session_state.llm_history,
        temperature=0.1 if st.session_state.user_type == "doctor" else 0.3,
        max_tokens=700
    )

    reply = response.choices[0].message.content

    save_message(st.session_state.session_id, "assistant", reply)
    st.session_state.llm_history.append(
        {"role": "assistant", "content": reply}
    )
    st.session_state.ui_history.append(("Bot", reply))

# ======================================================
# UI
# ======================================================

st.title("💬 Oncology Assistant")
st.caption(f"Mode: **{st.session_state.user_type.upper()}**")

left, right = st.columns([1, 2])

with left:
    st.subheader("📄 Upload Medical Report")

    file = st.file_uploader(
        "Upload PDF or Image",
        type=["pdf", "png", "jpg", "jpeg"]
    )

    if file:
        path = os.path.join(tempfile.gettempdir(), file.name)
        with open(path, "wb") as f:
            f.write(file.read())

        text = extract_text_from_file(path, langs=["en"], gpu=False)
        st.text_area("Extracted Text", text, height=250)

        if st.button("Analyze Report"):
            ask_bot(f"Interpret this report safely:\n{text}")

with right:
    st.subheader("💬 Chat")

    msg = st.text_input("Type your question")
    if st.button("Send") and msg.strip():
        st.session_state.ui_history.append(("You", msg))
        ask_bot(msg)

    st.subheader("Conversation")
    for sender, m in st.session_state.ui_history:
        st.markdown(f"**{sender}:** {m}")

    # ==================================================
    # DOCTOR-ONLY SIGNED SUMMARY
    # ==================================================

    if st.session_state.user_type == "doctor":
        st.divider()
        st.subheader("🩺 Doctor-Approved Clinical Summary")

        if "editable_summary" not in st.session_state:
            st.session_state.editable_summary = ""

        if st.button("Generate Clinical Summary"):
            st.session_state.editable_summary = generate_case_summary(
                get_patient_conversation_text()
            )

        st.text_area(
            "Editable Summary",
            st.session_state.editable_summary,
            height=300,
            key="editable_summary"
        )

        doctor_name = st.text_input("Doctor Name (Signature)")
        reg_id = st.text_input("Medical Registration ID (optional)")

        if st.button("📄 Sign & Export PDF"):
            pdf_path = export_summary_to_pdf(
                st.session_state.editable_summary,
                doctor_name,
                reg_id
            )

            with open(pdf_path, "rb") as f:
                st.download_button(
                    "Download Signed Clinical Summary",
                    f,
                    file_name="doctor_approved_summary.pdf",
                    mime="application/pdf"
                )
