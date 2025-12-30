import streamlit as st
from groq import Groq
import os
import uuid
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import io

# Your custom modules — change paths according to your project structure
from context import init_conversation as PATIENT_CONTEXT_FUNC
from context_2 import init_conversation as DOCTOR_CONTEXT_FUNC
from core.ocr_engine import extract_text_from_file
from local_db import (
    init_db,
    create_session,
    save_message
)
from streamlit_mic_recorder import mic_recorder

# ────────────────────────────────────────────────────────────────
# CONFIG & INITIAL SETUP
# ────────────────────────────────────────────────────────────────

load_dotenv()
init_db()

st.set_page_config(
    page_title="Oncology Assistant",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

DOCTOR_ID = "dev_doc24"  # ← change in production!

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    st.error("GROQ_API_KEY not found in .env file")
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

# ────────────────────────────────────────────────────────────────
# SESSION STATE DEFAULTS
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
# VERY IMPORTANT: define ask_bot function EARLY
# ────────────────────────────────────────────────────────────────

def ask_bot(user_message: str):
    """
    Send user message to LLM, get response and append to history
    """
    # Quick safety guardrail
    dangerous_keywords = ["dose", "dosage", "how much", "treatment plan", "cure", "prescribe"]
    if any(kw in user_message.lower() for kw in dangerous_keywords):
        reply = (
            "I'm not allowed to give dosages, drug names "
            "or specific treatment recommendations.\n\n"
            "Please discuss this with your oncologist."
        )
        st.session_state.ui_history.append(("Assistant", reply))
        save_message(st.session_state.session_id, "assistant", reply)
        return

    # Save user message
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
        st.error(f"Error contacting AI service: {str(e)}")


# ────────────────────────────────────────────────────────────────
# LOGIN / MODE SELECTION SCREEN
# ────────────────────────────────────────────────────────────────

if st.session_state.user_type is None:
    st.title("🩺 Oncology Assistant")
    st.markdown("### Supportive information for people affected by cancer")

    selected_lang = st.selectbox("Language", list(LANGUAGES.keys()), index=0)
    st.session_state.lang = LANGUAGES[selected_lang]

    st.divider()

    st.subheader("🧬 Cancer Situation (helps us answer better)")

    col1, col2 = st.columns(2)
    with col1:
        cancer_type = st.text_input(
            "Type of Cancer",
            placeholder="Breast cancer, Lung cancer, CML...",
        ).strip()

    with col2:
        cancer_stage = st.selectbox(
            "Stage",
            ["Unknown", "Stage 0", "Stage I", "Stage II",
             "Stage III", "Stage IV", "Recurrent", "Not applicable"]
        )

    st.markdown("---")
    doc_id = st.text_input("Doctor ID (leave empty if patient/family)", type="password")

    if st.button("Start Conversation", type="primary", use_container_width=True):
        is_doctor = doc_id.strip() == DOCTOR_ID

        st.session_state.cancer_type = cancer_type if cancer_type else "Not specified"
        st.session_state.cancer_stage = cancer_stage
        st.session_state.user_type = "doctor" if is_doctor else "patient"

        base_context = DOCTOR_CONTEXT_FUNC() if is_doctor else PATIENT_CONTEXT_FUNC()

        context_add = f"""
<IMPORTANT_CONTEXT>
Cancer type: {st.session_state.cancer_type}
Stage: {st.session_state.cancer_stage}

Always relate answers to this context.
Keep responses short, warm, supportive, non-alarming.
</IMPORTANT_CONTEXT>
"""

        st.session_state.system_prompt = base_context + "\n\n" + context_add

        session_id = str(uuid.uuid4())
        create_session(session_id, st.session_state.user_type)

        st.session_state.session_id = session_id
        st.session_state.llm_history = [
            {"role": "system", "content": st.session_state.system_prompt}
        ]
        st.session_state.ui_history = []

        st.success("Session started!")
        st.rerun()

    st.stop()

# ────────────────────────────────────────────────────────────────
# MAIN INTERFACE
# ────────────────────────────────────────────────────────────────

st.title("🩺 Oncology Assistant")
st.caption(
    f"**{st.session_state.cancer_type}**  •  "
    f"**{st.session_state.cancer_stage}**  •  "
    f"{st.session_state.user_type.title()} mode"
)

left, right = st.columns([1, 2.3])

# ── LEFT: Upload Medical Report ──
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
                ask_bot(f"Please explain this report in simple terms:\n\n{text}")
        finally:
            try:
                os.unlink(path)
            except:
                pass

# ── RIGHT: Chat ──
with right:
    st.subheader("💬 Conversation")

    # Scrollable messages container
    chat_container = st.container(height=520)

    with chat_container:
        for role, msg in st.session_state.ui_history:
            if role == "You":
                st.markdown(f"**You:** {msg}")
            else:
                st.markdown(f"**Assistant:** {msg}")

    # Auto-scroll attempt (works in many cases)
    st.markdown(
        """
        <script>
        var elem = window.parent.document.querySelector('.stApp > div');
        if (elem) elem.scrollTop = elem.scrollHeight;
        </script>
        """,
        unsafe_allow_html=True
    )

    # Input area — always at bottom
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

    # Voice input (optional)
    st.markdown("**Voice input**")
    audio = mic_recorder(
        format="webm",
        start_prompt="🎤 Record",
        stop_prompt="⏹",
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
                st.error(f"Voice → text failed: {str(e)}")