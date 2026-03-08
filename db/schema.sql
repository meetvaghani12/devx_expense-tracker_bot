-- Run this in Supabase SQL Editor to set up the database

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
