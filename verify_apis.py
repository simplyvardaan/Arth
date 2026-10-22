import os
import sys
import requests
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()


def verify():
    print("=" * 60)
    print("🪙 Verifying Arth AI Payment Engine & Supabase APIs...")
    print("   Moto: 'Arth: it means wealth. It means meaning.'")
    print("=" * 60)

    gemini_key = os.getenv("GEMINI_API_KEY")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not gemini_key:
        print("[ERROR] GEMINI_API_KEY is not set in .env file!")
        sys.exit(1)
    else:
        print("[OK] GEMINI_API_KEY is configured.")

    if not supabase_url or not supabase_key:
        print("[ERROR] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set in .env file!")
        sys.exit(1)
    else:
        print("[OK] Supabase credentials configured.")

    # 1. Test Gemini API
    try:
        from google import genai
        client = genai.Client()
        print("Testing Gemini 3.5 Flash Lite connection...")
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents="Say 'Arth is ready for Paytm hackathon' in one line."
        )
        print(f"[OK] Gemini API is live! Response: {response.text.strip()}")
    except Exception as e:
        print(f"[ERROR] Gemini API Test Failed: {e}")
        sys.exit(1)

    # 2. Test Supabase Endpoint
    try:
        print("Testing Supabase connection...")
        res = requests.get(
            f"{supabase_url}/rest/v1/",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        )
        if res.status_code == 200:
            print("[OK] Supabase REST API connected successfully!")
        else:
            print(f"[WARN] Supabase returned status {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[ERROR] Supabase Test Failed: {e}")
        sys.exit(1)

    # 3. Test Arth Realtime Payment Manager
    try:
        from utils.supabase_manager import payment_manager
        bal = payment_manager.get_user_balance()
        print(f"[OK] Payment Manager Active: User='{bal['name']}', Wallet=Rs {bal['wallet_balance']}, Bank=Rs {bal['bank_balance']}")
    except Exception as e:
        print(f"[ERROR] Payment Manager Failed: {e}")
        sys.exit(1)

    print("\n[SUCCESS] Arth Engine is fully configured and ready to run!")


if __name__ == "__main__":
    verify()
