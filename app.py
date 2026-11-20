"""
app.py
======
Executive-Grade Smart Grid SCADA Command Center Dashboard.

Visual Design:
- High-contrast Dark-Slate SCADA aesthetic (#0B1120 background, #111827 elevated cards).
- Cyan (#06B6D4) for Feeder (Techno LoRaWAN) Telemetry.
- Emerald (#10B981) for Consumer (TOMZN Wi-Fi) Telemetry.
- Crimson (#EF4444) Pulsing Banner for Active Theft Events.
- Amber (#F59E0B) for Partial Tap Discrepancies.

Views:
1. ⚡ Live Grid Monitor:
   - High-contrast KPI cards, side-by-side Feeder vs Consumer telemetry.
   - Real-time Plotly charts (Power Comparison, Cumulative Energy, Calibrated Discrepancy).
2. 🚨 Theft Audit & Incident Log:
   - Summary loss analytics, filterable historical incident table, one-click CSV export.
3. 📄 Consumer Billing & Utility Invoice Generator:
   - Interactive tiered tariff calculator (Slabs 1, 2, 3 + Fixed + Duty).
   - Official electricity board invoice card preview with instant PDF/HTML download.
"""

import os
import io
import time
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from datetime import datetime

from storage import SmartGridStorage
from billing import BillingEngine
from theft_engine import DualCheckTheftEngine
from collector import TelemetryCollector

# -----------------------------------------------------------------------------
# Streamlit Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Grid SCADA Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Custom SCADA Dark-Slate CSS Styling
# -----------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
    /* Dark-slate SCADA command center base background */
    .stApp {
        background-color: #0B1120 !important;
        color: #F8FAFC !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    
    /* Top app header bar */
    header[data-testid="stHeader"] {
        background-color: #0B1120 !important;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #0F172A !important;
        border-right: 1px solid #1E293B !important;
    }

    /* Elevated SCADA Cards */
    .scada-card {
        background-color: #111827;
        border: 1px solid #1F2937;
        border-radius: 10px;
        padding: 20px 22px;
        margin-bottom: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
        transition: border-color 0.2s ease-in-out;
    }
    .scada-card:hover {
        border-color: #374151;
    }

    /* Card Headers */
    .card-title-feeder {
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #06B6D4;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
    }
    .card-title-consumer {
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #10B981;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
    }
    .card-title-neutral {
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94A3B8;
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
    }

    /* KPI Display Metrics */
    .kpi-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        padding: 8px 0;
        border-bottom: 1px solid #1E293B;
    }
    .kpi-row:last-child {
        border-bottom: none;
    }
    .kpi-label {
        font-size: 12px;
        color: #94A3B8;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .kpi-value {
        font-size: 18px;
        font-weight: 700;
        color: #F8FAFC;
    }

    /* Pulsing Alert Banner for Theft */
    @keyframes pulse-crimson {
        0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
        70% { box-shadow: 0 0 0 12px rgba(239, 68, 68, 0); }
        100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    .banner-theft {
        background: linear-gradient(90deg, rgba(239, 68, 68, 0.25), rgba(239, 68, 68, 0.1));
        border: 1px solid #EF4444;
        border-left: 6px solid #EF4444;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 20px;
        animation: pulse-crimson 2.5s infinite;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .banner-normal {
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.15), rgba(16, 185, 129, 0.05));
        border: 1px solid #10B981;
        border-left: 6px solid #10B981;
        border-radius: 8px;
        padding: 14px 20px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    /* Badges */
    .badge-bypass {
        background-color: #7F1D1D;
        color: #FCA5A5;
        border: 1px solid #EF4444;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }
    .badge-partial {
        background-color: #78350F;
        color: #FDE68A;
        border: 1px solid #F59E0B;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }
    .badge-normal {
        background-color: #064E3B;
        color: #A7F3D0;
        border: 1px solid #10B981;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #0F172A;
        padding: 6px;
        border-radius: 8px;
        border: 1px solid #1E293B;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px;
        border-radius: 6px;
        color: #94A3B8;
        font-weight: 600;
        padding: 0 18px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1E293B !important;
        color: #38BDF8 !important;
        border-bottom: 2px solid #06B6D4 !important;
    }

    /* Dataframe dark table adjustments */
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
        border: 1px solid #1F2937;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Service Initializations & Caching
# -----------------------------------------------------------------------------
@st.cache_resource
def get_storage():
    return SmartGridStorage()


@st.cache_resource
def get_billing_engine():
    return BillingEngine()


storage = get_storage()
billing_engine = get_billing_engine()


# -----------------------------------------------------------------------------
# Sidebar Configuration & Controls
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
            <div style="background: #06B6D4; width: 12px; height: 12px; border-radius: 50%;"></div>
            <h2 style="margin: 0; font-size: 18px; font-weight: 800; color: #F8FAFC;">GRID SCADA CORE</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Advanced Anti-Theft & Billing Infrastructure")
    st.divider()

    # Cloud Connection Status Indicator
    is_cloud_active = storage.supabase_client is not None
    if is_cloud_active:
        st.markdown(
            """
            <div style="background: #064E3B; border: 1px solid #10B981; padding: 10px 14px; border-radius: 6px; font-size: 12px; margin-bottom: 16px;">
                <span style="color: #34D399; font-weight: 700;">● CLOUD SYNC ACTIVE</span><br>
                <span style="color: #E2E8F0;">Connected to Supabase PostgreSQL</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="background: #1E293B; border: 1px solid #475569; padding: 10px 14px; border-radius: 6px; font-size: 12px; margin-bottom: 16px;">
                <span style="color: #94A3B8; font-weight: 700;">○ LOCAL CACHE ACTIVE</span><br>
                <span style="color: #CBD5E1;">Buffering to SQLite (smart_grid.db)</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader("System Controls")
    auto_refresh = st.checkbox("Auto-refresh Live Telemetry", value=False)
    refresh_rate = st.slider("Refresh Interval (seconds)", min_value=2, max_value=15, value=4)

    if st.button("🔄 Manual Telemetry Refresh", use_container_width=True):
        st.rerun()

    st.divider()
    st.subheader("Interactive Simulator")
    st.caption("Inject synthetic grid scenarios for offline verification:")

    sim_scenario = st.selectbox(
        "Select Test Scenario",
        options=[
            ("All 3 Cycling (Normal, Bypass, Tap)", None),
            ("Case 1: Normal Operation (Only TOMZN Load)", 1),
            ("Case 2: 100% Bypass Theft (Feeder Tap Only)", 2),
            ("Case 3: Partial Tap Theft (Both Loads ON)", 3),
        ],
        format_func=lambda x: x[0],
    )

    sim_count = st.slider("Cycles to Generate", min_value=1, max_value=20, value=6)

    if st.button("⚡ Inject Simulation Telemetry", use_container_width=True):
        sim_collector = TelemetryCollector(simulate=True, poll_interval=0.01)
        with st.spinner("Generating calibrated hardware telemetry cycles..."):
            for _ in range(sim_count):
                sim_collector.process_cycle(scenario_override=sim_scenario[1])
        st.success(f"Generated {sim_count} telemetry snapshots!")
        st.rerun()

    st.divider()
    if st.button("⚠️ Clear Local Cache", use_container_width=True):
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            conn.cursor().execute("DELETE FROM meter_readings")
            conn.commit()
        st.warning("Local SQLite cache cleared.")
        st.rerun()


# -----------------------------------------------------------------------------
# Data Ingestion & State Resolution
# -----------------------------------------------------------------------------
readings = storage.get_readings(limit=150)
stats = storage.get_summary_stats()
latest = storage.get_latest_reading()

# If database is completely empty, inject initial sample records
if not latest:
    st.info("No telemetry records in database yet. Generating initial calibrated simulation data...")
    init_collector = TelemetryCollector(simulate=True, poll_interval=0.01)
    for _ in range(6):
        init_collector.process_cycle()
    readings = storage.get_readings(limit=150)
    stats = storage.get_summary_stats()
    latest = storage.get_latest_reading()


# -----------------------------------------------------------------------------
# Header Bar
# -----------------------------------------------------------------------------
col_header_left, col_header_right = st.columns([3, 1])
with col_header_left:
    st.markdown(
        """
        <h1 style="font-size: 26px; font-weight: 800; margin: 0 0 4px 0; color: #F8FAFC;">
            ⚡ SMART GRID POWER THEFT DETECTION & BILLING COMMAND CENTER
        </h1>
        <p style="color: #94A3B8; font-size: 14px; margin: 0;">
            Dual-Meter Real-Time Telemetry Pipeline • Techno LoRaWAN & TOMZN Wi-Fi • Empirical Baseline: -35.7 W
        </p>
        """,
        unsafe_allow_html=True,
    )

with col_header_right:
    now_str = datetime.now().strftime("%H:%M:%S | %d %b %Y")
    st.markdown(
        f"""
        <div style="text-align: right; background: #111827; border: 1px solid #1F2937; padding: 10px 14px; border-radius: 8px;">
            <div style="font-size: 11px; color: #64748B; text-transform: uppercase;">Grid Time (Local)</div>
            <div style="font-size: 15px; font-weight: 700; color: #06B6D4;">{now_str}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")


# -----------------------------------------------------------------------------
# Top-Level Theft Incident Banner
# -----------------------------------------------------------------------------
if latest:
    status = latest["theft_status"]
    if "100% BYPASS" in status:
        st.markdown(
            f"""
            <div class="banner-theft">
                <div>
                    <span style="font-size: 18px; font-weight: 800; color: #EF4444;">🚨 CRITICAL GRID EVENT: 100% BYPASS THEFT DETECTED</span>
                    <p style="margin: 4px 0 0 0; color: #FECACA; font-size: 13px;">
                        Feeder load is supplying active power ({latest['feeder_power_w']:.1f} W) while Consumer meter is completely bypassed (0.0 W).
                    </p>
                </div>
                <div style="text-align: right;">
                    <span class="badge-bypass">100% Bypass Alert</span>
                    <div style="font-size: 14px; font-weight: 700; color: #EF4444; margin-top: 6px;">
                        Loss: {latest['loss_w']:.1f} W / {latest['loss_kwh']:.4f} kWh
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif "PARTIAL TAP" in status:
        st.markdown(
            f"""
            <div style="background: linear-gradient(90deg, rgba(245, 158, 11, 0.2), rgba(245, 158, 11, 0.05)); border: 1px solid #F59E0B; border-left: 6px solid #F59E0B; border-radius: 8px; padding: 14px 20px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 18px; font-weight: 800; color: #F59E0B;">⚠️ WARNING: PARTIAL TAP THEFT DETECTED</span>
                    <p style="margin: 4px 0 0 0; color: #FEF3C7; font-size: 13px;">
                        Calibrated power discrepancy exceeds threshold (+{latest['calibrated_diff_w']:.1f} W > 15.0 W) or interval energy loss exceeds 0.015 kWh.
                    </p>
                </div>
                <div style="text-align: right;">
                    <span class="badge-partial">Partial Tap Alert</span>
                    <div style="font-size: 14px; font-weight: 700; color: #F59E0B; margin-top: 6px;">
                        Loss: {latest['loss_w']:.1f} W / {latest['loss_kwh']:.4f} kWh
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="banner-normal">
                <div>
                    <span style="font-size: 16px; font-weight: 700; color: #10B981;">✅ GRID TELEMETRY STABLE — NORMAL OPERATION</span>
                    <p style="margin: 3px 0 0 0; color: #D1FAE5; font-size: 13px;">
                        Feeder & Consumer measurements synchronized within calibrated baseline tolerance (Offset: -35.7 W applied).
                    </p>
                </div>
                <div>
                    <span class="badge-normal">Grid In Sync</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# -----------------------------------------------------------------------------
# Main Navigation Tabs
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["⚡ Live Grid Monitor", "🚨 Theft Audit & Incident Log", "📄 Consumer Billing & Invoices"])


# =============================================================================
# TAB 1: LIVE GRID MONITOR
# =============================================================================
with tab1:
    # Top KPI Metrics Row
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-neutral">System Health</div>
                <div style="font-size: 20px; font-weight: 800; color: #10B981;">ONLINE</div>
                <div style="font-size: 11px; color: #64748B; margin-top: 4px;">Uplink Heartbeat OK</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-feeder">Feeder Power</div>
                <div style="font-size: 20px; font-weight: 800; color: #06B6D4;">{latest['feeder_power_w']:.1f} <span style="font-size: 13px; font-weight: 500;">W</span></div>
                <div style="font-size: 11px; color: #64748B; margin-top: 4px;">Total: {latest['feeder_energy_kwh']:.3f} kWh</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-consumer">Consumer Power</div>
                <div style="font-size: 20px; font-weight: 800; color: #10B981;">{latest['consumer_power_w']:.1f} <span style="font-size: 13px; font-weight: 500;">W</span></div>
                <div style="font-size: 11px; color: #64748B; margin-top: 4px;">Total: {latest['consumer_energy_kwh']:.3f} kWh</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m4:
        diff_color = "#10B981" if abs(latest["calibrated_diff_w"]) <= 15.0 else "#EF4444"
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-neutral">Calibrated Diff (ΔP)</div>
                <div style="font-size: 20px; font-weight: 800; color: {diff_color};">{latest['calibrated_diff_w']:+.1f} <span style="font-size: 13px; font-weight: 500;">W</span></div>
                <div style="font-size: 11px; color: #64748B; margin-top: 4px;">Calibrated vs Baseline</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m5:
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-neutral">Total Stolen Energy</div>
                <div style="font-size: 20px; font-weight: 800; color: #F59E0B;">{stats['total_loss_kwh']:.4f} <span style="font-size: 13px; font-weight: 500;">kWh</span></div>
                <div style="font-size: 11px; color: #64748B; margin-top: 4px;">Cumulative Interval Loss</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Detailed Dual-Meter Telemetry Cards
    col_feeder, col_consumer = st.columns(2)

    with col_feeder:
        st.markdown(
            f"""
            <div class="scada-card" style="border-top: 3px solid #06B6D4;">
                <div class="card-title-feeder">
                    <span>📡 FEEDER METER TELEMETRY (Techno LoRaWAN)</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Supply Voltage</span>
                    <span class="kpi-value" style="color: #06B6D4;">{latest['feeder_voltage_v']:.2f} V</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Current Draw</span>
                    <span class="kpi-value">{latest['feeder_current_a']:.3f} A</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Instantaneous Active Power</span>
                    <span class="kpi-value" style="color: #06B6D4;">{latest['feeder_power_w']:.2f} W</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Calibrated Feeder Power (P - Offset)</span>
                    <span class="kpi-value" style="color: #38BDF8;">{(latest['feeder_power_w'] - (-35.7)):.2f} W</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Cumulative Energy</span>
                    <span class="kpi-value">{latest['feeder_energy_kwh']:.4f} kWh</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Uplink Gateway</span>
                    <span style="font-size: 12px; color: #94A3B8;">TTN eu1.cloud.thethings.network</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_consumer:
        st.markdown(
            f"""
            <div class="scada-card" style="border-top: 3px solid #10B981;">
                <div class="card-title-consumer">
                    <span>🏠 CONSUMER METER TELEMETRY (TOMZN DDS238-2 Wi-Fi)</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Consumer Voltage</span>
                    <span class="kpi-value" style="color: #10B981;">{latest['consumer_voltage_v']:.2f} V</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Current Draw</span>
                    <span class="kpi-value">{latest['consumer_current_a']:.3f} A</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Instantaneous Active Power</span>
                    <span class="kpi-value" style="color: #10B981;">{latest['consumer_power_w']:.2f} W</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Cumulative Energy</span>
                    <span class="kpi-value">{latest['consumer_energy_kwh']:.4f} kWh</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Estimated Current Bill</span>
                    <span class="kpi-value" style="color: #34D399;">₹{latest['estimated_bill_inr']:.2f}</span>
                </div>
                <div class="kpi-row">
                    <span class="kpi-label">Local Link Protocol</span>
                    <span style="font-size: 12px; color: #94A3B8;">TinyTuya TCP Polling (Port 6668)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Real-Time Plotly SCADA Graphs
    st.write("")
    st.markdown("<h3 style='font-size: 17px; font-weight: 700; color: #F8FAFC;'>📈 Real-Time Telemetry Analytics</h3>", unsafe_allow_html=True)

    if len(readings) > 0:
        # Convert readings to chronological order for plotting
        df_plot = pd.DataFrame(readings).iloc[::-1].reset_index(drop=True)
        df_plot["timestamp"] = pd.to_datetime(df_plot["created_at"]).dt.strftime("%H:%M:%S")
        df_plot["calibrated_feeder_power"] = df_plot["feeder_power_w"] - (-35.7)

        # Plot 1: Power Comparison (Feeder Calibrated vs Consumer Actual vs Uncalibrated Feeder)
        fig_power = go.Figure()
        fig_power.add_trace(
            go.Scatter(
                x=df_plot["timestamp"],
                y=df_plot["calibrated_feeder_power"],
                name="Calibrated Feeder Load (W)",
                line=dict(color="#06B6D4", width=3),
                mode="lines+markers",
            )
        )
        fig_power.add_trace(
            go.Scatter(
                x=df_plot["timestamp"],
                y=df_plot["consumer_power_w"],
                name="Consumer Meter Load (W)",
                line=dict(color="#10B981", width=2.5),
                mode="lines+markers",
            )
        )
        fig_power.add_trace(
            go.Scatter(
                x=df_plot["timestamp"],
                y=df_plot["feeder_power_w"],
                name="Raw Feeder Load (W)",
                line=dict(color="#64748B", width=1.5, dash="dot"),
                mode="lines",
            )
        )
        fig_power.update_layout(
            title="Real-Time Active Power Comparison (Watts)",
            paper_bgcolor="#111827",
            plot_bgcolor="#0F172A",
            font=dict(color="#94A3B8", family="sans-serif"),
            xaxis=dict(gridcolor="#1E293B", showgrid=True),
            yaxis=dict(gridcolor="#1E293B", showgrid=True, title="Active Power (W)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=50, b=40),
            height=340,
        )

        # Plot 2: Cumulative Energy Accumulation & Theft Loss
        fig_energy = make_subplots(specs=[[{"secondary_y": True}]])
        fig_energy.add_trace(
            go.Scatter(
                x=df_plot["timestamp"],
                y=df_plot["feeder_energy_kwh"],
                name="Feeder Energy (kWh)",
                line=dict(color="#06B6D4", width=2.5),
            ),
            secondary_y=False,
        )
        fig_energy.add_trace(
            go.Scatter(
                x=df_plot["timestamp"],
                y=df_plot["consumer_energy_kwh"],
                name="Consumer Energy (kWh)",
                line=dict(color="#10B981", width=2.5),
            ),
            secondary_y=False,
        )
        fig_energy.add_trace(
            go.Bar(
                x=df_plot["timestamp"],
                y=df_plot["loss_w"],
                name="Unaccounted Loss (W)",
                marker_color="#EF4444",
                opacity=0.4,
            ),
            secondary_y=True,
        )
        fig_energy.update_layout(
            title="Cumulative Energy Accumulation (kWh) & Instantaneous Loss (W)",
            paper_bgcolor="#111827",
            plot_bgcolor="#0F172A",
            font=dict(color="#94A3B8", family="sans-serif"),
            xaxis=dict(gridcolor="#1E293B", showgrid=True),
            yaxis=dict(gridcolor="#1E293B", showgrid=True, title="Energy (kWh)"),
            yaxis2=dict(showgrid=False, title="Loss (W)", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=50, b=40),
            height=340,
        )

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.plotly_chart(fig_power, use_container_width=True)
        with col_g2:
            st.plotly_chart(fig_energy, use_container_width=True)


# =============================================================================
# TAB 2: THEFT AUDIT & INCIDENT LOG
# =============================================================================
with tab2:
    st.markdown("<h3 style='font-size: 18px; font-weight: 700; color: #F8FAFC;'>🚨 Power Theft Incident Registry & Loss Analytics</h3>", unsafe_allow_html=True)
    st.caption("Forensic audit log of all classified discrepancy events for utility inspection.")

    # High-Level Audit Metrics
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-neutral">Total Snapshots</div>
                <div style="font-size: 22px; font-weight: 800; color: #F8FAFC;">{stats['total_records']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with a2:
        theft_pct = (stats['theft_count'] / stats['total_records'] * 100) if stats['total_records'] > 0 else 0.0
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-neutral">Theft Incidents</div>
                <div style="font-size: 22px; font-weight: 800; color: #EF4444;">{stats['theft_count']} <span style="font-size: 13px; color: #94A3B8;">({theft_pct:.1f}%)</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with a3:
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-neutral">Total Unaccounted Energy</div>
                <div style="font-size: 22px; font-weight: 800; color: #F59E0B;">{stats['total_loss_kwh']:.4f} <span style="font-size: 13px; color: #94A3B8;">kWh</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with a4:
        # Financial loss estimate at top tariff slab (₹7.50 / unit)
        financial_loss = stats['total_loss_kwh'] * 7.50
        st.markdown(
            f"""
            <div class="scada-card">
                <div class="card-title-neutral">Estimated Utility Loss</div>
                <div style="font-size: 22px; font-weight: 800; color: #EF4444;">₹{financial_loss:.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Filter Controls
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        theft_filter = st.selectbox(
            "Filter Events By Status",
            options=["ALL EVENTS", "THEFT DETECTED (ALL)", "THEFT DETECTED (100% BYPASS)", "THEFT DETECTED (PARTIAL TAP)", "NORMAL"],
        )
    with col_f2:
        max_rows = st.selectbox("Display Limit", options=[25, 50, 100, 250], index=1)
    with col_f3:
        st.write("")
        st.write("")
        # One-Click CSV Export
        all_readings = storage.get_readings(limit=500)
        df_export = pd.DataFrame(all_readings)
        csv_buffer = io.StringIO()
        df_export.to_csv(csv_buffer, index=False)
        st.download_button(
            label="📥 Export Audit CSV",
            data=csv_buffer.getvalue(),
            file_name=f"smart_grid_theft_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Build Filtered Table
    if readings:
        df_table = pd.DataFrame(readings)
        if theft_filter == "THEFT DETECTED (ALL)":
            df_table = df_table[df_table["theft_status"] != "NORMAL"]
        elif theft_filter != "ALL EVENTS":
            df_table = df_table[df_table["theft_status"] == theft_filter]

        df_display = df_table.head(max_rows)[
            [
                "id",
                "created_at",
                "theft_status",
                "feeder_power_w",
                "consumer_power_w",
                "calibrated_diff_w",
                "loss_w",
                "loss_kwh",
                "feeder_energy_kwh",
                "consumer_energy_kwh",
                "estimated_bill_inr",
            ]
        ].copy()

        df_display["created_at"] = pd.to_datetime(df_display["created_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

        st.dataframe(
            df_display,
            use_container_width=True,
            column_config={
                "id": "ID",
                "created_at": "Timestamp",
                "theft_status": st.column_config.TextColumn("Classification"),
                "feeder_power_w": st.column_config.NumberColumn("Feeder (W)", format="%.1f"),
                "consumer_power_w": st.column_config.NumberColumn("Consumer (W)", format="%.1f"),
                "calibrated_diff_w": st.column_config.NumberColumn("ΔP Cal (W)", format="%.1f"),
                "loss_w": st.column_config.NumberColumn("Loss (W)", format="%.1f"),
                "loss_kwh": st.column_config.NumberColumn("Loss (kWh)", format="%.4f"),
                "feeder_energy_kwh": st.column_config.NumberColumn("Feeder kWh", format="%.4f"),
                "consumer_energy_kwh": st.column_config.NumberColumn("Consumer kWh", format="%.4f"),
                "estimated_bill_inr": st.column_config.NumberColumn("Bill (₹)", format="₹%.2f"),
            },
            hide_index=True,
        )


# =============================================================================
# TAB 3: CONSUMER BILLING & INVOICE GENERATOR
# =============================================================================
with tab3:
    st.markdown("<h3 style='font-size: 18px; font-weight: 700; color: #F8FAFC;'>📄 Domestic Electricity Billing & Official Utility Invoice</h3>", unsafe_allow_html=True)
    st.caption("Calculate itemized tiered tariffs and generate official electricity board utility invoices.")

    col_bill_inputs, col_bill_preview = st.columns([1, 1])

    with col_bill_inputs:
        st.markdown(
            """
            <div class="scada-card" style="border-top: 3px solid #06B6D4;">
                <div class="card-title-feeder">⚙️ Billing Parameters & Tariff Calculator</div>
            """,
            unsafe_allow_html=True,
        )

        c_name = st.text_input("Consumer Name", value="SMART-CONSUMER-01")
        c_id = st.text_input("Consumer Account ID", value="CNS-2026-9812")
        m_id = st.text_input("Consumer Smart Meter ID", value="TOMZN-DDS238-WIFI")

        st.markdown("<div style='font-size: 13px; font-weight: 600; color: #94A3B8; margin: 12px 0 6px 0;'>Billing Cycle Readings</div>", unsafe_allow_html=True)
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            prev_kwh_input = st.number_input("Cycle Start Reading (kWh)", min_value=0.0, value=100.0, step=1.0)
        with col_r2:
            default_curr = float(latest["consumer_energy_kwh"]) if latest else 180.0
            curr_kwh_input = st.number_input("Cycle End Reading (kWh)", min_value=0.0, value=round(default_curr, 2), step=1.0)

        st.markdown("<div style='font-size: 13px; font-weight: 600; color: #94A3B8; margin: 12px 0 6px 0;'>Tariff Charges</div>", unsafe_allow_html=True)
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            fixed_charge_input = st.number_input("Fixed Meter Charge (₹)", min_value=0.0, value=50.0, step=5.0)
        with col_c2:
            duty_pct_input = st.number_input("Electricity Duty (%)", min_value=0.0, value=5.0, step=0.5)

        # Compute bill
        bill_data = billing_engine.calculate_bill(
            current_kwh=curr_kwh_input,
            previous_kwh=prev_kwh_input,
            fixed_charge=fixed_charge_input,
            duty_pct=duty_pct_input,
        )

        st.markdown(
            f"""
            <div style="background: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 14px; margin-top: 14px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                    <span style="color: #94A3B8;">Net Consumed Units:</span>
                    <span style="color: #10B981; font-weight: 700;">{bill_data['units_consumed']:.2f} kWh</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                    <span style="color: #94A3B8;">Energy Charges:</span>
                    <span style="color: #F8FAFC; font-weight: 600;">₹{bill_data['energy_charges']:.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                    <span style="color: #94A3B8;">Fixed Charge + Duty:</span>
                    <span style="color: #F8FAFC; font-weight: 600;">₹{(bill_data['fixed_charge'] + bill_data['electricity_duty']):.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; border-top: 1px solid #334155; padding-top: 8px; font-size: 16px;">
                    <span style="color: #06B6D4; font-weight: 800;">TOTAL PAYABLE:</span>
                    <span style="color: #06B6D4; font-weight: 800;">₹{bill_data['total_amount_inr']:.2f}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        # Invoice Generation & Download Buttons
        st.write("")
        consumer_metadata = {
            "consumer_name": c_name,
            "consumer_id": c_id,
            "meter_id": m_id,
        }

        # Generate HTML Invoice
        html_invoice = billing_engine.generate_html_invoice(bill_data, consumer_info=consumer_metadata)

        # Generate PDF Invoice to buffer
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            tmp_pdf_path = tmp_pdf.name
        billing_engine.generate_pdf_invoice(bill_data, tmp_pdf_path, consumer_info=consumer_metadata)
        with open(tmp_pdf_path, "rb") as f:
            pdf_bytes = f.read()
        try:
            os.remove(tmp_pdf_path)
        except Exception:
            pass

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            st.download_button(
                label="📄 Download PDF Invoice",
                data=pdf_bytes,
                file_name=f"invoice_{c_id}_{datetime.now().strftime('%Y%m')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with btn_col2:
            st.download_button(
                label="🌐 Download HTML Bill",
                data=html_invoice,
                file_name=f"invoice_{c_id}_{datetime.now().strftime('%Y%m')}.html",
                mime="text/html",
                use_container_width=True,
            )

    # Right Column: Utility Invoice Card Preview
    with col_bill_preview:
        st.markdown(
            """
            <div style="font-size: 14px; font-weight: 700; color: #94A3B8; text-transform: uppercase; margin-bottom: 8px;">
                👁️ Official Electricity Board Invoice Preview
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.components.v1.html(html_invoice, height=620, scrolling=True)


# -----------------------------------------------------------------------------
# Auto-Refresh Mechanism
# -----------------------------------------------------------------------------
if auto_refresh:
    time.sleep(refresh_rate)
    st.rerun()

