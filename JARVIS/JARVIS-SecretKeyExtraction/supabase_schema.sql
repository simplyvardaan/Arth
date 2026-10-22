-- ==============================================================================
-- 🪙 ARTH: Supabase Realtime Database Schema (Paytm Hackathon Edition)
-- Moto: "Arth: it means wealth. It means meaning."
-- ==============================================================================

-- 1. Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. Users Table (Paytm Wallet & Bank Profile)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    upi_id TEXT UNIQUE NOT NULL,
    wallet_balance NUMERIC(12, 2) NOT NULL DEFAULT 5000.00,
    bank_balance NUMERIC(12, 2) NOT NULL DEFAULT 45000.00,
    security_pin TEXT DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ensure security_pin column exists if table is already created
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS security_pin TEXT DEFAULT NULL;

-- 3. Transactions Table (Passbook & Payment Ledger)
CREATE TABLE IF NOT EXISTS public.transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    counterparty_name TEXT NOT NULL,
    counterparty_upi TEXT,
    amount NUMERIC(12, 2) NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('DEBIT', 'CREDIT')),
    category TEXT NOT NULL DEFAULT 'General',
    status TEXT NOT NULL DEFAULT 'SUCCESS' CHECK (status IN ('SUCCESS', 'PENDING', 'FAILED')),
    description TEXT,
    payment_method TEXT NOT NULL DEFAULT 'PAYTM_UPI',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Payment Requests / QR Invoices
CREATE TABLE IF NOT EXISTS public.payment_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    requester_name TEXT NOT NULL,
    requester_upi TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'PAID', 'EXPIRED')),
    qr_data TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Realtime Events Stream (For Live Payment Alerts, Soundbox & Broadcasts)
CREATE TABLE IF NOT EXISTS public.realtime_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Enable Realtime on all tables
ALTER PUBLICATION supabase_realtime ADD TABLE public.users;
ALTER PUBLICATION supabase_realtime ADD TABLE public.transactions;
ALTER PUBLICATION supabase_realtime ADD TABLE public.payment_requests;
ALTER PUBLICATION supabase_realtime ADD TABLE public.realtime_events;

-- 7. Row Level Security (RLS) Configuration
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.realtime_events ENABLE ROW LEVEL SECURITY;

-- Allow read/write for authenticated users and service role (Hackathon mode)
DROP POLICY IF EXISTS "Public access to users" ON public.users;
CREATE POLICY "Public access to users" ON public.users FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Public access to transactions" ON public.transactions;
CREATE POLICY "Public access to transactions" ON public.transactions FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Public access to payment_requests" ON public.payment_requests;
CREATE POLICY "Public access to payment_requests" ON public.payment_requests FOR ALL USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Public access to realtime_events" ON public.realtime_events;
CREATE POLICY "Public access to realtime_events" ON public.realtime_events FOR ALL USING (true) WITH CHECK (true);

-- 8. Seed Default Paytm Demo User & Transactions
INSERT INTO public.users (id, phone, name, upi_id, wallet_balance, bank_balance)
VALUES 
    ('a0000000-0000-0000-0000-000000000001', '9876543210', 'Arth', 'arth@paytm', 4850.00, 52000.00)
ON CONFLICT (phone) DO UPDATE 
SET name = EXCLUDED.name, upi_id = EXCLUDED.upi_id;

-- Seed Sample Recent Transactions
INSERT INTO public.transactions (user_id, counterparty_name, counterparty_upi, amount, type, category, status, description, payment_method)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Blue Tokai Coffee', 'bluetokai@paytm', 240.00, 'DEBIT', 'Food & Dining', 'SUCCESS', 'Cappuccino & Croissant', 'PAYTM_UPI'),
    ('a0000000-0000-0000-0000-000000000001', 'Delhi Metro Rail', 'dmrc@icici', 50.00, 'DEBIT', 'Transit & Travel', 'SUCCESS', 'Metro Smartcard Recharge', 'PAYTM_WALLET'),
    ('a0000000-0000-0000-0000-000000000001', 'Rahul Sharma', 'rahul@oksbi', 1500.00, 'CREDIT', 'Transfer', 'SUCCESS', 'Dinner split reimbursement', 'PAYTM_UPI'),
    ('a0000000-0000-0000-0000-000000000001', 'Blinkit Grocery', 'blinkit@paytm', 460.00, 'DEBIT', 'Groceries', 'SUCCESS', 'Weekly fruits & snacks', 'PAYTM_UPI')
ON CONFLICT DO NOTHING;

-- Seed Initial Realtime Event
INSERT INTO public.realtime_events (event_type, message, payload)
VALUES 
    ('SYSTEM_INIT', 'Arth AI Payment Engine initialized in Supabase Realtime mode', '{"engine": "Arth", "edition": "Paytm Hackathon"}'::jsonb);
