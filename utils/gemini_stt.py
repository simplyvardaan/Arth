import os
import sys
from google import genai
from google.genai import types
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()


def stt(audio_path, mime_type="audio/wav"):
    """
    Transcribe audio from a WAV file using Gemini API.
    Supports Hindi, English, and Hinglish.

    Args:
        audio_path: Path to the recorded WAV file.
        mime_type: MIME type of the audio file.

    Returns:
        Transcribed text string, or "" on failure.
    """
    if not os.path.exists(audio_path):
        print(f"[ERROR] STT Error: Audio file not found at {audio_path}")
        return ""

    try:
        # Client automatically reads GEMINI_API_KEY from environment
        client = genai.Client()
        
        print(f"[Gemini STT] Sending audio ({mime_type}) for transcription...")
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[
                types.Part.from_bytes(data=audio_data, mime_type=mime_type),
                "Please transcribe the speech in this audio file. Return only the transcription, with no other text, comments, or punctuation details. If the speaker is speaking in Hindi or Hinglish, transcribe it exactly as spoken."
            ]
        )
        
        transcript = response.text
        if transcript:
            transcript = transcript.strip()
            # Safe print
            try:
                print(f"[Gemini STT] Success: \"{transcript}\"")
            except Exception:
                print(f"[Gemini STT] Success: \"{transcript.encode('ascii', 'replace').decode()}\"")
            return transcript
        else:
            print("[Gemini STT] Error: Empty transcription response")
            return ""

    except Exception as e:
        print(f"[ERROR] Gemini STT unexpected error: {e}")
        return ""
