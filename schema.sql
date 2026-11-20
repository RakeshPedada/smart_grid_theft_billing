-- ====================================================================
-- Smart Grid Power Theft Detection & Billing System
-- Supabase / PostgreSQL Schema Definition
-- ====================================================================

-- Enable UUID extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create meter_readings table
CREATE TABLE IF NOT EXISTS meter_readings (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    
    -- Feeder Meter (Techno LoRaWAN) Telemetry
    feeder_voltage_v NUMERIC(8, 2) NOT NULL,
    feeder_current_a NUMERIC(8, 4) NOT NULL,
    feeder_power_w NUMERIC(8, 2) NOT NULL,
    feeder_energy_kwh NUMERIC(12, 4) NOT NULL,
    
    -- Consumer Meter (TOMZN DDS238-2 Wi-Fi) Telemetry
    consumer_voltage_v NUMERIC(8, 2) NOT NULL,
    consumer_current_a NUMERIC(8, 4) NOT NULL,
    consumer_power_w NUMERIC(8, 2) NOT NULL,
    consumer_energy_kwh NUMERIC(12, 4) NOT NULL,
    
    -- Theft Detection Analytics
    calibrated_diff_w NUMERIC(8, 2) NOT NULL,
    energy_diff_kwh NUMERIC(12, 4) NOT NULL,
    theft_status VARCHAR(64) NOT NULL,
    loss_w NUMERIC(8, 2) DEFAULT 0.0,
    loss_kwh NUMERIC(12, 4) DEFAULT 0.0,
    
    -- Billing Estimates
    billed_units_kwh NUMERIC(12, 4) DEFAULT 0.0,
    estimated_bill_inr NUMERIC(10, 2) DEFAULT 0.0
);

-- Indexes for performance on time-series queries and audit filters
CREATE INDEX IF NOT EXISTS idx_meter_readings_created_at ON meter_readings (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meter_readings_theft_status ON meter_readings (theft_status);

-- Optional Row Level Security (RLS) setup for Supabase public access or service role
ALTER TABLE meter_readings ENABLE ROW LEVEL SECURITY;

-- Allow read access to authenticated and anon users (read-only for dashboard)
CREATE POLICY "Allow public read access" ON meter_readings
    FOR SELECT USING (true);

-- Allow insert access for service role or authenticated collector
CREATE POLICY "Allow public insert access" ON meter_readings
    FOR INSERT WITH CHECK (true);

