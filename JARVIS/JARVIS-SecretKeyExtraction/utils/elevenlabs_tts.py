import os
import sys
import time
import requests
import subprocess
import threading
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
# Only enable ElevenLabs if a real secret key starting with 'sk_' is configured
ELEVENLABS_ENABLED = bool(ELEVENLABS_API_KEY and ELEVENLABS_API_KEY.startswith("sk_"))


def update_voice_clone(audio_path, shared_state):
    """
    Clones/refines the speaker's voice from recorded audio files.
    Only runs if a valid ElevenLabs key (sk_...) is provided.
    """
    if not ELEVENLABS_ENABLED:
        # Silently skip voice cloning when ElevenLabs key is not an active secret key
        return

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY
    }

    # Initialize rolling audio samples list if not present
    if "user_audio_samples" not in shared_state:
        shared_state["user_audio_samples"] = []

    # Copy current audio file to a persistent path in temp
    os.makedirs("temp", exist_ok=True)
    persistent_path = os.path.join("temp", f"user_voice_{int(time.time())}.wav")
    
    try:
        import shutil
        shutil.copy(audio_path, persistent_path)
        shared_state["user_audio_samples"].append(persistent_path)
    except Exception as e:
        print(f"[WARN] Voice Cloning: Failed to save audio sample: {e}")
        return

    # Keep only the last 4 samples
    if len(shared_state["user_audio_samples"]) > 4:
        old_sample = shared_state["user_audio_samples"].pop(0)
        try:
            if os.path.exists(old_sample):
                os.remove(old_sample)
        except Exception:
            pass

    voice_id = shared_state.get("cloned_voice_id")

    try:
        files = []
        open_files = []
        for sample_path in shared_state["user_audio_samples"]:
            if os.path.exists(sample_path):
                f = open(sample_path, "rb")
                open_files.append(f)
                files.append(("files", (os.path.basename(sample_path), f, "audio/wav")))

        if not files:
            for f in open_files:
                f.close()
            return

        data = {
            "name": "User_Cloned_Voice",
            "description": "User voice sample clone"
        }

        if not voice_id:
            url = "https://api.elevenlabs.io/v1/voices/add"
            res = requests.post(url, headers=headers, data=data, files=files)
            if res.status_code == 200:
                new_voice_id = res.json().get("voice_id")
                if new_voice_id:
                    shared_state["cloned_voice_id"] = new_voice_id
                    print(f"[OK] Voice Cloning: Cloned voice ready (ID: {new_voice_id})")
        else:
            url = f"https://api.elevenlabs.io/v1/voices/{voice_id}/edit"
            res = requests.post(url, headers=headers, data=data, files=files)

        for f in open_files:
            f.close()

    except Exception:
        pass


def _fallback_free_tts(text):
    """
    High-quality free speech engine:
    1. Google Translate TTS (gTTS) in Hindi mode (pronounces Hindi/Hinglish/English naturally).
    2. Fallback to offline Windows SAPI5 (pyttsx3) if ffplay/network unavailable.
    """
    os.makedirs("temp", exist_ok=True)
    temp_mp3 = os.path.join("temp", "gtts_fallback.mp3")
    
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="hi", slow=False)
        tts.save(temp_mp3)
        
        # Play via ffplay
        subprocess.run(
            ["ffplay", "-autoexit", "-nodisp", temp_mp3],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        try:
            if os.path.exists(temp_mp3):
                os.remove(temp_mp3)
        except Exception:
            pass
        return
        
    except Exception:
        pass
        
    # Second-level fallback: Offline Windows SAPI5 (pyttsx3)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty('rate', 165)
        voices = engine.getProperty('voices')
        if len(voices) > 1:
            engine.setProperty('voice', voices[1].id)
        engine.say(text)
        engine.runAndWait()
    except Exception as ex:
        print(f"[ERROR] Offline TTS (pyttsx3) failed: {ex}")


def _tts_stream_and_play(text, voice_id):
    """ElevenLabs streaming TTS."""
    if not ELEVENLABS_ENABLED:
        _fallback_free_tts(text)
        return

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.8
        }
    }

    try:
        player_process = subprocess.Popen(
            ["ffplay", "-autoexit", "-nodisp", "-i", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        response = requests.post(url, json=data, headers=headers, stream=True)
        if response.status_code == 200:
            for chunk in response.iter_content(chunk_size=4096):
                if chunk and player_process.stdin:
                    player_process.stdin.write(chunk)
                    player_process.stdin.flush()
        else:
            raise Exception(f"Status {response.status_code}")
    except Exception:
        _fallback_free_tts(text)
    finally:
        try:
            if player_process.stdin:
                player_process.stdin.close()
            player_process.wait()
        except Exception:
            pass


def speak_text(text, shared_state):
    """
    Play spoken audio while safely managing mic mute flag.
    """
    if not text or not text.strip():
        return

    shared_state["bot_is_speaking"] = True
    try:
        if ELEVENLABS_ENABLED:
            voice_id = shared_state.get("cloned_voice_id", "pNInz6obpgDQGcFmaJgB")
            _tts_stream_and_play(text, voice_id)
        else:
            _fallback_free_tts(text)
    except Exception as e:
        print(f"[ERROR] TTS playback failed: {e}")
    finally:
        time.sleep(0.2)
        shared_state["bot_is_speaking"] = False
