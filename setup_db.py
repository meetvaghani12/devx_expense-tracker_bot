"""
One-time database setup script.
Run this once to create all required tables in Supabase.
"""
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    telegram_username TEXT,
    name TEXT NOT NULL,
    email TEXT,
    joined_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    description TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    paid_by UUID REFERENCES users(id),
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expense_splits (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    expense_id UUID REFERENCES expenses(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    amount_owed DECIMAL(10,2) NOT NULL,
    is_settled BOOLEAN DEFAULT FALSE,
    settled_at TIMESTAMPTZ,
    UNIQUE(expense_id, user_id)
);

CREATE TABLE IF NOT EXISTS settlements (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    payer_id UUID REFERENCES users(id),
    receiver_id UUID REFERENCES users(id),
    amount DECIMAL(10,2) NOT NULL,
    settled_at TIMESTAMPTZ DEFAULT NOW(),
    method TEXT DEFAULT 'manual',
    note TEXT
);
"""


def verify_tables():
    from db.client import get_client
    db = get_client()
    tables = ["users", "expenses", "expense_splits", "settlements"]
    all_ok = True
    for table in tables:
        try:
            db.table(table).select("id").limit(1).execute()
            print(f"  ✅ {table}")
        except Exception as e:
            print(f"  ❌ {table} — {e}")
            all_ok = False
    return all_ok


if __name__ == "__main__":
    print("=" * 50)
    print("SplitBot — Database Setup")
    print("=" * 50)
    print()
    print("Checking tables...")
    if verify_tables():
        print()
        print("✅ All tables exist! Database is ready.")
    else:
        print()
        print("⚠️  Some tables are missing. Please run the SQL below in your")
        print("    Supabase SQL Editor:")
        print()
        print("    👉 https://supabase.com/dashboard/project/aumzmlejfefeofpswcjb/sql/new")
        print()
        print("─" * 50)
        print(SCHEMA_SQL)
        print("─" * 50)
        print()
        print("After running the SQL, re-run this script to verify.")
