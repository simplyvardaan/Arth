import os
import re
import time
import uuid
import json
import threading
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://nlzgvvlzjclzgbwnycba.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

# Fast In-Memory Realtime Cache (Zero-latency read access)
_CACHE = {
    "user": {
        "id": "a0000000-0000-0000-0000-000000000001",
        "name": "Arth",
        "phone": "9876543210",
        "upi_id": "arth@paytm",
        "wallet_balance": 4850.00,
        "bank_balance": 52000.00,
        "security_pin": None
    },
    "transactions": [
        {
            "id": str(uuid.uuid4()),
            "counterparty_name": "Blue Tokai Coffee",
            "counterparty_upi": "bluetokai@paytm",
            "amount": 240.00,
            "type": "DEBIT",
            "category": "Food & Dining",
            "status": "SUCCESS",
            "description": "Cappuccino & Croissant",
            "payment_method": "PAYTM_UPI",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "counterparty_name": "Delhi Metro Rail",
            "counterparty_upi": "dmrc@icici",
            "amount": 50.00,
            "type": "DEBIT",
            "category": "Transit & Travel",
            "status": "SUCCESS",
            "description": "Metro Smartcard Recharge",
            "payment_method": "PAYTM_WALLET",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "counterparty_name": "Rahul Sharma",
            "counterparty_upi": "rahul@oksbi",
            "amount": 1500.00,
            "type": "CREDIT",
            "category": "Transfer",
            "status": "SUCCESS",
            "description": "Dinner split reimbursement",
            "payment_method": "PAYTM_UPI",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "counterparty_name": "Blinkit Grocery",
            "counterparty_upi": "blinkit@paytm",
            "amount": 460.00,
            "type": "DEBIT",
            "category": "Groceries",
            "status": "SUCCESS",
            "description": "Weekly fruits & snacks",
            "payment_method": "PAYTM_UPI",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ],
    "realtime_events": []
}


def extract_pin_from_text(user_text: str):
    """
    Extract a 4-digit PIN from spoken text.
    Handles digits (e.g. '5678') or Hindi/English words ('paanch chhe saat aath').
    """
    digits_match = re.search(r'\b\d{4}\b', user_text)
    if digits_match:
        return digits_match.group(0)

    word_map = {
        "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "zero": "0",
        "ek": "1", "do": "2", "teen": "3", "chaar": "4", "char": "4",
        "paanch": "5", "panch": "5", "chhe": "6", "che": "6", "saat": "7", "sat": "7",
        "aath": "8", "ath": "8", "nau": "9", "shunya": "0", "sunya": "0"
    }
    words = re.findall(r'[a-zA-Z]+|\d', user_text.lower())
    digits = []
    for w in words:
        if w in word_map:
            digits.append(word_map[w])
        elif w.isdigit() and len(w) == 1:
            digits.append(w)
        elif w.isdigit() and len(w) == 4:
            return w

    if len(digits) == 4:
        return "".join(digits)
    return None


class SupabasePaymentManager:
    """
    Ultra-Fast Realtime Payment & Wealth Manager for Arth.
    Uses in-memory cache for 0ms reads + asynchronous background sync to Supabase.
    """

    def __init__(self):
        self.client = None
        self.is_connected = False
        self.pending_payment = None
        self._init_supabase()

    def _init_supabase(self):
        if not SUPABASE_KEY:
            return

        def _connect():
            try:
                from supabase import create_client, Client
                self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
                res = self.client.table("users").select("*").limit(1).execute()
                if res.data and len(res.data) > 0:
                    remote_user = res.data[0]
                    for k, v in remote_user.items():
                        if v is not None:
                            _CACHE["user"][k] = v
                self.is_connected = True
                print("[OK] Supabase Realtime Payment Engine loaded & cached!")
            except Exception:
                self.is_connected = False

        # Run connection in background so startup is instantaneous
        threading.Thread(target=_connect, daemon=True).start()

    def get_user_profile(self):
        """0ms in-memory cache lookup."""
        return _CACHE["user"]

    def get_user_balance(self):
        """0ms in-memory balance check."""
        user = _CACHE["user"]
        wallet = float(user.get("wallet_balance", 0.0))
        bank = float(user.get("bank_balance", 0.0))
        return {
            "name": user.get("name", "Arth"),
            "upi_id": user.get("upi_id", "arth@paytm"),
            "wallet_balance": wallet,
            "bank_balance": bank,
            "total_wealth": wallet + bank,
            "has_security_pin": bool(user.get("security_pin"))
        }

    def get_user_pin(self):
        """0ms in-memory PIN lookup."""
        return _CACHE["user"].get("security_pin")

    def set_user_pin(self, new_pin: str):
        """Set user personalized PIN in cache instantly + async sync to Supabase."""
        if not new_pin or len(new_pin) != 4 or not new_pin.isdigit():
            return {"success": False, "message": "PIN must be 4 digits"}

        # Instant cache update
        _CACHE["user"]["security_pin"] = new_pin
        print(f"[SECURITY] Personalised PIN set to: **** (instant 0ms update)")

        # Asynchronous background write to Supabase (does not block voice pipeline)
        def _sync():
            if self.is_connected and self.client:
                try:
                    self.client.table("users").update({"security_pin": new_pin}).eq("id", _CACHE["user"]["id"]).execute()
                except Exception:
                    pass
        threading.Thread(target=_sync, daemon=True).start()

        return {"success": True, "message": "PIN set successfully"}

    def has_security_pin(self) -> bool:
        pin = self.get_user_pin()
        return bool(pin and len(pin) == 4)

    def get_passbook(self, limit=5):
        """0ms in-memory passbook lookup."""
        return _CACHE["transactions"][:limit]

    # ============ 2-STEP SECURITY WORKFLOW ============

    def stage_payment(self, recipient_name: str, amount: float, category: str = "Payment", description: str = ""):
        amount = round(float(amount), 2)
        bal = self.get_user_balance()
        if amount > bal["total_wealth"]:
            return {
                "success": False,
                "message": f"Aparyaapt balance. Total available balance hai Rs {bal['total_wealth']}."
            }

        has_pin = self.has_security_pin()
        state = "AWAITING_PIN_VERIFICATION" if has_pin else "AWAITING_PIN_CREATION"

        self.pending_payment = {
            "recipient": recipient_name,
            "amount": amount,
            "category": category or "Payment",
            "description": description or f"Payment to {recipient_name}",
            "state": state,
            "created_at": time.time()
        }
        return {
            "success": True,
            "staged": True,
            "has_pin": has_pin,
            "recipient": recipient_name,
            "amount": amount
        }

    def cancel_pending_payment(self):
        if self.pending_payment:
            self.pending_payment = None
            return True
        return False

    def verify_pin_input(self, user_text: str) -> bool:
        user_pin = self.get_user_pin()
        if not user_pin:
            return False

        extracted = extract_pin_from_text(user_text)
        if extracted and extracted == user_pin:
            return True

        cleaned = user_text.lower().replace(" ", "").replace("-", "")
        return user_pin in cleaned

    def confirm_and_execute_payment(self, pin_input: str):
        if not self.pending_payment:
            return {"success": False, "error": "NO_PENDING_PAYMENT", "message": "Koi pending payment nahi hai."}

        if time.time() - self.pending_payment["created_at"] > 120:
            self.pending_payment = None
            return {"success": False, "error": "TIMEOUT", "message": "Payment session timeout."}

        if not self.verify_pin_input(pin_input):
            return {"success": False, "error": "INVALID_PIN", "message": "Galat Security Code!"}

        staged = self.pending_payment
        self.pending_payment = None
        return self._execute_payment(
            recipient_name=staged["recipient"],
            amount=staged["amount"],
            category=staged["category"],
            description=staged["description"]
        )

    def _execute_payment(self, recipient_name: str, amount: float, category: str = "Shopping",
                         description: str = "", method: str = "PAYTM_UPI"):
        """Instant in-memory execution + async background write to Supabase."""
        amount = round(float(amount), 2)
        current_balance = self.get_user_balance()
        if current_balance["wallet_balance"] >= amount:
            payment_source = "PAYTM_WALLET"
            new_wallet = current_balance["wallet_balance"] - amount
            new_bank = current_balance["bank_balance"]
        elif current_balance["bank_balance"] >= amount:
            payment_source = "PAYTM_UPI"
            new_wallet = current_balance["wallet_balance"]
            new_bank = current_balance["bank_balance"] - amount
        else:
            return {"success": False, "message": f"Insufficient balance."}

        txn_record = {
            "id": str(uuid.uuid4()),
            "counterparty_name": recipient_name,
            "counterparty_upi": f"{recipient_name.lower().replace(' ', '')}@paytm",
            "amount": amount,
            "type": "DEBIT",
            "category": category or "General",
            "status": "SUCCESS",
            "description": description or f"Payment to {recipient_name}",
            "payment_method": payment_source,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # 1. Instant Cache Update (0ms)
        _CACHE["user"]["wallet_balance"] = new_wallet
        _CACHE["user"]["bank_balance"] = new_bank
        _CACHE["transactions"].insert(0, txn_record)

        # 2. Asynchronous write to Supabase
        def _async_db_sync():
            if self.is_connected and self.client:
                try:
                    self.client.table("users").update({
                        "wallet_balance": new_wallet,
                        "bank_balance": new_bank
                    }).eq("id", _CACHE["user"]["id"]).execute()
                    self.client.table("transactions").insert(txn_record).execute()
                    self.client.table("realtime_events").insert({
                        "event_type": "PAYMENT_SENT",
                        "message": f"Paid Rs {amount} to {recipient_name}",
                        "payload": txn_record
                    }).execute()
                except Exception:
                    pass
        threading.Thread(target=_async_db_sync, daemon=True).start()

        print(f"[PAYTM SUCCESS] Paid Rs {amount} to {recipient_name} | Wallet: Rs {new_wallet}")

        return {
            "success": True,
            "recipient": recipient_name,
            "amount": amount,
            "payment_method": payment_source,
            "new_wallet_balance": new_wallet,
            "new_bank_balance": new_bank,
            "remaining_wealth": new_wallet + new_bank,
            "transaction_id": txn_record["id"]
        }

    def get_spend_analytics(self):
        txns = self.get_passbook(limit=20)
        total_debit = 0.0
        by_category = {}
        for t in txns:
            if t.get("type") == "DEBIT":
                amt = float(t.get("amount", 0.0))
                cat = t.get("category", "Other")
                total_debit += amt
                by_category[cat] = by_category.get(cat, 0.0) + amt
        return {
            "total_spend": round(total_debit, 2),
            "breakdown": by_category,
            "transaction_count": len([t for t in txns if t.get("type") == "DEBIT"])
        }


payment_manager = SupabasePaymentManager()
