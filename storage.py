"""
storage.py
==========
Hybrid Cloud Persistence & Local SQLite Cache Engine.

Features:
1. Supabase PostgreSQL as Primary Cloud Store (when SUPABASE_URL and SUPABASE_KEY are provided).
2. SQLite (smart_grid.db) as Local High-Reliability Fallback Cache.
3. Automatic sync worker to replicate cached local readings to Supabase once credentials/connection exist.
4. Unified query interface for telemetry history, theft incidents, and billing analysis.
"""

import os
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("SmartGridStorage")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "smart_grid.db")


class SmartGridStorage:
    """
    Manages dual-layer storage with Supabase cloud and SQLite offline fallback.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip()
        self.supabase_key = os.getenv("SUPABASE_KEY", "").strip()
        self.supabase_client = None

        self._init_sqlite()
        self._init_supabase()

    def _init_sqlite(self):
        """Initializes SQLite schema if not already present."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS meter_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    feeder_voltage_v REAL NOT NULL,
                    feeder_current_a REAL NOT NULL,
                    feeder_power_w REAL NOT NULL,
                    feeder_energy_kwh REAL NOT NULL,
                    consumer_voltage_v REAL NOT NULL,
                    consumer_current_a REAL NOT NULL,
                    consumer_power_w REAL NOT NULL,
                    consumer_energy_kwh REAL NOT NULL,
                    calibrated_diff_w REAL NOT NULL,
                    energy_diff_kwh REAL NOT NULL,
                    theft_status TEXT NOT NULL,
                    loss_w REAL DEFAULT 0.0,
                    loss_kwh REAL DEFAULT 0.0,
                    billed_units_kwh REAL DEFAULT 0.0,
                    estimated_bill_inr REAL DEFAULT 0.0,
                    synced_to_supabase INTEGER DEFAULT 0
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sq_created ON meter_readings(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sq_theft ON meter_readings(theft_status)")
            conn.commit()

    def _init_supabase(self):
        """Attempts connection to Supabase if credentials are provided."""
        if self.supabase_url and self.supabase_key and not self.supabase_url.startswith("http://placeholder"):
            try:
                from supabase import create_client
                self.supabase_client = create_client(self.supabase_url, self.supabase_key)
                logger.info("Connected successfully to Supabase PostgreSQL cloud.")
            except Exception as e:
                logger.warning("Supabase connection failed (%s). Using local SQLite fallback.", str(e))
                self.supabase_client = None
        else:
            logger.info("Supabase credentials not configured in .env. Running in local SQLite fallback mode.")

    def record_reading(self, data: Dict[str, Any]) -> int:
        """
        Saves a reading to the local SQLite database and attempts cloud sync.
        Returns the inserted local record ID.
        """
        created_at = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        row = (
            created_at,
            float(data["feeder_voltage_v"]),
            float(data["feeder_current_a"]),
            float(data["feeder_power_w"]),
            float(data["feeder_energy_kwh"]),
            float(data["consumer_voltage_v"]),
            float(data["consumer_current_a"]),
            float(data["consumer_power_w"]),
            float(data["consumer_energy_kwh"]),
            float(data["calibrated_diff_w"]),
            float(data["energy_diff_kwh"]),
            str(data["theft_status"]),
            float(data.get("loss_w", 0.0)),
            float(data.get("loss_kwh", 0.0)),
            float(data.get("billed_units_kwh", 0.0)),
            float(data.get("estimated_bill_inr", 0.0)),
            0,  # synced_to_supabase = 0
        )

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO meter_readings (
                    created_at, feeder_voltage_v, feeder_current_a, feeder_power_w, feeder_energy_kwh,
                    consumer_voltage_v, consumer_current_a, consumer_power_w, consumer_energy_kwh,
                    calibrated_diff_w, energy_diff_kwh, theft_status, loss_w, loss_kwh,
                    billed_units_kwh, estimated_bill_inr, synced_to_supabase
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            conn.commit()
            local_id = cursor.lastrowid

        # Attempt immediate cloud sync if client active
        if self.supabase_client:
            self._sync_row_to_supabase(local_id, data, created_at)

        return local_id

    def _sync_row_to_supabase(self, local_id: int, data: Dict[str, Any], created_at: str) -> bool:
        """Pushes a single reading to Supabase."""
        try:
            cloud_payload = {
                "created_at": created_at,
                "feeder_voltage_v": float(data["feeder_voltage_v"]),
                "feeder_current_a": float(data["feeder_current_a"]),
                "feeder_power_w": float(data["feeder_power_w"]),
                "feeder_energy_kwh": float(data["feeder_energy_kwh"]),
                "consumer_voltage_v": float(data["consumer_voltage_v"]),
                "consumer_current_a": float(data["consumer_current_a"]),
                "consumer_power_w": float(data["consumer_power_w"]),
                "consumer_energy_kwh": float(data["consumer_energy_kwh"]),
                "calibrated_diff_w": float(data["calibrated_diff_w"]),
                "energy_diff_kwh": float(data["energy_diff_kwh"]),
                "theft_status": str(data["theft_status"]),
                "loss_w": float(data.get("loss_w", 0.0)),
                "loss_kwh": float(data.get("loss_kwh", 0.0)),
                "billed_units_kwh": float(data.get("billed_units_kwh", 0.0)),
                "estimated_bill_inr": float(data.get("estimated_bill_inr", 0.0)),
            }
            self.supabase_client.table("meter_readings").insert(cloud_payload).execute()

            with sqlite3.connect(self.db_path) as conn:
                conn.cursor().execute(
                    "UPDATE meter_readings SET synced_to_supabase = 1 WHERE id = ?",
                    (local_id,),
                )
                conn.commit()
            return True
        except Exception as e:
            logger.warning("Cloud push failed for reading #%s: %s", local_id, str(e))
            return False

    def sync_pending_to_supabase(self, batch_size: int = 50) -> int:
        """
        Synchronizes all un-synced local records to Supabase.
        Returns the count of successfully synced rows.
        """
        if not self.supabase_client:
            self._init_supabase()
            if not self.supabase_client:
                return 0

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM meter_readings
                WHERE synced_to_supabase = 0
                ORDER BY id ASC LIMIT ?
                """,
                (batch_size,),
            )
            unsynced_rows = cursor.fetchall()

        if not unsynced_rows:
            return 0

        synced_count = 0
        for row in unsynced_rows:
            row_dict = dict(row)
            local_id = row_dict["id"]
            if self._sync_row_to_supabase(local_id, row_dict, row_dict["created_at"]):
                synced_count += 1

        logger.info("Successfully synced %s pending records to Supabase.", synced_count)
        return synced_count

    def get_readings(
        self,
        limit: int = 100,
        theft_only: bool = False,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fetches readings. Tries Supabase first; falls back seamlessly to SQLite.
        """
        # If Supabase is available, query Supabase
        if self.supabase_client:
            try:
                query = self.supabase_client.table("meter_readings").select("*").order("created_at", desc=True)
                if theft_only:
                    query = query.neq("theft_status", "NORMAL")
                response = query.range(offset, offset + limit - 1).execute()
                if response.data is not None:
                    return response.data
            except Exception as e:
                logger.warning("Supabase fetch failed (%s). Falling back to local SQLite.", str(e))

        # SQLite query fallback
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM meter_readings "
            params = []
            if theft_only:
                query += "WHERE theft_status != 'NORMAL' "
            query += "ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def get_latest_reading(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent single reading."""
        readings = self.get_readings(limit=1)
        return readings[0] if readings else None

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Calculates aggregate statistics: total readings, theft events, unaccounted energy, etc.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_records,
                    SUM(CASE WHEN theft_status != 'NORMAL' THEN 1 ELSE 0 END) as theft_count,
                    SUM(loss_w) as total_loss_w,
                    SUM(loss_kwh) as total_loss_kwh,
                    MAX(consumer_energy_kwh) as latest_consumer_kwh,
                    MIN(consumer_energy_kwh) as initial_consumer_kwh
                FROM meter_readings
                """
            )
            row = dict(cursor.fetchone())

        return {
            "total_records": row["total_records"] or 0,
            "theft_count": row["theft_count"] or 0,
            "total_loss_w": round(row["total_loss_w"] or 0.0, 2),
            "total_loss_kwh": round(row["total_loss_kwh"] or 0.0, 4),
            "latest_consumer_kwh": round(row["latest_consumer_kwh"] or 0.0, 2),
            "initial_consumer_kwh": round(row["initial_consumer_kwh"] or 0.0, 2),
        }

