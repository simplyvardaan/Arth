import os
import re
import sys
from google import genai
from google.genai import types
from dotenv import load_dotenv
from utils.supabase_manager import payment_manager, extract_pin_from_text

load_dotenv()

VISION_MODEL = "gemini-3.5-flash-lite"
MOTO = "Arth: it means wealth. It means meaning."

BASE_SYSTEM_PROMPT = (
    "You are Arth, Paytm's elite AI Voice & Vision Payment Copilot.\n"
    "Your Moto: 'Arth: it means wealth. It means meaning.'\n\n"
    "--- CORE RESTRICTIONS & SCOPE ---\n"
    "You are STRICTLY RESTRICTED to payment, fintech, and wealth management matters only.\n"
    "Your capabilities are:\n"
    "1. Checking wallet balance, bank account balance, and total wealth.\n"
    "2. Passbook inquiries, recent transactions, and spending analysis.\n"
    "3. Staging money transfers, bills, and UPI payments.\n"
    "4. QR code detection and merchant bill scanning via camera vision.\n"
    "5. Managing personalised Paytm Security Codes (PINs) created uniquely by each user.\n\n"
    "--- PERSONALISED 2-STEP SECURITY CODE (PIN) PROTOCOL ---\n"
    "Every user MUST have their own personalised 4-digit Paytm Security Code.\n"
    "- If the live context shows 'HAS_PIN=False' and user wants to pay, ask them to CREATE their personalised 4-digit code:\n"
    "  Example: 'Payment karne se pehle, kripya apna personalised 4-digit Paytm Security Code banayein.'\n"
    "- If the live context shows 'HAS_PIN=True' and user wants to pay, ask for their Security Code to confirm:\n"
    "  Example: 'Rahul ko Rs 200 bhejne ke liye, kripya apna 4-digit Paytm Security Code batayein.'\n"
    "- If user wants to set or update their PIN (e.g. 'Set my pin to 5678' / 'Mera security code badlo'):\n"
    "  Acknowledge and set it.\n"
    "- Append an action tag at the end of your response to stage the payment:\n"
    "  [ACTION:STAGE_PAY:Recipient:Amount:Category]\n\n"
    "--- CRITICAL GUARDRAIL: OUT-OF-SCOPE BEHAVIOR ---\n"
    "If the user asks about ANYTHING outside payments, money, banking, or wealth (e.g. general chit-chat, "
    "movies, gaming, jokes, weather, science, coding, politics), you MUST politely, wittily, and firmly REFUSE "
    "and immediately steer them back to payments/finances.\n"
    "Example response in Hinglish: 'Main Arth hoon — mera maksad sirf aapke paise aur payments ko sambhalna hai. Batayein, koi payment karni hai ya balance check karna hai?'\n"
    "Never entertain non-financial conversations under any circumstances.\n\n"
    "--- SPOKEN VOICE CONVERSATION RULES ---\n"
    "1. Mirror the user's spoken language (Hindi, English, or Hinglish) naturally.\n"
    "2. Keep responses very concise - maximum 1 to 2 short, punchy sentences so it is fast to speak.\n"
    "3. Never output emojis, markdown asterisks (*), hashtags, or bullet points — output pure spoken text only.\n"
    "4. If you see a QR code, receipt, or bill in the camera frame, identify the payee/merchant and amount, and ask for security code to pay."
)


class ConversationalLLM:
    """
    Conversational LLM for Arth with Person-Specific Personalised Security Codes.
    """

    def __init__(self, system_prompt: str = BASE_SYSTEM_PROMPT):
        self.client = genai.Client()
        self.system_prompt = system_prompt
        self.chat_history = []

    def _get_live_financial_context(self) -> str:
        """Fetch current realtime financial state to inject as context."""
        try:
            balance = payment_manager.get_user_balance()
            txns = payment_manager.get_passbook(limit=3)
            has_pin = payment_manager.has_security_pin()
            
            txn_lines = []
            for t in txns:
                t_type = t.get("type", "DEBIT")
                amt = t.get("amount", 0)
                name = t.get("counterparty_name", "Unknown")
                txn_lines.append(f"{t_type} Rs {amt} with {name}")
            
            recent_str = "; ".join(txn_lines) if txn_lines else "None"
            pending_str = "None"
            if payment_manager.pending_payment:
                p = payment_manager.pending_payment
                pending_str = f"PENDING_{p['state']} for Rs {p['amount']} to {p['recipient']}"

            return (
                f"[LIVE FINANCIAL STATE: User={balance['name']}, HAS_PIN={has_pin}, "
                f"Paytm Wallet=Rs {balance['wallet_balance']}, Bank Account=Rs {balance['bank_balance']}, "
                f"Total Wealth=Rs {balance['total_wealth']}, Pending Transaction: {pending_str}, "
                f"Recent Passbook: {recent_str}]"
            )
        except Exception as e:
            return f"[LIVE FINANCIAL STATE: Error fetching live state: {e}]"

    def send_message(self, user_text: str, image_path: str = None) -> str:
        """
        Process speech with personalised per-user security PIN creation and verification.
        """
        lower_text = user_text.lower().strip()

        # ==============================================================
        # 0. Check for explicit PIN Creation / Change Commands
        # e.g. "Mera security code 5678 set karo" / "Set my PIN to 4321"
        # ==============================================================
        has_pin_word = any(w in lower_text for w in ["pin", "code", "security"])
        has_set_word = any(w in lower_text for w in ["set", "change", "create", "make", "banao", "badlo", "karo", "rakho", "update"])
        if (has_pin_word and has_set_word) or "pin" in lower_text:
            extracted = extract_pin_from_text(user_text)
            if extracted:
                payment_manager.set_user_pin(extracted)
                reply = f"Aapka naya 4-digit Paytm Security Code safaltapoorvak set ho gaya hai! Ab aap surakshit payments kar sakte hain."
                self.chat_history.append({"role": "user", "text": user_text})
                self.chat_history.append({"role": "model", "text": reply})
                return reply

        # ==============================================================
        # 1. Check if a payment is currently awaiting PIN (Creation or Verification)
        # ==============================================================
        if payment_manager.pending_payment:
            cancel_triggers = ["cancel", "mat bhejo", "ruk jao", "nahi", "stop", "rehne do", "abort"]
            if any(t in lower_text for t in cancel_triggers):
                payment_manager.cancel_pending_payment()
                reply = "Theek hai, payment cancel kar di gayi hai. Koi rashi nahi kati."
                self.chat_history.append({"role": "user", "text": user_text})
                self.chat_history.append({"role": "model", "text": reply})
                return reply

            staged = payment_manager.pending_payment
            state = staged.get("state", "AWAITING_PIN_VERIFICATION")

            # 1A. State: User has no PIN yet -> Creating their personalized PIN on the fly!
            if state == "AWAITING_PIN_CREATION":
                extracted = extract_pin_from_text(user_text)
                if extracted:
                    # Save user's personalized PIN
                    payment_manager.set_user_pin(extracted)
                    # Automatically execute the staged transaction
                    exec_res = payment_manager._execute_payment(
                        recipient_name=staged["recipient"],
                        amount=staged["amount"],
                        category=staged["category"],
                        description=staged["description"]
                    )
                    payment_manager.pending_payment = None
                    if exec_res.get("success"):
                        reply = (
                            f"Aapka personalised Security Code set ho gaya aur {staged['recipient']} ko "
                            f"Rs {staged['amount']} safaltapoorvak bhej diye gaye! Naya wallet balance Rs {exec_res['new_wallet_balance']} hai."
                        )
                    else:
                        reply = f"Aapka Security Code set ho gaya, lekin payment poori nahi ho saki: {exec_res.get('message')}."
                else:
                    reply = "Kripya 4 anko ka Security Code bolein, jaise 5678."

                self.chat_history.append({"role": "user", "text": user_text})
                self.chat_history.append({"role": "model", "text": reply})
                return reply

            # 1B. State: User has a PIN -> Verifying their unique personal PIN
            else:
                result = payment_manager.confirm_and_execute_payment(user_text)
                if result.get("success"):
                    reply = (
                        f"Security Code verified! {result['recipient']} ko Rs {result['amount']} "
                        f"safaltapoorvak bhej diye gaye. Naya Paytm Wallet balance Rs {result['new_wallet_balance']} hai."
                    )
                else:
                    reply = f"Galat Security Code! Suraksha ke kaaran payment execute nahi hui. Kripya punah shuru karein."

                self.chat_history.append({"role": "user", "text": user_text})
                self.chat_history.append({"role": "model", "text": reply})
                return reply

        # ==============================================================
        # 1.5 Fast-Path: Instant 0ms Balance & Passbook Queries
        # ==============================================================
        balance_triggers = ["balance", "kitna paisa", "kitne paise", "check balance", "wallet balance", "bank balance", "account balance", "balance check", "paise kitne", "mera balance"]
        pay_words = ["pay", "send", "bhejo", "bhejna", "transfer", "karo"]
        is_asking_to_pay = any(w in lower_text for w in pay_words)

        if any(t in lower_text for t in balance_triggers) and not is_asking_to_pay:
            bal = payment_manager.get_user_balance()
            reply = f"Aapka Paytm Wallet balance Rs {int(bal['wallet_balance']):,} hai aur Bank account mein Rs {int(bal['bank_balance']):,} hain. Total wealth Rs {int(bal['total_wealth']):,} hai."
            self.chat_history.append({"role": "user", "text": user_text})
            self.chat_history.append({"role": "model", "text": reply})
            return reply

        passbook_triggers = ["passbook", "last transaction", "pichle transaction", "recent transaction", "history", "aakhri kharch"]
        if any(t in lower_text for t in passbook_triggers):
            txns = payment_manager.get_passbook(limit=2)
            lines = [f"{t.get('counterparty_name')} ko Rs {int(t.get('amount', 0))}" for t in txns]
            recent_str = " aur ".join(lines) if lines else "Koi recent transaction nahi mila"
            reply = f"Aapke pichle transactions hain: {recent_str}."
            self.chat_history.append({"role": "user", "text": user_text})
            self.chat_history.append({"role": "model", "text": reply})
            return reply

        # ==============================================================
        # 2. Normal Flow: Process with Gemini Multimodal Model
        # ==============================================================
        live_context = self._get_live_financial_context()
        combined_text = f"{live_context}\nUser said: {user_text}"

        parts = []
        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
                print(f"[VISION] Attached camera frame for Arth payment analysis: {image_path}")
            except Exception as e:
                print(f"[WARN] Failed to read frame {image_path}: {e}")

        parts.append(types.Part.from_text(text=combined_text))

        contents = []
        for turn in self.chat_history:
            contents.append(types.Content(
                role=turn["role"],
                parts=[types.Part.from_text(text=turn["text"])]
            ))
        contents.append(types.Content(role="user", parts=parts))

        try:
            response = self.client.models.generate_content(
                model=VISION_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.4,
                    max_output_tokens=150,
                )
            )

            bot_reply = response.text.strip() if response.text else "Maaf kijiye, main samajh nahi paya."

            # Check if Gemini wants to set/create a PIN
            # Format: [ACTION:SET_PIN:XXXX]
            set_pin_match = re.search(r'\[ACTION:SET_PIN:(\d{4})\]', bot_reply)
            if set_pin_match:
                new_pin = set_pin_match.group(1)
                payment_manager.set_user_pin(new_pin)
                bot_reply = re.sub(r'\[ACTION:SET_PIN:\d{4}\]', '', bot_reply).strip()

            # Check if Gemini wants to stage a payment
            # Format: [ACTION:STAGE_PAY:Recipient:Amount:Category]
            stage_match = re.search(r'\[ACTION:STAGE_PAY:([^:]+):([0-9.]+)(?::([^\]]+))?\]', bot_reply)
            if stage_match:
                recipient = stage_match.group(1).strip()
                amount = float(stage_match.group(2).strip())
                category = stage_match.group(3).strip() if stage_match.group(3) else "Payment"

                # Stage the payment in payment_manager
                stage_info = payment_manager.stage_payment(recipient, amount, category=category)
                bot_reply = re.sub(r'\[ACTION:STAGE_PAY:[^\]]+\]', '', bot_reply).strip()

                # If user doesn't have a PIN yet, guide them to create one
                if not stage_info.get("has_pin"):
                    bot_reply = f"{recipient} ko Rs {amount} bhejne ke liye, pehle apna manpasand 4-digit Paytm Security Code banayein."

            # Clean any remaining brackets
            bot_reply = re.sub(r'\[.*?\]', '', bot_reply).strip()

            self.chat_history.append({"role": "user", "text": user_text})
            self.chat_history.append({"role": "model", "text": bot_reply})

            if len(self.chat_history) > 12:
                self.chat_history = self.chat_history[-12:]

            return bot_reply

        except Exception as e:
            print(f"[ERROR] Gemini generation failed: {e}")
            return "Server se sampark karne mein dikkat aa rahi hai. Kripya punah prayas karein."
