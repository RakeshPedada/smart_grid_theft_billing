"""
test_phase1.py
==============
Automated Unit & Integration Test Suite for Phase 1.

Verifies:
1. Calibrated Dual-Check Theft Detection Engine (All 3 scenarios + edge cases).
2. Automated Tiered Domestic Electricity Billing Engine (All slabs + duty + fixed charge).
3. Hybrid Storage Persistence (SQLite creation, record storage, query interface, summary stats).
4. HTML, PDF, and CSV Bill Invoice generation.
5. End-to-end Collector Simulation Pipeline.
"""

import os
import unittest
import tempfile
import sqlite3
from theft_engine import DualCheckTheftEngine, MeterSnapshot
from billing import BillingEngine
from storage import SmartGridStorage
from collector import TelemetryCollector


class TestDualCheckTheftEngine(unittest.TestCase):
    def setUp(self):
        # Baseline offset: -35.7 W, Power threshold: 15.0 W, Energy threshold: 0.015 kWh
        self.engine = DualCheckTheftEngine(
            baseline_offset_w=-35.7,
            power_threshold_w=15.0,
            energy_threshold_kwh=0.015,
        )

    def test_case_1_normal_operation(self):
        """Case 1 (Normal): Feeder ~22.7W, Consumer ~58.4W."""
        feeder = MeterSnapshot(voltage_v=229.2, current_a=0.099, power_w=22.7, energy_kwh=100.005)
        consumer = MeterSnapshot(voltage_v=229.3, current_a=0.255, power_w=58.4, energy_kwh=100.005)
        prev_f = MeterSnapshot(voltage_v=229.2, current_a=0.099, power_w=22.7, energy_kwh=100.000)
        prev_c = MeterSnapshot(voltage_v=229.3, current_a=0.255, power_w=58.4, energy_kwh=100.000)

        result = self.engine.evaluate(feeder, consumer, prev_f, prev_c)

        # Calibrated Feeder W = 22.7 - (-35.7) = 58.4 W
        # Calibrated Diff = 58.4 - 58.4 = 0.0 W
        self.assertEqual(result.theft_status, "NORMAL")
        self.assertFalse(result.is_theft)
        self.assertAlmostEqual(result.calibrated_diff_w, 0.0, places=1)
        self.assertEqual(result.loss_w, 0.0)
        self.assertEqual(result.loss_kwh, 0.0)

    def test_case_2_100_percent_bypass_theft(self):
        """Case 2 (100% Bypass Theft): Feeder ~22.7W, Consumer 0.0W."""
        feeder = MeterSnapshot(voltage_v=229.2, current_a=0.099, power_w=22.7, energy_kwh=100.010)
        consumer = MeterSnapshot(voltage_v=229.1, current_a=0.000, power_w=0.0, energy_kwh=100.000)
        prev_f = MeterSnapshot(voltage_v=229.2, current_a=0.099, power_w=22.7, energy_kwh=100.000)
        prev_c = MeterSnapshot(voltage_v=229.1, current_a=0.000, power_w=0.0, energy_kwh=100.000)

        result = self.engine.evaluate(feeder, consumer, prev_f, prev_c)

        self.assertEqual(result.theft_status, "THEFT DETECTED (100% BYPASS)")
        self.assertTrue(result.is_theft)
        self.assertGreater(result.loss_w, 0.0)
        self.assertAlmostEqual(result.loss_kwh, 0.010, places=3)

    def test_case_3_partial_tap_theft_power_discrepancy(self):
        """Case 3 (Partial Tap Theft): Discrepancy > 15.0W."""
        # Feeder draws 62.7W (uncalibrated) -> Calibrated = 62.7 - (-35.7) = 98.4W
        # Consumer draws 58.3W -> Calibrated Diff = 98.4 - 58.3 = 40.1W (> 15.0W)
        feeder = MeterSnapshot(voltage_v=229.1, current_a=0.274, power_w=62.7, energy_kwh=100.020)
        consumer = MeterSnapshot(voltage_v=229.2, current_a=0.254, power_w=58.3, energy_kwh=100.002)
        prev_f = MeterSnapshot(voltage_v=229.1, current_a=0.274, power_w=62.7, energy_kwh=100.000)
        prev_c = MeterSnapshot(voltage_v=229.2, current_a=0.254, power_w=58.3, energy_kwh=100.000)

        result = self.engine.evaluate(feeder, consumer, prev_f, prev_c)

        self.assertEqual(result.theft_status, "THEFT DETECTED (PARTIAL TAP)")
        self.assertTrue(result.is_theft)
        self.assertGreater(result.calibrated_diff_w, 15.0)
        self.assertAlmostEqual(result.loss_w, 40.1, places=1)

    def test_case_3_partial_tap_theft_energy_loss(self):
        """Case 3 (Partial Tap Theft): Interval energy loss > 0.015 kWh."""
        # Feeder increments by 0.020 kWh while consumer increments by 0.002 kWh -> delta = 0.018 kWh > 0.015 kWh
        feeder = MeterSnapshot(voltage_v=229.1, current_a=0.100, power_w=22.7, energy_kwh=100.020)
        consumer = MeterSnapshot(voltage_v=229.2, current_a=0.254, power_w=58.4, energy_kwh=100.002)
        prev_f = MeterSnapshot(voltage_v=229.1, current_a=0.100, power_w=22.7, energy_kwh=100.000)
        prev_c = MeterSnapshot(voltage_v=229.2, current_a=0.254, power_w=58.4, energy_kwh=100.000)

        result = self.engine.evaluate(feeder, consumer, prev_f, prev_c)

        self.assertEqual(result.theft_status, "THEFT DETECTED (PARTIAL TAP)")
        self.assertTrue(result.is_theft)
        self.assertAlmostEqual(result.energy_diff_kwh, 0.018, places=3)
        self.assertAlmostEqual(result.loss_kwh, 0.018, places=3)

    def test_grid_idle_state(self):
        """Idle Grid (0W on both): No false positive."""
        feeder = MeterSnapshot(voltage_v=229.0, current_a=0.000, power_w=0.0, energy_kwh=100.0)
        consumer = MeterSnapshot(voltage_v=229.0, current_a=0.000, power_w=0.0, energy_kwh=100.0)
        result = self.engine.evaluate(feeder, consumer)

        self.assertEqual(result.theft_status, "NORMAL")
        self.assertFalse(result.is_theft)
        self.assertEqual(result.loss_w, 0.0)


class TestBillingEngine(unittest.TestCase):
    def setUp(self):
        # 0-50 @ 4.5, 51-150 @ 6.0, >150 @ 7.5, fixed=50.0, duty=5%
        self.engine = BillingEngine()

    def test_slab_1_calculation(self):
        """Test consumption within Slab 1 (40 units)."""
        bill = self.engine.calculate_bill(current_kwh=140.0, previous_kwh=100.0)
        # Units = 40.0
        # Energy = 40 * 4.50 = 180.0
        # Fixed = 50.0
        # Duty = 5% of 180 = 9.0
        # Total = 180 + 50 + 9 = 239.0
        self.assertEqual(bill["units_consumed"], 40.0)
        self.assertEqual(bill["energy_charges"], 180.0)
        self.assertEqual(bill["fixed_charge"], 50.0)
        self.assertEqual(bill["electricity_duty"], 9.0)
        self.assertEqual(bill["total_amount_inr"], 239.0)

    def test_slab_2_calculation(self):
        """Test consumption across Slab 1 and Slab 2 (120 units)."""
        bill = self.engine.calculate_bill(current_kwh=220.0, previous_kwh=100.0)
        # Units = 120.0
        # Slab 1: 50 * 4.50 = 225.0
        # Slab 2: 70 * 6.00 = 420.0
        # Energy = 225 + 420 = 645.0
        # Fixed = 50.0
        # Duty = 5% of 645 = 32.25
        # Total = 645 + 50 + 32.25 = 727.25
        self.assertEqual(bill["units_consumed"], 120.0)
        self.assertEqual(bill["energy_charges"], 645.0)
        self.assertEqual(bill["electricity_duty"], 32.25)
        self.assertEqual(bill["total_amount_inr"], 727.25)

    def test_slab_3_calculation(self):
        """Test consumption across all 3 Slabs (200 units)."""
        bill = self.engine.calculate_bill(current_kwh=300.0, previous_kwh=100.0)
        # Units = 200.0
        # Slab 1: 50 * 4.50 = 225.0
        # Slab 2: 100 * 6.00 = 600.0
        # Slab 3: 50 * 7.50 = 375.0
        # Energy = 225 + 600 + 375 = 1200.0
        # Fixed = 50.0
        # Duty = 5% of 1200 = 60.0
        # Total = 1200 + 50 + 60 = 1310.0
        self.assertEqual(bill["units_consumed"], 200.0)
        self.assertEqual(bill["energy_charges"], 1200.0)
        self.assertEqual(bill["electricity_duty"], 60.0)
        self.assertEqual(bill["total_amount_inr"], 1310.0)

    def test_html_and_pdf_generation(self):
        """Verify HTML and PDF invoice documents render correctly."""
        bill = self.engine.calculate_bill(current_kwh=180.0, previous_kwh=100.0)
        html = self.engine.generate_html_invoice(bill)
        self.assertIn("SMART GRID UTILITY CORPORATION", html)
        self.assertIn("Official Invoice", html)
        self.assertIn("80.00", html)
        self.assertIn("Net Units Billed", html)

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "test_invoice.pdf")
            self.engine.generate_pdf_invoice(bill, pdf_path)
            self.assertTrue(os.path.exists(pdf_path))
            self.assertGreater(os.path.getsize(pdf_path), 1000)

            csv_path = os.path.join(tmpdir, "test_audit.csv")
            self.engine.export_audit_csv([{"id": 1, "theft_status": "NORMAL"}], csv_path)
            self.assertTrue(os.path.exists(csv_path))


class TestStorageAndCollectorSimulation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_grid.db")
        self.storage = SmartGridStorage(db_path=self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_sqlite_persistence_and_queries(self):
        """Test writing and reading readings from SQLite fallback."""
        sample_data = {
            "created_at": "2026-11-18T18:00:00Z",
            "feeder_voltage_v": 229.2,
            "feeder_current_a": 0.099,
            "feeder_power_w": 22.7,
            "feeder_energy_kwh": 142.50,
            "consumer_voltage_v": 229.3,
            "consumer_current_a": 0.255,
            "consumer_power_w": 58.4,
            "consumer_energy_kwh": 142.10,
            "calibrated_diff_w": 0.0,
            "energy_diff_kwh": 0.0,
            "theft_status": "NORMAL",
            "loss_w": 0.0,
            "loss_kwh": 0.0,
            "billed_units_kwh": 42.10,
            "estimated_bill_inr": 239.0,
        }
        rec_id = self.storage.record_reading(sample_data)
        self.assertGreaterEqual(rec_id, 1)

        readings = self.storage.get_readings(limit=10)
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0]["theft_status"], "NORMAL")
        self.assertEqual(readings[0]["feeder_power_w"], 22.7)

    def test_collector_simulation_pipeline(self):
        """Test collector running in simulation mode for all 3 scenarios."""
        collector = TelemetryCollector(simulate=True, poll_interval=0.01)
        collector.storage = self.storage  # inject isolated test db

        # Run Case 1 (Normal)
        r1 = collector.process_cycle(scenario_override=1)
        self.assertEqual(r1["theft_status"], "NORMAL")

        # Run Case 2 (100% Bypass)
        r2 = collector.process_cycle(scenario_override=2)
        self.assertEqual(r2["theft_status"], "THEFT DETECTED (100% BYPASS)")
        self.assertGreater(r2["loss_w"], 0.0)

        # Run Case 3 (Partial Tap)
        r3 = collector.process_cycle(scenario_override=3)
        self.assertEqual(r3["theft_status"], "THEFT DETECTED (PARTIAL TAP)")

        # Verify summary stats
        stats = self.storage.get_summary_stats()
        self.assertEqual(stats["total_records"], 3)
        self.assertEqual(stats["theft_count"], 2)


if __name__ == "__main__":
    unittest.main()
