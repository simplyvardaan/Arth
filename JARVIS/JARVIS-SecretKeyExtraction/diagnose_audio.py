import pyaudio
import numpy as np
import time

def list_devices():
    p = pyaudio.PyAudio()
    try:
        info = p.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        
        print("\n=== AVAILABLE AUDIO INPUT DEVICES ===")
        default_input = p.get_default_input_device_info()
        print(f"Default Input Device: ID {default_input['index']} - {default_input['name']}\n")
        
        for i in range(0, numdevices):
            try:
                device_info = p.get_device_info_by_host_api_device_index(0, i)
                if device_info.get('maxInputChannels') > 0:
                    print(f"Device ID {i}: {device_info.get('name')} (Max Channels: {device_info.get('maxInputChannels')}, Default Rate: {device_info.get('defaultSampleRate')}Hz)")
            except Exception:
                pass
    except Exception as e:
        print(f"Error listing host devices: {e}")
    finally:
        p.terminate()

def test_recording():
    p = pyaudio.PyAudio()
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK = 1024
    
    try:
        default_idx = p.get_default_input_device_info()['index']
        print(f"\nOpening default input device (ID {default_idx})...")
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Failed to open default input device: {e}")
        p.terminate()
        return

    print("Recording audio for 5 seconds... PLEASE SPEAK INTO THE MICROPHONE!")
    start_time = time.time()
    max_volume = 0
    total_samples = 0
    zero_chunks = 0
    
    while time.time() - start_time < 5.0:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            if len(audio_data) > 0:
                rms = np.sqrt(np.mean(audio_data.astype(np.float64)**2))
                if rms > max_volume:
                    max_volume = rms
                if rms == 0.0:
                    zero_chunks += 1
                total_samples += 1
        except Exception as e:
            print(f"Read error: {e}")
            
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print("\n=== RECORDING ANALYSIS ===")
    print(f"Total read chunks: {total_samples}")
    print(f"Completely silent (zero) chunks: {zero_chunks}")
    print(f"Peak RMS volume level: {max_volume:.2f}")
    
    if max_volume == 0.0:
        print("\n[WARNING] Microphone returned absolutely ZERO sound. Your microphone is either muted in Windows, set to 0% volume, or locked by another application.")
    elif max_volume < 15.0:
        print("\n[WARNING] Microphone volume is extremely low. VAD might not detect speech. Try turning up the input volume in Windows settings.")
    else:
        print("\n[SUCCESS] Microphone is working perfectly and capturing audio!")

if __name__ == "__main__":
    list_devices()
    test_recording()
