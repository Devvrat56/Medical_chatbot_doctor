import streamlit as st
from groq import Groq
import os
import uuid
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import io

# Your custom modules
from context import init_conversation as PATIENT_CONTEXT_FUNC
from context_2 import init_conversation as DOCTOR_CONTEXT_FUNC
from core.ocr_engine import extract_text_from_file
from local_db import init_db, create_session, save_message
from streamlit_mic_recorder import mic_recorder

# ────────────────────────────────────────────────────────────────
# CONFIG
# ────────────────────────────────────────────────────────────────

load_dotenv()
init_db()

st.set_page_config(
    page_title="Oncology Assistant",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

DOCTOR_ID = "dev_doc24"

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    st.error("GROQ_API_KEY not found in .env")
    st.stop()

llm_client = Groq(api_key=GROQ_API_KEY)

whisper_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

LANGUAGES = {
    "English": "en",
    "हिन्दी": "hi",
    "ਪੰਜਾਬੀ": "pa",
    "Deutsch": "de",
    "Svenska": "sv"
}

# Fake hospital contact details (for demo/safety)
FAKE_EMERGENCY_NUMBER = "+91-214-352-354-235"
FAKE_APPOINTMENT_EMAIL = "dvvratshuk@softsensor.ai"

# ────────────────────────────────────────────────────────────────
# SESSION STATE
# ────────────────────────────────────────────────────────────────

defaults = {
    "user_type": None,
    "cancer_type": "Not specified",
    "cancer_stage": "Unknown",
    "lang": "en",
    "session_id": None,
    "llm_history": [],
    "ui_history": [],
    "system_prompt": "",
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ────────────────────────────────────────────────────────────────
# EARLY DEFINITION - ask_bot function
# ────────────────────────────────────────────────────────────────

def ask_bot(user_message: str):
    # ── Special handling for appointment / emergency / contact requests ──
    contact_keywords = [
        "appointment", "book", "schedule", "make appointment",
        "contact", "call", "phone", "number", "email", "emergency",
        "urgent", "hospital contact", "doctor contact", "help line"
    ]

    if any(kw in user_message.lower() for kw in contact_keywords):
        reply = (
            "I understand you would like to book an appointment or contact the hospital — "
            "that's a really important step.\n\n"
            "I cannot make bookings or calls directly, but you can reach out here:\n\n"
            f"• **Emergency / Urgent help**: Call {FAKE_EMERGENCY_NUMBER}\n"
            f"• **Appointments & general inquiries**: Email {FAKE_APPOINTMENT_EMAIL}\n\n"
            "The team will assist you quickly. Would you like help preparing what to tell them?"
        )
        st.session_state.ui_history.append(("Assistant", reply))
        save_message(st.session_state.session_id, "assistant", reply)
        return

    # ── Normal dangerous medical questions guardrail ──
    dangerous = ["dose", "dosage", "how much", "treatment plan", "cure", "prescribe"]
    if any(w in user_message.lower() for w in dangerous):
        reply = (
            "I'm not allowed to give dosages, drug names "
            "or specific treatment recommendations.\n\n"
            "Please discuss this with your oncologist."
        )
        st.session_state.ui_history.append(("Assistant", reply))
        save_message(st.session_state.session_id, "assistant", reply)
        return

    # Normal flow
    save_message(st.session_state.session_id, "user", user_message)
    st.session_state.llm_history.append({"role": "user", "content": user_message})

    try:
        response = llm_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=st.session_state.llm_history,
            temperature=0.45,
            max_tokens=320,
            top_p=0.9
        )
        answer = response.choices[0].message.content.strip()

        save_message(st.session_state.session_id, "assistant", answer)
        st.session_state.llm_history.append({"role": "assistant", "content": answer})
        st.session_state.ui_history.append(("Assistant", answer))

    except Exception as e:
        st.error(f"AI service error: {str(e)}")

# ────────────────────────────────────────────────────────────────
# LOGIN SCREEN
# ────────────────────────────────────────────────────────────────

if st.session_state.user_type is None:
    st.title("🩺 Oncology Assistant")
    st.markdown("### Supportive information for people affected by cancer")

    selected_lang = st.selectbox("Language", list(LANGUAGES.keys()), index=0)
    st.session_state.lang = LANGUAGES[selected_lang]

    st.divider()

    st.subheader("About your situation (helps us give better answers)")

    c1, c2 = st.columns(2)
    with c1:
        cancer_type = st.text_input("Type of Cancer", placeholder="e.g. Breast, Lung, Leukemia...").strip()
    with c2:
        cancer_stage = st.selectbox("Stage", [
            "Unknown", "Stage 0", "Stage I", "Stage II",
            "Stage III", "Stage IV", "Recurrent", "Not applicable"
        ])

    st.markdown("---")
    doc_id = st.text_input("Doctor ID (leave empty if patient/family)", type="password")

    if st.button("Start Conversation", type="primary"):
        is_doctor = doc_id.strip() == DOCTOR_ID

        st.session_state.cancer_type = cancer_type or "Not specified"
        st.session_state.cancer_stage = cancer_stage
        st.session_state.user_type = "doctor" if is_doctor else "patient"

        base = DOCTOR_CONTEXT_FUNC() if is_doctor else PATIENT_CONTEXT_FUNC()

        extra_context = f"""
<IMPORTANT>
Cancer type: {st.session_state.cancer_type}
Stage: {st.session_state.cancer_stage}
Always relate answers to this context.
Keep responses short, warm, supportive.
</IMPORTANT>
"""

        st.session_state.system_prompt = base + "\n\n" + extra_context

        sid = str(uuid.uuid4())
        create_session(sid, st.session_state.user_type)

        st.session_state.session_id = sid
        st.session_state.llm_history = [{"role": "system", "content": st.session_state.system_prompt}]
        st.session_state.ui_history = []

        st.success("Ready!")
        st.rerun()

    st.stop()

# ────────────────────────────────────────────────────────────────
# MAIN UI
# ────────────────────────────────────────────────────────────────

st.title("🩺 Oncology Assistant")
st.caption(f"{st.session_state.cancer_type} • {st.session_state.cancer_stage} • {st.session_state.user_type.title()} mode")

left, right = st.columns([1, 2.3])

# ── LEFT: Upload ──
with left:
    st.subheader("📋 Upload Medical Report")
    file = st.file_uploader("PDF or Image", type=["pdf", "png", "jpg", "jpeg"])

    if file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.name)[1]) as tmp:
            tmp.write(file.read())
            path = tmp.name

        try:
            text = extract_text_from_file(path)
            st.text_area("Extracted text", text, height=160)

            if st.button("Explain this report"):
                st.session_state.ui_history.append(("You", "[Report analysis request]"))
                ask_bot(f"Please explain this report in simple, patient-friendly language:\n\n{text}")
        finally:
            try:
                os.unlink(path)
            except:
                pass

# ── RIGHT: Chat ──
with right:
    st.subheader("💬 Conversation")

    chat_container = st.container(height=520)

    with chat_container:
        for role, msg in st.session_state.ui_history:
            if role == "You":
                st.markdown(f"**You:** {msg}")
            else:
                st.markdown(f"**Assistant:** {msg}")

    # Simple auto-scroll attempt
    st.markdown(
        """
        <script>
        const container = window.parent.document.querySelector('.stApp > div');
        if (container) container.scrollTop = container.scrollHeight;
        </script>
        """,
        unsafe_allow_html=True
    )

    # Input at bottom
    col_text, col_send = st.columns([6, 1])
    with col_text:
        user_input = st.text_input(
            "",
            placeholder="Ask anything about your situation...",
            label_visibility="collapsed",
            key="chat_input"
        )
    with col_send:
        if st.button("Send", use_container_width=True) and user_input.strip():
            st.session_state.ui_history.append(("You", user_input))
            ask_bot(user_input)
            st.rerun()

    # Voice input
    st.markdown("**Voice input**")
    audio = mic_recorder(
        format="webm",
        start_prompt="🎤 Record",
        stop_prompt="⏹ Stop",
        just_once=True
    )

    if audio and audio.get("bytes"):
        with st.spinner("Transcribing..."):
            try:
                audio_file = io.BytesIO(audio["bytes"])
                audio_file.name = "voice.webm"

                transcription = whisper_client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=audio_file,
                    language=st.session_state.lang,
                    response_format="text"
                ).strip()

                st.session_state.ui_history.append(("You (voice)", transcription))
                ask_bot(transcription)
                st.rerun()
            except Exception as e:
                st.error(f"Voice recognition failed: {str(e)}")