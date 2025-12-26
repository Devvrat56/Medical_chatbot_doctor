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
import io

from local_db import (
    init_db,
    create_session,
    save_message
)

# 🎤 MIC + AUDIO
from streamlit_mic_recorder import mic_recorder
from pydub import AudioSegment
import speech_recognition as sr

# ----------------------------------
# INITIAL SETUP
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
# LANGUAGE CONFIG
# ----------------------------------
LANGUAGES = {
    "English": "en",
    "Hindi": "hi",
    "Punjabi": "pa",
    "German": "de",
    "Swedish": "sv"
}

if "lang" not in st.session_state:
    st.session_state.lang = "en"

# ----------------------------------
# SESSION INIT
# ----------------------------------
if "user_type" not in st.session_state:

    st.title("💉 Oncology Assistant Chatbot")
    st.subheader("Access Mode")

    selected_lang = st.selectbox("🌐 Output Language", LANGUAGES.keys())
    st.session_state.lang = LANGUAGES[selected_lang]

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
# TRANSLATION
# ----------------------------------
def translate_text(text, target_lang):
    if target_lang == "en":
        return text

    prompt = f"""
Translate the following medical content accurately.
Do NOT add or remove information.
Preserve medical terminology.

Target language: {target_lang}

Text:
{text}
"""

    response = llm_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=900
    )

    return response.choices[0].message.content

# ----------------------------------
# 🎤 SPEECH → TEXT (FFMPEG PIPELINE)
# ----------------------------------
def transcribe_audio_bytes(audio_bytes):
    recognizer = sr.Recognizer()

    # Decode browser audio (WebM/Opus) using FFmpeg
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))

    # Convert to SpeechRecognition-compatible format
    audio = audio.set_frame_rate(16000).set_channels(1)

    wav_io = io.BytesIO()
    audio.export(wav_io, format="wav")
    wav_io.seek(0)

    with sr.AudioFile(wav_io) as source:
        audio_data = recognizer.record(source)

    try:
        return recognizer.recognize_google(audio_data)
    except sr.UnknownValueError:
        return "Sorry, I could not understand the audio."
    except sr.RequestError:
        return "Speech recognition service unavailable."

# ----------------------------------
# CHATBOT CORE
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

    raw_reply = response.choices[0].message.content
    reply = translate_text(raw_reply, st.session_state.lang)

    save_message(st.session_state.session_id, "assistant", raw_reply)

    st.session_state.llm_history.append(
        {"role": "assistant", "content": raw_reply}
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
Generate a DOCTOR-READY oncology clinical summary.

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
        max_tokens=350
    )

    return translate_text(
        response.choices[0].message.content,
        st.session_state.lang
    )

# ----------------------------------
# PDF EXPORT
# ----------------------------------
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

st.session_state.lang = LANGUAGES[
    st.selectbox("🌐 Output Language", LANGUAGES.keys())
]

left, right = st.columns([1, 2])

# LEFT PANEL
with left:
    st.subheader("📄 Upload Medical Report")

    file = st.file_uploader("Upload PDF / Image", type=["pdf", "png", "jpg"])

    if file:
        path = os.path.join(tempfile.gettempdir(), file.name)
        with open(path, "wb") as f:
            f.write(file.read())

        extracted_text = extract_text_from_file(path)
        st.text_area("Extracted Text", extracted_text, height=200)

        if st.button("Analyze Report"):
            ask_bot(f"Analyze this safely:\n{extracted_text}")

# RIGHT PANEL
with right:
    st.subheader("💬 Chat")

    msg = st.text_input("Ask a question")

    st.markdown("🎤 **Or speak your question**")
    audio = mic_recorder(
        start_prompt="🎙 Start Recording",
        stop_prompt="⏹ Stop Recording",
        just_once=True
    )

    if audio:
        with st.spinner("Transcribing..."):
            spoken_text = transcribe_audio_bytes(audio["bytes"])
            st.success(f"🗣 You said: {spoken_text}")
            st.session_state.ui_history.append(("You (Voice)", spoken_text))
            ask_bot(spoken_text)

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
