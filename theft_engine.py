"""
theft_engine.py
================
Dual-Check Power Theft Detection Engine for Smart Grid Telemetry.

Features:
1. Hardware Calibration:
   Accounts for empirical hardware calibration offset (BASELINE_OFFSET_W = -35.7 W)
   because the Techno LoRaWAN meter's instantaneous power register quantizes
   low loads while cumulative energy_kWh increments accurately.
2. Dual-Check Classification:
   - NORMAL: Grid telemetry balanced within tolerance.
   - THEFT DETECTED (100% BYPASS): Feeder draws power (>5.0 W) while Consumer meter reads 0.0 W.
   - THEFT DETECTED (PARTIAL TAP): Calibrated power discrepancy > 15.0 W OR
     interval energy loss (delta_feeder_kwh - delta_consumer_kwh) > 0.015 kWh.
3. Quantified Loss Tracking:
   Tracks instantaneous unaccounted watts (loss_w) and interval unaccounted energy (loss_kwh).
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASELINE_OFFSET_W = float(os.getenv("BASELINE_OFFSET_W", "-35.7"))
DEFAULT_POWER_THRESHOLD_W = float(os.getenv("POWER_THEFT_THRESHOLD_W", "15.0"))
DEFAULT_ENERGY_THRESHOLD_KWH = float(os.getenv("ENERGY_THEFT_THRESHOLD_KWH", "0.015"))


@dataclass
class MeterSnapshot:
    voltage_v: float
    current_a: float
    power_w: float
    energy_kwh: float


@dataclass
class TheftEvaluationResult:
    theft_status: str
    calibrated_diff_w: float
    energy_diff_kwh: float
    loss_w: float
    loss_kwh: float
    is_theft: bool
    details: str


class DualCheckTheftEngine:
    """
    Evaluates instantaneous and cumulative telemetry from Feeder and Consumer meters.
    """

    def __init__(
        self,
        baseline_offset_w: float = DEFAULT_BASELINE_OFFSET_W,
        power_threshold_w: float = DEFAULT_POWER_THRESHOLD_W,
        energy_threshold_kwh: float = DEFAULT_ENERGY_THRESHOLD_KWH,
    ):
        self.baseline_offset_w = baseline_offset_w
        self.power_threshold_w = power_threshold_w
        self.energy_threshold_kwh = energy_threshold_kwh

    def evaluate(
        self,
        feeder: MeterSnapshot,
        consumer: MeterSnapshot,
        prev_feeder: Optional[MeterSnapshot] = None,
        prev_consumer: Optional[MeterSnapshot] = None,
    ) -> TheftEvaluationResult:
        """
        Evaluate pair of meter readings to determine grid status and detect theft.
        """
        f_p = float(feeder.power_w)
        c_p = float(consumer.power_w)
        f_e = float(feeder.energy_kwh)
        c_e = float(consumer.energy_kwh)

        # 1. Calculate cumulative interval energy deltas if previous readings exist
        if prev_feeder is not None and prev_consumer is not None:
            delta_feeder_kwh = max(0.0, f_e - float(prev_feeder.energy_kwh))
            delta_consumer_kwh = max(0.0, c_e - float(prev_consumer.energy_kwh))
            energy_diff_kwh = delta_feeder_kwh - delta_consumer_kwh
        else:
            delta_feeder_kwh = 0.0
            delta_consumer_kwh = 0.0
            energy_diff_kwh = 0.0

        # Guard: Idle/Offline grid state
        if f_p < 2.0 and c_p < 2.0:
            return TheftEvaluationResult(
                theft_status="NORMAL",
                calibrated_diff_w=0.0,
                energy_diff_kwh=round(energy_diff_kwh, 4),
                loss_w=0.0,
                loss_kwh=0.0,
                is_theft=False,
                details="Grid idle or zero load detected on both meters.",
            )

        # 2. Case 2: 100% Bypass Theft Check
        # Feeder is supplying active load (> 5.0 W) but Consumer meter reads 0.0 W
        if f_p > 5.0 and c_p <= 0.1:
            calibrated_feeder_w = f_p - self.baseline_offset_w
            calibrated_diff_w = calibrated_feeder_w - c_p
            loss_w = max(0.0, calibrated_diff_w)
            loss_kwh = max(0.0, energy_diff_kwh) if (prev_feeder and prev_consumer) else 0.0
            return TheftEvaluationResult(
                theft_status="THEFT DETECTED (100% BYPASS)",
                calibrated_diff_w=round(calibrated_diff_w, 2),
                energy_diff_kwh=round(energy_diff_kwh, 4),
                loss_w=round(loss_w, 2),
                loss_kwh=round(loss_kwh, 4),
                is_theft=True,
                details=f"Feeder supplying {f_p:.1f}W while Consumer meter is bypassed (0.0W).",
            )

        # 3. Apply baseline hardware calibration offset
        # Calibrated Feeder Power = feeder_power_w - BASELINE_OFFSET_W
        # Because BASELINE_OFFSET_W is -35.7 W, subtracting it adds 35.7 W to match empirical reading.
        calibrated_feeder_w = f_p - self.baseline_offset_w
        calibrated_diff_w = calibrated_feeder_w - c_p

        # 4. Case 3: Partial Tap Theft Check
        # Discrepancy occurs if calibrated difference exceeds 15.0 W
        # OR interval energy loss (delta_feeder_kwh - delta_consumer_kwh) exceeds 0.015 kWh
        is_power_theft = calibrated_diff_w > self.power_threshold_w
        is_energy_theft = energy_diff_kwh > self.energy_threshold_kwh

        if is_power_theft or is_energy_theft:
            loss_w = max(0.0, calibrated_diff_w)
            loss_kwh = max(0.0, energy_diff_kwh)
            reasons = []
            if is_power_theft:
                reasons.append(f"Power diff {calibrated_diff_w:.1f}W > {self.power_threshold_w:.1f}W threshold")
            if is_energy_theft:
                reasons.append(f"Energy loss {energy_diff_kwh:.4f}kWh > {self.energy_threshold_kwh:.4f}kWh threshold")
            return TheftEvaluationResult(
                theft_status="THEFT DETECTED (PARTIAL TAP)",
                calibrated_diff_w=round(calibrated_diff_w, 2),
                energy_diff_kwh=round(energy_diff_kwh, 4),
                loss_w=round(loss_w, 2),
                loss_kwh=round(loss_kwh, 4),
                is_theft=True,
                details="Partial tap detected: " + "; ".join(reasons),
            )

        # 5. Case 1: Normal Operation
        # Calibrated power difference within acceptable threshold
        return TheftEvaluationResult(
            theft_status="NORMAL",
            calibrated_diff_w=round(calibrated_diff_w, 2),
            energy_diff_kwh=round(energy_diff_kwh, 4),
            loss_w=0.0,
            loss_kwh=0.0,
            is_theft=False,
            details=f"Normal grid operation. Calibrated diff: {calibrated_diff_w:.1f}W within bounds.",
        )

