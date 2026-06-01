"""
שליפת ספציפיקציות מהרשת — DuckDuckGo בלבד.

מחזיר קטעי טקסט גולמיים (snippets) — Claude מחלץ את הערך.
"""
import json
from typing import Optional

from duckduckgo_search import DDGS

from state import VehicleInfo


# ─── מטא-דאטה לכל סוג ספציפיקציה ──────────────────────────────────────────────

SPEC_META: dict[str, dict] = {
    "oil_drain_plug_torque": {
        "display":  "מומנט פקק שמן מנוע",
        "query_en": "oil drain plug torque Nm specifications",
        "unit":     "Nm",
    },
    "wheel_torque": {
        "display":  "מומנט בורגי גלגל",
        "query_en": "wheel lug nut torque spec Nm",
        "unit":     "Nm",
    },
    "spark_plug_torque": {
        "display":  "מומנט נר הצתה",
        "query_en": "spark plug torque spec Nm",
        "unit":     "Nm",
    },
    "brake_caliper_torque": {
        "display":  "מומנט בורג צבת בלמים",
        "query_en": "brake caliper bolt torque Nm",
        "unit":     "Nm",
    },
    "engine_oil_type": {
        "display":  "סוג שמן מנוע",
        "query_en": "engine oil type viscosity grade recommended",
        "unit":     "",
    },
    "engine_oil_capacity": {
        "display":  "כמות שמן מנוע",
        "query_en": "engine oil capacity liters with filter",
        "unit":     "L",
    },
    "coolant_type": {
        "display":  "סוג נוזל קירור",
        "query_en": "coolant type antifreeze color recommended",
        "unit":     "",
    },
    "brake_fluid_type": {
        "display":  "סוג נוזל בלמים",
        "query_en": "brake fluid type DOT recommended",
        "unit":     "",
    },
    "oil_change_interval": {
        "display":  "מרווח החלפת שמן",
        "query_en": "oil change interval km miles recommended",
        "unit":     "km",
    },
    "spark_plug_type": {
        "display":  "סוג נר הצתה",
        "query_en": "spark plug type part number OEM",
        "unit":     "",
    },
    "spark_plug_gap": {
        "display":  "פיר נר הצתה",
        "query_en": "spark plug gap mm specification",
        "unit":     "mm",
    },
    "battery_capacity_ah": {
        "display":  "קיבולת מצבר",
        "query_en": "battery capacity Ah OEM specification",
        "unit":     "Ah",
    },
    "battery_cca": {
        "display":  "עוצמת התנעה (CCA)",
        "query_en": "battery cold cranking amps CCA specification",
        "unit":     "CCA",
    },
    "headlight_low_beam_bulb": {
        "display":  "נורת פנס קרוב",
        "query_en": "headlight low beam bulb type H7 H4 specification",
        "unit":     "",
    },
    "headlight_high_beam_bulb": {
        "display":  "נורת פנס רחוק",
        "query_en": "headlight high beam bulb type specification",
        "unit":     "",
    },
    "fog_light_front_bulb": {
        "display":  "נורת ערפל קדמי",
        "query_en": "front fog light bulb type specification",
        "unit":     "",
    },
    "turn_signal_front_bulb": {
        "display":  "נורת פלאש קדמי",
        "query_en": "front turn signal bulb type specification",
        "unit":     "",
    },
    "brake_light_bulb": {
        "display":  "נורת בלם",
        "query_en": "brake light bulb type specification",
        "unit":     "",
    },
}


def fetch_from_web(vehicle: VehicleInfo, spec_type: str) -> Optional[dict]:
    """
    מחפש ספציפיקציה ב-DuckDuckGo ומחזיר snippets גולמיים.

    מחזיר dict עם: snippets (list), display, unit — או None אם החיפוש נכשל.
    Claude יחלץ את הערך מה-snippets.
    """
    meta = SPEC_META.get(spec_type)
    if not meta:
        return None

    make  = vehicle.get("manufacturer", "")
    model = vehicle.get("model", "")
    year  = vehicle.get("year", "")
    query = f"{make} {model} {year} {meta['query_en']}"

    try:
        with DDGS(timeout=5) as ddgs:
            results = list(ddgs.text(query, max_results=4))
        if not results:
            return None
        snippets = [r.get("body", "") for r in results if r.get("body")]
        return {
            "snippets": snippets,
            "display":  meta["display"],
            "unit":     meta["unit"],
            "source":   "web",
        }
    except Exception:
        return None
