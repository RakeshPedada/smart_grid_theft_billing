"""
billing.py
==========
Automated Consumer Electricity Billing Engine & Invoice Generator.

Tariff Structure (INR ₹):
- Slab 1 (0 to 50 kWh):    ₹4.50 / unit
- Slab 2 (51 to 150 kWh):  ₹6.00 / unit
- Slab 3 (> 150 kWh):      ₹7.50 / unit
- Fixed Meter Charge:      ₹50.00
- Electricity Duty:        5.0% on Energy Charges

Capabilities:
- Dynamic calculation of tiered consumption and itemized slab breakdown.
- Support for previous vs current reading cycle delta.
- Generation of responsive, printable HTML utility bill invoices.
- Standalone PDF invoice generation via ReportLab.
- Tabular CSV audit log export.
"""

import os
import csv
from datetime import datetime
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# Tariff configuration with environment fallbacks
SLAB_1_LIMIT = float(os.getenv("SLAB_1_LIMIT", "50.0"))
SLAB_1_RATE = float(os.getenv("SLAB_1_RATE", "4.50"))
SLAB_2_LIMIT = float(os.getenv("SLAB_2_LIMIT", "150.0"))
SLAB_2_RATE = float(os.getenv("SLAB_2_RATE", "6.00"))
SLAB_3_RATE = float(os.getenv("SLAB_3_RATE", "7.50"))

DEFAULT_FIXED_CHARGE = float(os.getenv("FIXED_METER_CHARGE", "50.00"))
DEFAULT_DUTY_PCT = float(os.getenv("ELECTRICITY_DUTY_PCT", "5.0"))


class BillingEngine:
    """
    Computes tiered domestic electricity bills and produces itemized invoices.
    """

    def __init__(
        self,
        slab1_limit: float = SLAB_1_LIMIT,
        slab1_rate: float = SLAB_1_RATE,
        slab2_limit: float = SLAB_2_LIMIT,
        slab2_rate: float = SLAB_2_RATE,
        slab3_rate: float = SLAB_3_RATE,
        fixed_charge: float = DEFAULT_FIXED_CHARGE,
        duty_pct: float = DEFAULT_DUTY_PCT,
    ):
        self.slab1_limit = slab1_limit
        self.slab1_rate = slab1_rate
        self.slab2_limit = slab2_limit
        self.slab2_rate = slab2_rate
        self.slab3_rate = slab3_rate
        self.fixed_charge = fixed_charge
        self.duty_pct = duty_pct

    def calculate_bill(
        self,
        current_kwh: float,
        previous_kwh: float = 0.0,
        fixed_charge: Optional[float] = None,
        duty_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculates itemized domestic electricity bill for given consumption interval.
        """
        fixed = self.fixed_charge if fixed_charge is None else fixed_charge
        duty_rate = self.duty_pct if duty_pct is None else duty_pct

        units = max(0.0, float(current_kwh) - float(previous_kwh))
        remaining = units

        # Slab 1: 0 - 50 kWh
        slab1_units = min(remaining, self.slab1_limit)
        slab1_amount = slab1_units * self.slab1_rate
        remaining = max(0.0, remaining - slab1_units)

        # Slab 2: 51 - 150 kWh
        slab2_capacity = self.slab2_limit - self.slab1_limit
        slab2_units = min(remaining, slab2_capacity)
        slab2_amount = slab2_units * self.slab2_rate
        remaining = max(0.0, remaining - slab2_units)

        # Slab 3: > 150 kWh
        slab3_units = remaining
        slab3_amount = slab3_units * self.slab3_rate

        energy_charges = slab1_amount + slab2_amount + slab3_amount
        electricity_duty = (energy_charges * duty_rate) / 100.0
        total_amount = energy_charges + fixed + electricity_duty

        return {
            "previous_kwh": round(float(previous_kwh), 2),
            "current_kwh": round(float(current_kwh), 2),
            "units_consumed": round(units, 2),
            "slabs": [
                {
                    "name": f"Slab 1 (0 – {int(self.slab1_limit)} kWh)",
                    "units": round(slab1_units, 2),
                    "rate": self.slab1_rate,
                    "amount": round(slab1_amount, 2),
                },
                {
                    "name": f"Slab 2 ({int(self.slab1_limit)+1} – {int(self.slab2_limit)} kWh)",
                    "units": round(slab2_units, 2),
                    "rate": self.slab2_rate,
                    "amount": round(slab2_amount, 2),
                },
                {
                    "name": f"Slab 3 (> {int(self.slab2_limit)} kWh)",
                    "units": round(slab3_units, 2),
                    "rate": self.slab3_rate,
                    "amount": round(slab3_amount, 2),
                },
            ],
            "energy_charges": round(energy_charges, 2),
            "fixed_charge": round(fixed, 2),
            "duty_pct": duty_rate,
            "electricity_duty": round(electricity_duty, 2),
            "total_amount_inr": round(total_amount, 2),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def generate_html_invoice(
        self,
        bill_data: Dict[str, Any],
        consumer_info: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generates an executive utility bill HTML invoice with print stylesheet.
        """
        info = {
            "consumer_name": "SMART-CONSUMER-01",
            "consumer_id": "CNS-2026-9812",
            "meter_id": "TOMZN-DDS238-WIFI",
            "feeder_id": "TECHNO-LORAWAN-F1",
            "billing_cycle": datetime.now().strftime("%B %Y"),
            "due_date": datetime.now().strftime("%Y-%m-%d"),
            "connection_type": "LT-Domestic Single Phase",
            "address": "Smart Grid Testbed, Lab 4, Block C",
        }
        if consumer_info:
            info.update(consumer_info)

        slabs_rows = "".join(
            f"""
            <tr>
                <td style="padding: 10px 12px; border-bottom: 1px solid #2d3748; color: #e2e8f0;">{s['name']}</td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #2d3748; text-align: center; color: #cbd5e1;">{s['units']:.2f}</td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #2d3748; text-align: right; color: #cbd5e1;">₹{s['rate']:.2f}</td>
                <td style="padding: 10px 12px; border-bottom: 1px solid #2d3748; text-align: right; font-weight: 600; color: #10b981;">₹{s['amount']:.2f}</td>
            </tr>
            """
            for s in bill_data["slabs"]
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Electricity Bill Invoice - {info['consumer_id']}</title>
<style>
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        background-color: #0b1120;
        color: #f8fafc;
        margin: 0;
        padding: 24px;
    }}
    .invoice-card {{
        max-width: 800px;
        margin: 0 auto;
        background: #111827;
        border: 1px solid #1f2937;
        border-radius: 12px;
        box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5);
        padding: 32px;
    }}
    .header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        border-bottom: 2px solid #374151;
        padding-bottom: 20px;
        margin-bottom: 24px;
    }}
    .utility-title {{
        font-size: 24px;
        font-weight: 800;
        color: #06b6d4;
        letter-spacing: -0.5px;
        margin: 0 0 6px 0;
    }}
    .utility-sub {{
        color: #94a3b8;
        font-size: 13px;
        margin: 0;
    }}
    .invoice-badge {{
        background: #1e293b;
        border: 1px solid #06b6d4;
        color: #06b6d4;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .grid-info {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        background: #0f172a;
        padding: 18px 20px;
        border-radius: 8px;
        border: 1px solid #1e293b;
        margin-bottom: 24px;
    }}
    .info-label {{
        color: #64748b;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 2px;
    }}
    .info-value {{
        color: #f1f5f9;
        font-size: 14px;
        font-weight: 600;
    }}
    .readings-bar {{
        display: flex;
        justify-content: space-between;
        background: #1e293b;
        border-radius: 8px;
        padding: 16px 24px;
        margin-bottom: 24px;
        border-left: 4px solid #10b981;
    }}
    .reading-stat {{
        text-align: center;
    }}
    .reading-num {{
        font-size: 20px;
        font-weight: 700;
        color: #f8fafc;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 24px;
    }}
    th {{
        background: #1e293b;
        color: #94a3b8;
        text-transform: uppercase;
        font-size: 11px;
        letter-spacing: 0.5px;
        padding: 10px 12px;
        text-align: left;
    }}
    .summary-box {{
        margin-left: auto;
        width: 320px;
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 16px 20px;
    }}
    .summary-row {{
        display: flex;
        justify-content: space-between;
        padding: 6px 0;
        font-size: 13px;
        color: #cbd5e1;
    }}
    .total-row {{
        display: flex;
        justify-content: space-between;
        padding: 12px 0 6px 0;
        margin-top: 8px;
        border-top: 2px solid #374151;
        font-size: 18px;
        font-weight: 800;
        color: #06b6d4;
    }}
    .footer {{
        margin-top: 32px;
        border-top: 1px solid #1f2937;
        padding-top: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        color: #64748b;
        font-size: 12px;
    }}
    .print-btn {{
        background: #06b6d4;
        color: #0b1120;
        border: none;
        padding: 8px 18px;
        border-radius: 6px;
        font-weight: 700;
        cursor: pointer;
        font-size: 13px;
    }}
    @media print {{
        body {{
            background: white !important;
            color: black !important;
            padding: 0 !important;
        }}
        .invoice-card {{
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
            background: white !important;
        }}
        .print-btn {{
            display: none !important;
        }}
        .utility-title {{
            color: #0284c7 !important;
        }}
        .grid-info, .readings-bar, .summary-box, th {{
            background: #f1f5f9 !important;
            border-color: #cbd5e1 !important;
            color: #0f172a !important;
        }}
        .info-value, .reading-num, td, .summary-row, .total-row {{
            color: #0f172a !important;
        }}
    }}
</style>
</head>
<body>
<div class="invoice-card">
    <div class="header">
        <div>
            <div class="utility-title">SMART GRID UTILITY CORPORATION</div>
            <p class="utility-sub">Advanced Automated Metering & Power Theft Detection Infrastructure</p>
        </div>
        <div style="text-align: right;">
            <div class="invoice-badge">Official Invoice</div>
            <p style="color: #64748b; font-size: 12px; margin-top: 6px;">Bill Date: {bill_data['generated_at']}</p>
        </div>
    </div>

    <div class="grid-info">
        <div>
            <div class="info-label">Consumer Details</div>
            <div class="info-value">{info['consumer_name']} ({info['consumer_id']})</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">{info['address']}</div>
        </div>
        <div>
            <div class="info-label">Metering & Feeder Point</div>
            <div class="info-value">Meter: {info['meter_id']}</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Feeder: {info['feeder_id']} | Type: {info['connection_type']}</div>
        </div>
    </div>

    <div class="readings-bar">
        <div class="reading-stat">
            <div class="info-label">Previous Reading</div>
            <div class="reading-num">{bill_data['previous_kwh']:.2f} <span style="font-size: 13px; color: #94a3b8;">kWh</span></div>
        </div>
        <div class="reading-stat">
            <div class="info-label">Current Reading</div>
            <div class="reading-num">{bill_data['current_kwh']:.2f} <span style="font-size: 13px; color: #94a3b8;">kWh</span></div>
        </div>
        <div class="reading-stat">
            <div class="info-label">Net Units Billed</div>
            <div class="reading-num" style="color: #10b981;">{bill_data['units_consumed']:.2f} <span style="font-size: 13px; color: #94a3b8;">Units</span></div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Consumption Slab</th>
                <th style="text-align: center;">Billed Units (kWh)</th>
                <th style="text-align: right;">Tariff Rate (₹)</th>
                <th style="text-align: right;">Energy Charges (₹)</th>
            </tr>
        </thead>
        <tbody>
            {slabs_rows}
        </tbody>
    </table>

    <div class="summary-box">
        <div class="summary-row">
            <span>Total Energy Charges:</span>
            <span>₹{bill_data['energy_charges']:.2f}</span>
        </div>
        <div class="summary-row">
            <span>Fixed Meter Charge:</span>
            <span>₹{bill_data['fixed_charge']:.2f}</span>
        </div>
        <div class="summary-row">
            <span>Electricity Duty ({bill_data['duty_pct']}%):</span>
            <span>₹{bill_data['electricity_duty']:.2f}</span>
        </div>
        <div class="total-row">
            <span>Total Payable:</span>
            <span>₹{bill_data['total_amount_inr']:.2f}</span>
        </div>
    </div>

    <div class="footer">
        <div>
            <span>Verified by Smart Grid Anti-Theft Telemetry Engine</span>
        </div>
        <div>
            <button class="print-btn" onclick="window.print()">Print / Save PDF</button>
        </div>
    </div>
</div>
</body>
</html>
"""
        return html

    def generate_pdf_invoice(
        self,
        bill_data: Dict[str, Any],
        output_path: str,
        consumer_info: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generates a standalone PDF utility bill invoice using ReportLab.
        """
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        info = {
            "consumer_name": "SMART-CONSUMER-01",
            "consumer_id": "CNS-2026-9812",
            "meter_id": "TOMZN-DDS238-WIFI",
            "feeder_id": "TECHNO-LORAWAN-F1",
            "connection_type": "LT-Domestic Single Phase",
            "address": "Smart Grid Testbed, Lab 4, Block C",
        }
        if consumer_info:
            info.update(consumer_info)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#06B6D4"),
        )
        sub_style = ParagraphStyle(
            "SubStyle",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748B"),
        )
        bold_style = ParagraphStyle(
            "BoldStyle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#0F172A"),
            fontName="Helvetica-Bold",
        )

        elements.append(Paragraph("SMART GRID UTILITY CORPORATION", title_style))
        elements.append(Paragraph("Automated Metering & Dual-Check Power Theft Detection Infrastructure", sub_style))
        elements.append(Spacer(1, 14))

        # Consumer & Meter Metadata Table
        meta_data = [
            [
                Paragraph("<b>Consumer Name:</b> " + info["consumer_name"], styles["Normal"]),
                Paragraph("<b>Consumer ID:</b> " + info["consumer_id"], styles["Normal"]),
            ],
            [
                Paragraph("<b>Meter ID:</b> " + info["meter_id"], styles["Normal"]),
                Paragraph("<b>Feeder Point:</b> " + info["feeder_id"], styles["Normal"]),
            ],
            [
                Paragraph("<b>Connection Type:</b> " + info["connection_type"], styles["Normal"]),
                Paragraph("<b>Bill Date:</b> " + bill_data["generated_at"], styles["Normal"]),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[270, 270])
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 14))

        # Consumption Reading Summary
        reading_data = [
            ["Previous Reading", "Current Reading", "Net Billed Units"],
            [
                f"{bill_data['previous_kwh']:.2f} kWh",
                f"{bill_data['current_kwh']:.2f} kWh",
                f"{bill_data['units_consumed']:.2f} Units",
            ],
        ]
        reading_table = Table(reading_data, colWidths=[180, 180, 180])
        reading_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (2, 1), (2, 1), colors.HexColor("#059669")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
                ]
            )
        )
        elements.append(reading_table)
        elements.append(Spacer(1, 16))

        # Slab Breakdown Table
        slab_rows = [["Consumption Slab", "Billed Units", "Tariff Rate (Rs)", "Energy Charges (Rs)"]]
        for s in bill_data["slabs"]:
            slab_rows.append([s["name"], f"{s['units']:.2f}", f"Rs {s['rate']:.2f}", f"Rs {s['amount']:.2f}"])

        slab_table = Table(slab_rows, colWidths=[220, 100, 110, 110])
        slab_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ]
            )
        )
        elements.append(slab_table)
        elements.append(Spacer(1, 14))

        # Bill Summary Calculation Table
        summary_rows = [
            ["Total Energy Charges:", f"Rs {bill_data['energy_charges']:.2f}"],
            ["Fixed Meter Charge:", f"Rs {bill_data['fixed_charge']:.2f}"],
            [f"Electricity Duty ({bill_data['duty_pct']}%):", f"Rs {bill_data['electricity_duty']:.2f}"],
            ["TOTAL AMOUNT PAYABLE:", f"Rs {bill_data['total_amount_inr']:.2f}"],
        ]
        summary_table = Table(summary_rows, colWidths=[380, 160])
        summary_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, -1), (-1, -1), 11),
                    ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#0891B2")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#0F172A")),
                ]
            )
        )
        elements.append(summary_table)

        doc.build(elements)
        return output_path

    @staticmethod
    def export_audit_csv(readings: List[Dict[str, Any]], output_path: str) -> str:
        """
        Exports list of reading dictionaries to CSV.
        """
        if not readings:
            # write empty template
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "created_at", "theft_status", "loss_w", "loss_kwh", "estimated_bill_inr"])
            return output_path

        fieldnames = list(readings[0].keys())
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in readings:
                writer.writerow(r)
        return output_path

