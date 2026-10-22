import os
import sys

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

print("=" * 65)
print("🪙  ARTH — Paytm AI Voice & Vision Payment Copilot")
print("    Moto: 'Arth: it means wealth. It means meaning.'")
print("    Edition: Paytm Hackathon Realtime Suite")
print("=" * 65)
print("Initializing core components (loading PyTorch)...")

import torch
print("[OK] PyTorch loaded successfully")

import cv2
import time
import threading
import pyaudio
import numpy as np
import wave
from utils.conversational_llm import ConversationalLLM, BASE_SYSTEM_PROMPT as SYSTEM_PROMPT
from utils.main_pipeline import main_pipeline
from utils.supabase_manager import payment_manager


# ============ AUDIO CONFIGURATION ============
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024  # 64ms chunks at 16kHz
INPUT_DEVICE_INDEX = None  # None = default mic


# ============ FRAME CONFIGURATION ============
FRAME_MAX_WIDTH = 512          # Keeps frame lightweight for fast multimodal processing
FRAME_JPEG_QUALITY = 80        # Optimal quality & speed
FRAME_COLLECT_EVERY_N = 8      # Capture a frame every ~512ms during speech


# ============ SHARED STATE ============
shared_state = {
    "current_conversation": None,
    "bot_is_speaking": False,
    "user_is_speaking": False,
    "running": True,
    "latest_frame": None,
    "current_frame_path": None,
}


# ============ VAD MODEL (lazy-loaded) ============
vad_model = None

def get_vad_model():
    global vad_model
    if vad_model is None:
        print("Loading Silero VAD model for voice activity detection...")
        try:
            repo_dir = os.path.expanduser("~/.cache/torch/hub/snakers4_silero-vad_master")
            if os.path.exists(repo_dir):
                vad_model, _ = torch.hub.load(
                    repo_or_dir=repo_dir,
                    model="silero_vad",
                    source="local",
                    trust_repo=True,
                )
                print("[OK] VAD model loaded locally from cache")
            else:
                raise FileNotFoundError()
        except Exception:
            print("[INFO] Checking online for Silero VAD...")
            vad_model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            print("[OK] VAD model loaded online")
    return vad_model


# ============ FRAME UTILITIES ============

def _compute_sharpness(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _resize_frame(frame, max_width):
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / float(w)
    return cv2.resize(frame, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)


def select_best_frame(frames):
    if not frames:
        return None
    if len(frames) == 1:
        return frames[0]

    best_frame = None
    best_sharpness = -1.0
    for f in frames:
        s = _compute_sharpness(f)
        if s > best_sharpness:
            best_sharpness = s
            best_frame = f
    return best_frame


def save_best_frame_to_temp(best_frame, output_path="temp/best_frame.jpg"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    resized = _resize_frame(best_frame, FRAME_MAX_WIDTH)
    cv2.imwrite(output_path, resized, [cv2.IMWRITE_JPEG_QUALITY, FRAME_JPEG_QUALITY])
    return output_path


# ============ AUDIO RECORDING THREAD ============

def audio_recording_thread():
    model = get_vad_model()
    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=INPUT_DEVICE_INDEX,
            frames_per_buffer=CHUNK,
        )
    except Exception as e:
        print(f"[FATAL] Could not open microphone: {e}")
        shared_state["running"] = False
        return

    print("[MIC] Audio recording started — Arth is listening for payment requests...\n")

    audio_buffer = []
    speaking = False
    silence_chunks = 0
    collected_frames = []
    chunk_counter = 0

    silence_threshold = 12      # ~768ms of natural silence to finalize speech (cut latency by >1.2s)
    speech_threshold = 0.5      # VAD probability threshold
    min_speech_chunks = 6       # Minimum speech length (~200ms)

    while shared_state["running"]:
        if shared_state["bot_is_speaking"]:
            time.sleep(0.05)
            continue

        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception:
            continue

        audio_int16 = np.frombuffer(data, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        if len(audio_float32) != 512:
            step = 512
            vad_scores = []
            for i in range(0, len(audio_float32), step):
                chunk_slice = audio_float32[i:i + step]
                if len(chunk_slice) == step:
                    chunk_tensor = torch.from_numpy(chunk_slice)
                    with torch.no_grad():
                        score = model(chunk_tensor, RATE).item()
                    vad_scores.append(score)
            speech_prob = float(np.mean(vad_scores)) if vad_scores else 0.0
        else:
            chunk_tensor = torch.from_numpy(audio_float32)
            with torch.no_grad():
                speech_prob = model(chunk_tensor, RATE).item()

        if speech_prob > speech_threshold:
            if not speaking:
                speaking = True
                shared_state["user_is_speaking"] = True
                audio_buffer = []
                collected_frames = []
                chunk_counter = 0
                print("\n[SPEECH] Voice detected — recording...")

            audio_buffer.append(data)
            silence_chunks = 0

            chunk_counter += 1
            if chunk_counter % FRAME_COLLECT_EVERY_N == 0:
                latest = shared_state.get("latest_frame")
                if latest is not None:
                    collected_frames.append(latest)

        elif speaking:
            audio_buffer.append(data)
            silence_chunks += 1

            if silence_chunks > silence_threshold:
                speaking = False
                shared_state["user_is_speaking"] = False
                print("[SILENCE] Speech ended — processing request...")

                if len(audio_buffer) >= min_speech_chunks:
                    os.makedirs("temp", exist_ok=True)
                    audio_path = "temp/temp_audio.wav"

                    with wave.open(audio_path, "wb") as wf:
                        wf.setnchannels(CHANNELS)
                        wf.setsampwidth(p.get_sample_size(FORMAT))
                        wf.setframerate(RATE)
                        wf.writeframes(b"".join(audio_buffer))

                    if collected_frames:
                        best = select_best_frame(collected_frames)
                        if best is not None:
                            frame_path = save_best_frame_to_temp(best)
                            shared_state["current_frame_path"] = frame_path
                            print(f"[CAMERA] Vision frame captured: {frame_path} ({len(collected_frames)} samples)")

                    # Process through Arth main pipeline
                    main_pipeline(audio_path, shared_state)

                audio_buffer = []
                collected_frames = []
                silence_chunks = 0

    stream.stop_stream()
    stream.close()
    p.terminate()
    print("[MIC] Audio thread stopped")


# ============ CAMERA & DISPLAY LOOP ============

def start():
    """
    Main entry point for Arth:
    - Displays camera window with Paytm/Arth status HUD
    - Starts audio daemon thread
    - Runs until 'q' is pressed
    """
    conversation = ConversationalLLM(SYSTEM_PROMPT)
    shared_state["current_conversation"] = conversation
    print("[OK] Arth Conversational LLM initialized")

    # Connect & display initial balance
    bal = payment_manager.get_user_balance()
    print(f"[ARTH] Active Profile: {bal['name']} | Paytm Wallet: Rs {bal['wallet_balance']} | Bank: Rs {bal['bank_balance']}")

    print("[CAM] Attempting to open camera...")
    cap = cv2.VideoCapture(0)
    has_camera = cap.isOpened()

    if not has_camera:
        print("[WARN] Could not open camera. Running in AUDIO-ONLY mode.")
        print("Press Ctrl+C to quit\n")
    else:
        print("[CAM] Camera opened successfully")
        print("Press 'q' in the camera window to quit\n")

    # Start audio recording thread
    audio_thread = threading.Thread(target=audio_recording_thread, daemon=True)
    audio_thread.start()

    if not has_camera:
        try:
            while shared_state["running"]:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Exiting Arth...")
        finally:
            shared_state["running"] = False
    else:
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("[WARN] Camera frame capture failed. Falling back to audio-only.")
                    has_camera = False
                    cap.release()
                    cv2.destroyAllWindows()
                    while shared_state["running"]:
                        time.sleep(0.5)
                    break

                # Share frame with audio pipeline
                shared_state["latest_frame"] = frame.copy()

                # Status overlay
                is_speaking = shared_state["bot_is_speaking"]
                is_user_speaking = shared_state.get("user_is_speaking", False)

                if is_speaking:
                    status = "Arth: Speaking..."
                    color = (0, 165, 255)  # Orange
                elif is_user_speaking:
                    status = "User: Speaking (Listening)..."
                    color = (0, 255, 0)    # Green
                else:
                    status = "Arth: Ready (Say 'Check balance' / 'Pay Rahul')..."
                    color = (255, 200, 0)  # Cyan/Blue

                # Header bar
                cv2.rectangle(frame, (0, 0), (frame.shape[1], 45), (20, 20, 20), -1)
                cv2.putText(frame, "ARTH - Paytm AI Payment Copilot", (12, 30),
                            cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 220, 255), 2)
                cv2.putText(frame, status, (12, frame.shape[0] - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

                cv2.imshow("Arth - Wealth & Meaning | Paytm Hackathon", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("Exiting Arth...")
                    break
        except KeyboardInterrupt:
            print("Exiting Arth...")
        finally:
            shared_state["running"] = False
            if has_camera:
                cap.release()
                cv2.destroyAllWindows()
            print("Camera released and windows closed. Goodbye!")


if __name__ == "__main__":
    start()
