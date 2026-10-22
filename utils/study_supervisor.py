import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def analyze_study_focus(image_path):
    """
    Analyze the user image to determine if they are focused on studying or slacking.
    
    Args:
        image_path: Path to the JPG webcam frame.
        
    Returns:
        "STUDYING" or "SLACKING: <reminder_message>"
    """
    if not os.path.exists(image_path):
        return "STUDYING"

    try:
        client = genai.Client()
        
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        prompt = (
            "Analyze the person in this image. They are supposed to be studying. "
            "Determine if they are actively studying/working (e.g. writing, reading books, "
            "staring focused at screen/notes) OR if they are slacking off (e.g. looking at/using "
            "a smartphone, sleeping/lying down, resting head on desk/hand sluggishly, "
            "or if the chair is completely empty/absent).\n\n"
            "If they are studying, return exactly: STUDYING\n"
            "If they are slacking off, using a phone, sleeping, or absent, return exactly: "
            "SLACKING: <witty, strict, or roasting one-sentence verbal warning to get them back to work, "
            "addressed in Hinglish or Hindi. Keep it direct and short so it can be spoken quickly.>"
        )

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                types.Part.from_text(text=prompt)
            ]
        )

        result = response.text
        if result:
            return result.strip()
        return "STUDYING"

    except Exception as e:
        print(f"[ERROR] Study supervisor check failed: {e}")
        return "STUDYING"
