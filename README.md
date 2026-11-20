# ⚡ IoT Smart Grid Power Theft Detection, Cloud Telemetry & Consumer Billing System

An industrial-grade IoT Smart Grid platform designed for real-time power theft detection, cloud telemetry synchronization, domestic electricity billing calculation, and executive SCADA monitoring.

---

## 🏗️ Architecture & Dual-Meter Infrastructure

```
┌─────────────────────────────────────────┐       ┌─────────────────────────────────────────┐
│     FEEDER METER (Techno LoRaWAN)       │       │    CONSUMER METER (TOMZN DDS238-2)      │
│  • High-accuracy cumulative energy      │       │  • Local Wi-Fi Smart Meter              │
│  • Uplink via The Things Network (TTN)  │       │  • Polled via TinyTuya Local TCP LAN    │
│  • Protocol: MQTT (eu1.cloud.thethings) │       │  • DPS: 20(V), 18(A), 19(W), 17/1(kWh)  │
└────────────────────┬────────────────────┘       └────────────────────┬────────────────────┘
                     │                                                 │
                     ▼                                                 ▼
        ┌───────────────────────────────────────────────────────────────────────────┐
        │                 INGESTION & HARMONIZATION (collector.py)                  │
        │  • Live MQTT Uplink Consumer + TinyTuya TCP Poller                        │
        │  • High-Fidelity Simulation Engine (--simulate flag)                      │
        └─────────────────────────────────────┬─────────────────────────────────────┘
                                              │
                                              ▼
        ┌───────────────────────────────────────────────────────────────────────────┐
        │            DUAL-CHECK POWER THEFT ENGINE (theft_engine.py)                │
        │  • Baseline Hardware Calibration Offset: BASELINE_OFFSET_W = -35.7 W      │
        │  • Check 1: 100% Bypass Detection (Feeder > 5W & Consumer == 0W)          │
        │  • Check 2: Calibrated Discrepancy (> 15W) OR Energy Loss (> 0.015 kWh)   │
        └─────────────────────────────────────┬─────────────────────────────────────┘
                                              │
                                              ▼
        ┌───────────────────────────────────────────────────────────────────────────┐
        │            AUTOMATED TARIFF BILLING ENGINE (billing.py)                   │
        │  • Slabs: 0-50 kWh @ ₹4.50, 51-150 kWh @ ₹6.00, >150 kWh @ ₹7.50          │
        │  • Fixed Meter Charge (₹50) + Electricity Duty (5%)                       │
        │  • Generates Official Utility Invoices (Printable HTML + PDF + CSV)       │
        └─────────────────────────────────────┬─────────────────────────────────────┘
                                              │
                                              ▼
        ┌───────────────────────────────────────────────────────────────────────────┐
        │             HYBRID CLOUD & LOCAL STORAGE LAYER (storage.py)               │
        │  • Primary Cloud Store: Supabase PostgreSQL (meter_readings table)        │
        │  • Resilient Offline Fallback: SQLite (smart_grid.db)                     │
        │  • Auto-Sync Buffer when Cloud Credentials / Connectivity are restored   │
        └─────────────────────────────────────┬─────────────────────────────────────┘
                                              │
                                              ▼
        ┌───────────────────────────────────────────────────────────────────────────┐
        │             EXECUTIVE SCADA COMMAND CENTER (app.py)                       │
        │  • Dark-slate aesthetic (#0B1120 background, #111827 elevated cards)      │
        │  • Cyan (#06B6D4) Feeder Telemetry, Emerald (#10B981) Consumer Telemetry  │
        │  • Pulsing Crimson (#EF4444) Alert Banner for active theft events         │
        │  • Real-time Plotly charts, Theft incident log, & Invoice generator       │
        └───────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Power Theft Detection Engine & Calibration Rationale

The Techno LoRaWAN meter instantaneous `power_W` register exhibits a quantization offset at lower loads while its cumulative `energy_kWh` increments accurately.

Under normal grid baseline conditions (Case 1):
- Feeder reads: $\approx 22.7\text{ W}$ ($229.2\text{ V}, 0.099\text{ A}$)
- Consumer reads: $\approx 58.4\text{ W}$ ($229.3\text{ V}, 0.255\text{ A}$)
- Empirical Hardware Calibration Offset: $\text{BASELINE\_OFFSET\_W} = -35.7\text{ W}$

### Calibration Formula:
$$P_{\text{feeder, cal}} = P_{\text{feeder}} - \text{BASELINE\_OFFSET\_W} = 22.7 - (-35.7) = 58.4\text{ W}$$
$$\Delta P_{\text{cal}} = P_{\text{feeder, cal}} - P_{\text{consumer}} = 58.4 - 58.4 = 0.0\text{ W}$$

### Dual-Check Classification Logic:
1. **`NORMAL`**: Calibrated discrepancy $\Delta P_{\text{cal}} \le 15.0\text{ W}$ and interval energy loss $\le 0.015\text{ kWh}$.
2. **`THEFT DETECTED (100% BYPASS)`**: Triggered when `feeder_power_w > 5.0` and `consumer_power_w <= 0.1` (feeder is drawing power while the consumer meter is bypassed).
3. **`THEFT DETECTED (PARTIAL TAP)`**: Triggered when $\Delta P_{\text{cal}} > 15.0\text{ W}$ OR $(\Delta E_{\text{feeder}} - \Delta E_{\text{consumer}}) > 0.015\text{ kWh}$.

---

## 🚀 Quick Start Guide

### 1. Prerequisites & Virtual Environment
Ensure Python 3.10+ is installed:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
Copy the template configuration:
```powershell
cp .env.example .env
```
Edit `.env` with your hardware keys. If `SUPABASE_URL` and `SUPABASE_KEY` are left empty, the system automatically uses the local SQLite cache fallback (`smart_grid.db`).

```ini
# Feeder Meter (LoRaWAN TTN)
TTN_BROKER=eu1.cloud.thethings.network
TTN_PORT=8883
TTN_APP_ID=energy-meter-iot-app
TTN_API_KEY=NNSXS.xxxx
TTN_DEVICE_ID=energy-device

# Consumer Meter (TOMZN Wi-Fi TinyTuya)
TUYA_DEVICE_ID=xxxx
TUYA_IP_ADDRESS=192.168.1.100
TUYA_LOCAL_KEY=xxxx
TUYA_VERSION=3.3

# Supabase PostgreSQL (Optional - SQLite fallback enabled if empty)
SUPABASE_URL=
SUPABASE_KEY=

# Calibration & Tariffs
BASELINE_OFFSET_W=-35.7
POWER_THEFT_THRESHOLD_W=15.0
ENERGY_THEFT_THRESHOLD_KWH=0.015
FIXED_METER_CHARGE=50.00
ELECTRICITY_DUTY_PCT=5.0
```

---

## 🧪 Running Offline Hardware Simulation Mode

You can test all 3 physical hardware scenarios offline without waiting for LoRaWAN packet intervals:

```powershell
# Run continuous simulation cycling across all 3 hardware test cases
python collector.py --simulate

# Run with custom polling interval (e.g. every 1 second)
python collector.py --simulate --interval 1.0

# Lock simulation to a specific test case:
# Scenario 1 (Normal):
python collector.py --simulate --scenario 1

# Scenario 2 (100% Bypass Theft):
python collector.py --simulate --scenario 2

# Scenario 3 (Partial Tap Theft):
python collector.py --simulate --scenario 3
```

---

## ⚡ Running in Live Hardware Mode

Ensure TTN and TinyTuya credentials are configured in `.env`, then run:
```powershell
python collector.py
```
The collector subscribes to TTN MQTT for LoRaWAN feeder packets and polls the TOMZN Wi-Fi meter every 5 seconds over local LAN.

---

## 🖥️ Launching the SCADA Dashboard

Launch the executive-grade Streamlit web dashboard:
```powershell
streamlit run app.py
```
Open your browser to `http://localhost:8501`.

### Key Dashboard Features:
1. **⚡ Live Grid Monitor**:
   - High-contrast KPI cards for Voltage, Current, Active Power, and Cumulative Energy.
   - Side-by-side Feeder (Cyan `#06B6D4`) vs. Consumer (Emerald `#10B981`) telemetry panels.
   - Real-time Plotly charts: Active Power comparison, Cumulative Energy accumulation, and Discrepancy loss graph.
   - Active Pulsing Crimson (`#EF4444`) Alert Banner for detected theft incidents.
2. **🚨 Theft Audit & Incident Log**:
   - Incident Registry summarizing total monitored snapshots, theft event count, unaccounted kWh, and revenue loss in ₹.
   - Interactive table with classification filters.
   - One-click CSV Audit Log download button.
3. **📄 Consumer Billing & Invoices**:
   - Interactive slab tariff calculator: choose previous and current kWh readings.
   - Dynamic calculation of Slab 1 (0–50 @ ₹4.50), Slab 2 (51–150 @ ₹6.00), Slab 3 (>150 @ ₹7.50), Fixed Charge (₹50), and Duty (5%).
   - Live preview card styled as an official utility electricity board invoice.
   - One-click Download buttons for **Printable HTML** and **PDF Invoices**.

---

## 🗄️ Supabase Cloud Database Setup

To enable Supabase PostgreSQL cloud sync:
1. Create a project at [supabase.com](https://supabase.com).
2. Go to the **SQL Editor** and execute the provided `schema.sql` file:
   ```sql
   -- Paste and run the contents of schema.sql
   ```
3. Copy your project URL and `anon` / `service_role` API key into `.env`:
   ```ini
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-key
   ```
4. Restart the collector or dashboard; existing buffered SQLite records will automatically sync to Supabase.

---

## 🧪 Verification & Automated Tests

Run the complete Phase 1 & Phase 2 verification test suite:
```powershell
python test_phase1.py
```
All tests verify:
- Dual-Check Theft Engine across all 3 scenarios and edge cases.
- Tiered billing calculations across all slabs, fixed charges, and duty.
- SQLite persistence, retrieval, and aggregate statistics.
- Standalone HTML invoice and PDF report rendering.

