"""
collector.py
============
Smart Grid Telemetry Collector & Dual-Meter Ingestion Service.

Ingestion Sources:
1. Feeder Meter (Techno LoRaWAN Energy Meter):
   - Protocol: MQTT (The Things Network v3)
   - Broker: eu1.cloud.thethings.network (Port 8883 / 1883)
   - Payload: uplink_message.decoded_payload (voltage_V, current_A, power_W, energy_kWh)
2. Consumer Meter (TOMZN DDS238-2 Wi-Fi Smart Meter):
   - Protocol: TinyTuya Local LAN Polling
   - DPS: 20 (V/10), 18 (mA/1000), 19 (W/10), 17 or 1 (Total kWh/100)

Simulation Mode (--simulate):
- Replicates all 3 physical hardware test scenarios offline:
  * Case 1: Normal (Only TOMZN load) -> Feeder ~22.7W, Consumer ~58.4W
  * Case 2: 100% Bypass Theft -> Feeder ~22.7W, Consumer 0.0W
  * Case 3: Partial Tap Theft -> Feeder power & energy > Consumer while Consumer draws ~58.3W

Data Flow:
Raw Feeder & Consumer Telemetry -> Synchronizer -> DualCheckTheftEngine -> BillingEngine -> SmartGridStorage (SQLite + Supabase Cloud)
"""

import os
import sys
import time
import json
import random
import argparse
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from dotenv import load_dotenv

from theft_engine import DualCheckTheftEngine, MeterSnapshot
from billing import BillingEngine
from storage import SmartGridStorage

load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("SmartGridCollector")

# Terminal Color Codes for SCADA CLI
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


class TelemetryCollector:
    """
    Manages real-time ingestion from Feeder (LoRaWAN TTN) and Consumer (TinyTuya Wi-Fi)
    meters, or runs high-fidelity multi-case hardware simulations.
    """

    def __init__(self, simulate: bool = False, poll_interval: float = 5.0):
        self.simulate = simulate
        self.poll_interval = poll_interval

        # Engines
        self.theft_engine = DualCheckTheftEngine()
        self.billing_engine = BillingEngine()
        self.storage = SmartGridStorage()

        # Telemetry State Caches
        self.latest_feeder: Optional[MeterSnapshot] = None
        self.latest_consumer: Optional[MeterSnapshot] = None
        self.prev_feeder: Optional[MeterSnapshot] = None
        self.prev_consumer: Optional[MeterSnapshot] = None
        self.last_feeder_rx_time: Optional[datetime] = None
        self.last_consumer_rx_time: Optional[datetime] = None

        # Cumulative counters for simulation
        self._sim_feeder_kwh = 142.5000
        self._sim_consumer_kwh = 142.1000
        self._sim_step = 0

        # TTN MQTT Client (Live mode)
        self.mqtt_client = None
        # TinyTuya Device (Live mode)
        self.tuya_device = None

        if not self.simulate:
            self._setup_live_clients()

    def _setup_live_clients(self):
        """Initializes TTN MQTT and TinyTuya clients for live hardware mode."""
        # 1. Setup TTN MQTT
        ttn_broker = os.getenv("TTN_BROKER", "eu1.cloud.thethings.network")
        ttn_port = int(os.getenv("TTN_PORT", "8883"))
        ttn_app_id = os.getenv("TTN_APP_ID", "energy-meter-iot-app")
        ttn_api_key = os.getenv("TTN_API_KEY", "")
        ttn_device_id = os.getenv("TTN_DEVICE_ID", "energy-device")

        if ttn_api_key:
            try:
                import paho.mqtt.client as mqtt

                def on_connect(client, userdata, flags, rc):
                    if rc == 0:
                        logger.info("Connected to TTN MQTT Broker (%s:%s)", ttn_broker, ttn_port)
                        topic = f"v3/{ttn_app_id}@ttn/devices/{ttn_device_id}/up"
                        client.subscribe(topic)
                        logger.info("Subscribed to TTN uplink topic: %s", topic)
                    else:
                        logger.error("TTN MQTT connection failed with return code %s", rc)

                def on_message(client, userdata, msg):
                    self._handle_ttn_message(msg.payload)

                self.mqtt_client = mqtt.Client()
                self.mqtt_client.username_pw_set(f"{ttn_app_id}@ttn", ttn_api_key)
                if ttn_port == 8883:
                    self.mqtt_client.tls_set()
                self.mqtt_client.on_connect = on_connect
                self.mqtt_client.on_message = on_message
                self.mqtt_client.connect_async(ttn_broker, ttn_port, 60)
                self.mqtt_client.loop_start()
            except Exception as e:
                logger.warning("Could not start TTN MQTT client: %s", e)
        else:
            logger.warning("TTN_API_KEY is empty in .env. Live Feeder telemetry will wait for packets.")

        # 2. Setup TinyTuya
        tuya_id = os.getenv("TUYA_DEVICE_ID", "")
        tuya_ip = os.getenv("TUYA_IP_ADDRESS", "")
        tuya_key = os.getenv("TUYA_LOCAL_KEY", "")
        tuya_ver = float(os.getenv("TUYA_VERSION", "3.3"))

        if tuya_id and tuya_ip and tuya_key and tuya_id != "mock_device_id":
            try:
                import tinytuya
                self.tuya_device = tinytuya.OutletDevice(tuya_id, tuya_ip, tuya_key)
                self.tuya_device.set_version(tuya_ver)
                logger.info("Configured TinyTuya client for TOMZN meter at %s", tuya_ip)
            except Exception as e:
                logger.warning("Failed to configure TinyTuya client: %s", e)
        else:
            logger.warning("Tuya credentials not fully populated in .env.")

    def _handle_ttn_message(self, raw_payload: bytes):
        """Decodes uplink JSON message from Techno LoRaWAN energy meter."""
        try:
            data = json.loads(raw_payload.decode("utf-8"))
            decoded = data.get("uplink_message", {}).get("decoded_payload", {})
            v = float(decoded.get("voltage_V", 230.0))
            a = float(decoded.get("current_A", 0.0))
            w = float(decoded.get("power_W", 0.0))
            kwh = float(decoded.get("energy_kWh", 0.0))

            self.prev_feeder = self.latest_feeder
            self.latest_feeder = MeterSnapshot(voltage_v=v, current_a=a, power_w=w, energy_kwh=kwh)
            self.last_feeder_rx_time = datetime.now(timezone.utc)
            logger.info("Received LoRaWAN Feeder Uplink: %.1fV, %.3fA, %.1fW, %.4fkWh", v, a, w, kwh)
        except Exception as e:
            logger.error("Error decoding TTN uplink: %s", e)

    def _poll_consumer_tuya(self) -> Optional[MeterSnapshot]:
        """Polls TOMZN DDS238-2 Wi-Fi Smart Meter via local LAN TinyTuya."""
        if not self.tuya_device:
            return None
        try:
            status = self.tuya_device.status()
            dps = status.get("dps", {})

            # DPS Mappings:
            # 20: Voltage in 0.1 V
            # 18: Current in mA
            # 19: Power in 0.1 W
            # 17 or 1: Total kWh in 0.01 kWh
            raw_v = dps.get("20", 2300)
            raw_a = dps.get("18", 0)
            raw_w = dps.get("19", 0)
            raw_kwh = dps.get("17", dps.get("1", 0))

            v = float(raw_v) / 10.0
            a = float(raw_a) / 1000.0
            w = float(raw_w) / 10.0
            kwh = float(raw_kwh) / 100.0

            snapshot = MeterSnapshot(voltage_v=v, current_a=a, power_w=w, energy_kwh=kwh)
            self.prev_consumer = self.latest_consumer
            self.latest_consumer = snapshot
            self.last_consumer_rx_time = datetime.now(timezone.utc)
            return snapshot
        except Exception as e:
            logger.warning("TinyTuya poll failed: %s", e)
            return None

    def generate_simulation_snapshot(self, scenario: int = 1) -> tuple[MeterSnapshot, MeterSnapshot]:
        """
        Generates realistic simulation data for the 3 specified hardware test scenarios:
        - Case 1 (Normal): Feeder ~22.7W (229.2V, 0.099A), Consumer ~58.4W (229.3V, 0.255A)
        - Case 2 (100% Bypass Theft): Feeder ~22.7W, Consumer 0.0W (0.000A)
        - Case 3 (Partial Tap Theft): Both ON; Feeder increments faster while Consumer draws ~58.3W
        """
        noise_v = random.uniform(-0.4, 0.4)
        noise_p = random.uniform(-0.3, 0.3)

        if scenario == 1:
            # Case 1: Normal (Only TOMZN load)
            f_v = 229.2 + noise_v
            f_w = 22.7 + noise_p
            f_a = round(f_w / f_v, 3)

            c_v = 229.3 + noise_v
            c_w = 58.4 + noise_p
            c_a = round(c_w / c_v, 3)

            # In normal operation, energy increments symmetrically
            kwh_inc = 0.0020 + random.uniform(0.0001, 0.0003)
            self._sim_feeder_kwh += kwh_inc
            self._sim_consumer_kwh += kwh_inc

        elif scenario == 2:
            # Case 2: 100% Bypass Theft (Only Feeder tap load, consumer bypassed)
            f_v = 229.2 + noise_v
            f_w = 22.7 + noise_p
            f_a = round(f_w / f_v, 3)

            c_v = 229.1 + noise_v
            c_w = 0.0
            c_a = 0.000

            # Only Feeder energy accumulates; Consumer energy is frozen
            self._sim_feeder_kwh += (0.0020 + random.uniform(0.0001, 0.0003))
            # Consumer gets 0 kWh increment

        else:
            # Case 3: Partial Tap Theft (Both loads ON, Feeder draws additional tapped load)
            # Consumer draws normal load
            c_v = 229.2 + noise_v
            c_w = 58.3 + noise_p
            c_a = round(c_w / c_v, 3)

            # Feeder supplies both consumer load + illegal tap load (e.g. 40W tap)
            # Uncalibrated feeder = 22.7 + 40.0 = 62.7W (calibrated = 98.4W vs 58.3W consumer)
            f_v = 229.1 + noise_v
            f_w = 62.7 + noise_p
            f_a = round(f_w / f_v, 3)

            # Feeder increments much faster than consumer
            self._sim_feeder_kwh += 0.0180  # exceeds 0.015 kWh threshold delta
            self._sim_consumer_kwh += 0.0020

        feeder = MeterSnapshot(
            voltage_v=round(f_v, 1),
            current_a=round(f_a, 3),
            power_w=round(f_w, 1),
            energy_kwh=round(self._sim_feeder_kwh, 4),
        )
        consumer = MeterSnapshot(
            voltage_v=round(c_v, 1),
            current_a=round(c_a, 3),
            power_w=round(c_w, 1),
            energy_kwh=round(self._sim_consumer_kwh, 4),
        )
        return feeder, consumer

    def process_cycle(self, scenario_override: Optional[int] = None) -> Dict[str, Any]:
        """
        Runs one ingestion and evaluation cycle:
        1. Obtains snapshots for Feeder and Consumer.
        2. Evaluates with DualCheckTheftEngine.
        3. Computes estimated consumer billing.
        4. Persists record to local cache & cloud.
        5. Displays SCADA console output.
        """
        if self.simulate:
            # Select scenario (1, 2, or 3)
            if scenario_override is not None:
                current_scenario = scenario_override
            else:
                # Cycle every 3 iterations across Case 1 -> Case 2 -> Case 3
                cycle_idx = (self._sim_step // 3) % 3
                current_scenario = cycle_idx + 1

            feeder_snap, consumer_snap = self.generate_simulation_snapshot(scenario=current_scenario)
            self._sim_step += 1
        else:
            # Live hardware mode
            self._poll_consumer_tuya()
            feeder_snap = self.latest_feeder or MeterSnapshot(229.2, 0.099, 22.7, 142.50)
            consumer_snap = self.latest_consumer or MeterSnapshot(229.3, 0.255, 58.4, 142.10)

        # Evaluate power theft
        eval_result = self.theft_engine.evaluate(
            feeder=feeder_snap,
            consumer=consumer_snap,
            prev_feeder=self.prev_feeder,
            prev_consumer=self.prev_consumer,
        )

        # Update previous snapshots
        self.prev_feeder = feeder_snap
        self.prev_consumer = consumer_snap

        # Compute current billing estimate
        bill_data = self.billing_engine.calculate_bill(
            current_kwh=consumer_snap.energy_kwh,
            previous_kwh=100.0,  # Baseline cycle start for running estimate
        )

        # Construct unified reading payload
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "feeder_voltage_v": feeder_snap.voltage_v,
            "feeder_current_a": feeder_snap.current_a,
            "feeder_power_w": feeder_snap.power_w,
            "feeder_energy_kwh": feeder_snap.energy_kwh,
            "consumer_voltage_v": consumer_snap.voltage_v,
            "consumer_current_a": consumer_snap.current_a,
            "consumer_power_w": consumer_snap.power_w,
            "consumer_energy_kwh": consumer_snap.energy_kwh,
            "calibrated_diff_w": eval_result.calibrated_diff_w,
            "energy_diff_kwh": eval_result.energy_diff_kwh,
            "theft_status": eval_result.theft_status,
            "loss_w": eval_result.loss_w,
            "loss_kwh": eval_result.loss_kwh,
            "billed_units_kwh": bill_data["units_consumed"],
            "estimated_bill_inr": bill_data["total_amount_inr"],
        }

        # Save to database
        record_id = self.storage.record_reading(payload)
        payload["id"] = record_id

        # Print SCADA formatted log
        self._print_scada_log(payload, eval_result)
        return payload

    def _print_scada_log(self, payload: Dict[str, Any], result: Any):
        """Prints a high-contrast SCADA console status line."""
        status = payload["theft_status"]
        if "100% BYPASS" in status:
            status_badge = f"{C_BOLD}{C_RED}[ 🚨 THEFT: 100% BYPASS ]{C_RESET}"
        elif "PARTIAL TAP" in status:
            status_badge = f"{C_BOLD}{C_YELLOW}[ ⚠️ THEFT: PARTIAL TAP ]{C_RESET}"
        else:
            status_badge = f"{C_BOLD}{C_GREEN}[  NORMAL  ]{C_RESET}"

        f_txt = f"{C_CYAN}FEEDER:{C_RESET} {payload['feeder_voltage_v']:.1f}V | {payload['feeder_current_a']:.3f}A | {payload['feeder_power_w']:.1f}W | {payload['feeder_energy_kwh']:.4f}kWh"
        c_txt = f"{C_GREEN}CONSUMER:{C_RESET} {payload['consumer_voltage_v']:.1f}V | {payload['consumer_current_a']:.3f}A | {payload['consumer_power_w']:.1f}W | {payload['consumer_energy_kwh']:.4f}kWh"
        diff_txt = f"ΔP_cal: {payload['calibrated_diff_w']:+.1f}W | Loss: {payload['loss_w']:.1f}W / {payload['loss_kwh']:.4f}kWh"
        bill_txt = f"Bill: ₹{payload['estimated_bill_inr']:.2f}"

        print(f"[{payload['created_at'][11:19]}] {status_badge}  {f_txt}  ||  {c_txt}  ||  {diff_txt}  ||  {bill_txt}")

    def run(self, max_iterations: Optional[int] = None, scenario_override: Optional[int] = None):
        """Runs the continuous telemetry collection loop."""
        mode_str = f"SIMULATION (Scenario: {scenario_override or 'All 3 Cycling'})" if self.simulate else "LIVE HARDWARE"
        print(f"\n{C_BOLD}{'='*80}{C_RESET}")
        print(f"{C_BOLD}   ⚡ SMART GRID TELEMETRY & POWER THEFT COLLECTOR SERVICE ⚡{C_RESET}")
        print(f"   Mode: {mode_str} | Interval: {self.poll_interval}s | Storage: {self.storage.db_path}")
        print(f"{C_BOLD}{'='*80}{C_RESET}\n")

        count = 0
        try:
            while True:
                self.process_cycle(scenario_override=scenario_override)
                count += 1
                if max_iterations and count >= max_iterations:
                    break
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("\nShutting down collector gracefully...")
        finally:
            if self.mqtt_client:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="IoT Smart Grid Power Theft Telemetry Collector")
    parser.add_argument("--simulate", action="store_true", help="Run in offline simulation mode for hardware test cases")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3], default=None, help="Lock simulation to specific scenario (1: Normal, 2: Bypass, 3: Partial Tap)")
    parser.add_argument("--duration", type=int, default=None, help="Run for specific number of iterations and exit")
    parser.add_argument("--interval", type=float, default=3.0, help="Polling/simulation interval in seconds (default: 3.0s)")

    args = parser.parse_args()
    collector = TelemetryCollector(simulate=args.simulate, poll_interval=args.interval)
    collector.run(max_iterations=args.duration, scenario_override=args.scenario)


if __name__ == "__main__":
    main()

