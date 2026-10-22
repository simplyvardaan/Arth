import os
import sys
import threading
from dotenv import load_dotenv
from utils.elevenlabs_tts import speak_text, update_voice_clone
from utils.gemini_stt import stt

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()


def main_pipeline(audio_path, shared_state):
    """
    Process recorded audio through the Arth voice pipeline:
    STT (Gemini 3.5 Flash Lite) → LLM (Arth Realtime Payment & Vision Engine) → TTS (ElevenLabs / Fallback)

    Voice cloning runs concurrently in the background while the LLM is thinking
    to reduce overall roundtrip latency.

    Args:
        audio_path:   Path to the recorded audio WAV file.
        shared_state: Shared state dict (see arth.py for all keys).
    """
    conversation = shared_state.get("current_conversation")

    if not conversation:
        print("[WARN]  No conversation context set in shared_state.")
        return

    # Grab and immediately clear the captured frame path so stale frames
    # don't accidentally get reused on the next pipeline call.
    image_path = shared_state.pop("current_frame_path", None)

    # Step 1: Speech-to-Text via Gemini 3.5 Flash Lite
    try:
        user_text = stt(audio_path)
    except Exception as e:
        print(f"[ERROR] STT Error: {e}")
        return

    if not user_text or not user_text.strip():
        print("[WARN]  No transcription detected, skipping.")
        return

    try:
        print(f"[USER] User: {user_text}")
    except Exception:
        print(f"[USER] User: {user_text.encode('ascii', 'replace').decode()}")

    if image_path:
        print(f"[CAMERA] Payment Vision frame attached: {image_path}")

    # Step 2: LLM Generation via Arth Payment Engine
    response = ""
    try:
        print("[ARTH] Processing financial request...")
        response = conversation.send_message(user_text, image_path=image_path)
        try:
            print(f"[ARTH] Arth: {response}")
        except Exception:
            print(f"[ARTH] Arth: {response.encode('ascii', 'replace').decode()}")
    except Exception as e:
        print(f"[ERROR] LLM Error: {e}")
        return

    # Step 3: Instant TTS Playback
    speak_text(response, shared_state)
