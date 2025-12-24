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
from dotenv import load_dotenv
from fpdf import FPDF

from database.local_db import (
    init_db,
    create_session,
    save_message
)

# ----------------------------------
# CONFIG
# ----------------------------------
load_dotenv()
init_db()

st.set_page_config(
    page_title="Oncology Assistant Chatbot",
    page_icon="💉",
    layout="wide"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DOCTOR_ID = "dev_doc24"

llm_client = Groq(api_key=GROQ_API_KEY)
pdf_router = PDFReferenceRouter(pdf_folder="pdfs")

# ----------------------------------
# SESSION INIT
# ----------------------------------
if "user_type" not in st.session_state:

    st.title("💉 Oncology Assistant Chatbot")
    st.subheader("Access Mode")

    doc_id = st.text_input("Enter Doctor ID (optional)", type="password")

    if st.button("Continue"):

        if doc_id == DOCTOR_ID:
            st.session_state.user_type = "doctor"
            st.session_state.system_prompt = DOCTOR_CONTEXT
            st.success("Doctor mode activated")
        else:
            st.session_state.user_type = "patient"
            st.session_state.system_prompt = PATIENT_CONTEXT
            st.info("Patient mode activated")

        session_id = str(uuid.uuid4())
        create_session(session_id, st.session_state.user_type)

        st.session_state.session_id = session_id
        st.session_state.llm_history = [
            {"role": "system", "content": st.session_state.system_prompt}
        ]
        st.session_state.ui_history = []

        st.rerun()

    st.stop()

# ----------------------------------
# BOT FUNCTION
# ----------------------------------
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


# ----------------------------------
# CLINICAL SUMMARY
# ----------------------------------
def get_patient_text():
    return "\n".join(
        msg["content"]
        for msg in st.session_state.llm_history
        if msg["role"] == "user"
    )


def generate_case_summary(text):
    prompt = f"""
Generate a DOCTOR-READY clinical summary.

Format:
Patient Summary:
- Age:
- Gender:
- Symptoms:
- Duration:
- Red Flags:
- Suggested Tests:
- Guideline Reference (NCCN / WHO / ASCO-ESMO):
- Clinical Note:

Conversation:
{text}
"""

    response = llm_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=300
    )

    return response.choices[0].message.content


def export_pdf(summary, doctor, reg_id):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)

    for line in summary.split("\n"):
        pdf.multi_cell(0, 8, line)

    pdf.ln(5)
    pdf.cell(0, 8, f"Doctor: {doctor}", ln=True)
    pdf.cell(0, 8, f"Registration ID: {reg_id}", ln=True)
    pdf.cell(0, 8, f"Signed: {datetime.now().strftime('%d %b %Y')}", ln=True)

    path = f"/tmp/summary_{uuid.uuid4().hex}.pdf"
    pdf.output(path)
    return path


# ----------------------------------
# UI
# ----------------------------------
st.title("💬 Oncology Assistant")
st.caption(f"Mode: {st.session_state.user_type.upper()}")

left, right = st.columns([1, 2])

with left:
    st.subheader("📄 Upload Medical Report")

    file = st.file_uploader("Upload PDF / Image", type=["pdf", "png", "jpg"])

    if file:
        path = os.path.join(tempfile.gettempdir(), file.name)
        with open(path, "wb") as f:
            f.write(file.read())

        text = extract_text_from_file(path)
        st.text_area("Extracted Text", text, height=200)

        if st.button("Analyze Report"):
            ask_bot(f"Analyze this safely:\n{text}")

with right:
    st.subheader("💬 Chat")

    msg = st.text_input("Ask a question")
    if st.button("Send") and msg.strip():
        st.session_state.ui_history.append(("You", msg))
        ask_bot(msg)

    for sender, m in st.session_state.ui_history:
        st.markdown(f"**{sender}:** {m}")

    if st.session_state.user_type == "doctor":
        st.divider()
        st.subheader("🩺 Clinical Summary")

        if "summary" not in st.session_state:
            st.session_state.summary = ""

        if st.button("Generate Summary"):
            st.session_state.summary = generate_case_summary(
                get_patient_text()
            )

        st.text_area("Editable Summary", st.session_state.summary, height=300)

        doctor = st.text_input("Doctor Name")
        reg_id = st.text_input("Registration ID")

        if st.button("Export PDF"):
            pdf_path = export_pdf(
                st.session_state.summary,
                doctor,
                reg_id
            )
            with open(pdf_path, "rb") as f:
                st.download_button(
                    "Download PDF",
                    f,
                    file_name="clinical_summary.pdf"
                )
