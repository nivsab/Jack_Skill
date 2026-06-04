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
    "backup_light_bulb": {
        "display":  "נורת רוורס (Back-up)",
        "query_en": "backup reverse light bulb type specification",
        "unit":     "",
    },
    "turn_signal_rear_bulb": {
        "display":  "נורת פלאש אחורי",
        "query_en": "rear turn signal bulb type specification",
        "unit":     "",
    },
    "parking_light_bulb": {
        "display":  "נורת עמידה קדמית",
        "query_en": "front parking position light bulb type specification",
        "unit":     "",
    },
    "license_plate_bulb": {
        "display":  "נורת לוחית רישוי",
        "query_en": "license plate light bulb type specification",
        "unit":     "",
    },
    "rear_fog_light_bulb": {
        "display":  "נורת ערפל אחורי",
        "query_en": "rear fog light bulb type specification",
        "unit":     "",
    },
    "interior_dome_bulb": {
        "display":  "נורת תאורה פנימית (גג)",
        "query_en": "interior dome map reading light bulb type specification",
        "unit":     "",
    },
    "wiper_front_driver_mm": {
        "display":  "מגב קדמי — צד נהג",
        "query_en": "front driver wiper blade size mm specification",
        "unit":     "mm",
    },
    "wiper_front_passenger_mm": {
        "display":  "מגב קדמי — צד נוסע",
        "query_en": "front passenger wiper blade size mm specification",
        "unit":     "mm",
    },
    "wiper_rear_mm": {
        "display":  "מגב אחורי",
        "query_en": "rear wiper blade size mm specification",
        "unit":     "mm",
    },
    "engine_air_filter": {
        "display":  "מסנן אוויר מנוע",
        "query_en": "engine air filter part number OEM size specification",
        "unit":     "",
    },
    "cabin_air_filter": {
        "display":  "מסנן אוויר קבינה (מזגן)",
        "query_en": "cabin pollen air filter part number OEM size specification",
        "unit":     "",
    },
    "tire_size_front": {
        "display":  "מידת צמיג קדמי",
        "query_en": "front tire size specification OEM",
        "unit":     "",
    },
    "tire_pressure_front": {
        "display":  "לחץ צמיג קדמי",
        "query_en": "front tire inflation pressure bar kPa PSI specification",
        "unit":     "bar",
    },
    "tire_pressure_rear": {
        "display":  "לחץ צמיג אחורי",
        "query_en": "rear tire inflation pressure bar kPa PSI specification",
        "unit":     "bar",
    },
    "coolant_capacity_liters": {
        "display":  "כמות נוזל קירור",
        "query_en": "coolant system capacity liters specification",
        "unit":     "L",
    },
    "battery_group_size": {
        "display":  "קוד מצבר (DIN/BCI)",
        "query_en": "battery group size DIN BCI OEM specification",
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
