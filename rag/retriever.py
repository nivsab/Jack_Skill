"""
אורקסטרטור שליפת ספציפיקציות — Supabase cache → Claude parametric fallback.

על Cache Miss: מחזיר None — Claude משתמש בידע פנימי + מציג דיסקליימר.
DDG שמור למחירים וסרטונים בלבד (parts.py, youtube.py).

CLI: python rag/retriever.py <make> <model> <year> <message>
פלט: JSON ל-stdout
"""
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
warnings.filterwarnings("ignore")

from typing import Optional
from dotenv import load_dotenv
load_dotenv()

from state import VehicleInfo
from rag import cache
from rag.fetcher import SPEC_META


# ─── מיפוי מילות מפתח → spec_types ──────────────────────────────────────────

_KEYWORD_SPEC_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    # ── שמן ──────────────────────────────────────────────────────────────────
    (
        ("שמן", "oil", "מסנן שמן", "oil filter", "החלפת שמן", "פקק"),
        ["oil_drain_plug_torque", "engine_oil_type", "engine_oil_capacity", "oil_change_interval"],
    ),
    # ── גלגלים / צמיגים ──────────────────────────────────────────────────────
    (
        ("גלגל", "צמיג", "wheel", "tire", "גלגלים", "בורגי גלגל",
         "מידת צמיג", "tire size", "לחץ", "tire pressure", "פנצ'ר"),
        ["wheel_torque", "tire_size_front", "tire_pressure_front", "tire_pressure_rear"],
    ),
    # ── נרות הצתה ────────────────────────────────────────────────────────────
    (
        ("נר", "spark", "נרות", "הצתה"),
        ["spark_plug_torque", "spark_plug_type", "spark_plug_gap"],
    ),
    # ── בלמים ────────────────────────────────────────────────────────────────
    (
        ("בלמים", "brake", "דיסק", "רפידות", "כרית", "בלם"),
        ["brake_caliper_torque", "brake_fluid_type"],
    ),
    # ── קירור ────────────────────────────────────────────────────────────────
    (
        ("קירור", "coolant", "רדיאטור", "אנטיפריז"),
        ["coolant_type", "coolant_capacity_liters"],
    ),
    # ── מצבר ─────────────────────────────────────────────────────────────────
    (
        ("מצבר", "battery", "סוללה", "cca", "להתנעה", "din", "bci"),
        ["battery_capacity_ah", "battery_cca", "battery_group_size"],
    ),
    # ── נורות — כל סוגי התאורה ───────────────────────────────────────────────
    (
        ("נורה", "נורות", "פנס", "bulb", "headlight", "ערפל", "פלאש", "תאורה", "light"),
        [
            "headlight_low_beam_bulb", "headlight_high_beam_bulb",
            "fog_light_front_bulb", "rear_fog_light_bulb",
            "turn_signal_front_bulb", "turn_signal_rear_bulb",
            "brake_light_bulb", "backup_light_bulb",
            "parking_light_bulb", "license_plate_bulb",
            "interior_dome_bulb",
        ],
    ),
    # ── נורות — מיפוי ספציפי לסוג ───────────────────────────────────────────
    (
        ("רוורס", "backup", "גיבוי", "reverse light", "back-up", "backup light"),
        ["backup_light_bulb"],
    ),
    (
        ("פלאש אחורי", "rear turn signal", "rear blinker", "indicator rear"),
        ["turn_signal_rear_bulb"],
    ),
    (
        ("לוחית רישוי", "license plate", "number plate"),
        ["license_plate_bulb"],
    ),
    (
        ("ערפל אחורי", "rear fog"),
        ["rear_fog_light_bulb"],
    ),
    (
        ("עמידה", "position light", "parking light", "נורת חניה"),
        ["parking_light_bulb"],
    ),
    (
        ("תאורה פנימית", "dome light", "dome bulb", "map light", "reading light", "גג", "פנים"),
        ["interior_dome_bulb"],
    ),
    # ── מגבים ────────────────────────────────────────────────────────────────
    (
        ("מגב", "מגבים", "wiper", "windshield wiper", "מגב קדמי", "מגב אחורי"),
        ["wiper_front_driver_mm", "wiper_front_passenger_mm", "wiper_rear_mm"],
    ),
    # ── מסנן אוויר מנוע ──────────────────────────────────────────────────────
    (
        ("מסנן אוויר", "air filter", "פילטר אוויר", "מסנן מנוע"),
        ["engine_air_filter"],
    ),
    # ── מסנן קבינה / מזגן ────────────────────────────────────────────────────
    (
        ("מסנן קבינה", "מסנן מזגן", "cabin filter", "pollen filter",
         "cabin air filter", "מסנן אוויר פנים", "מזגן מסנן"),
        ["cabin_air_filter"],
    ),
]

_CONFIDENCE_EMOJI = {
    "verified": "✅",
    "scraped":  "🌐",
    "llm":      "🤖",
}


def _detect_relevant_specs(text: str) -> list[str]:
    text_lower = text.lower()
    found: list[str] = []
    for keywords, specs in _KEYWORD_SPEC_MAP:
        if any(kw in text_lower for kw in keywords):
            for s in specs:
                if s not in found:
                    found.append(s)
    return found


def get_spec(vehicle: VehicleInfo, spec_type: str) -> Optional[dict]:
    """
    שולף ספציפיקציה מ-Supabase cache בלבד.
    Cache Miss → None → Claude parametric knowledge + disclaimer.
    DDG לא נקרא כאן — שמור למחירים וסרטונים.
    """
    cached = cache.get_spec(vehicle, spec_type)
    if cached:
        return {**cached, "source": "cache"}
    return None


def get_specs_context(vehicle: Optional[VehicleInfo], last_message: str) -> str:
    """מחזיר בלוק טקסט מוכן להזרקה לפרומפט — לשימוש תוכניתי בלבד."""
    if not vehicle:
        return ""
    spec_types = _detect_relevant_specs(last_message)
    if not spec_types:
        return ""

    make  = vehicle.get("manufacturer", "")
    model = vehicle.get("model", "")
    year  = vehicle.get("year", "")

    lines = [f"=== ספציפיקציות ל-{make} {model} {year} ==="]
    found_any = False

    for spec_type in spec_types:
        result = get_spec(vehicle, spec_type)
        if not result:
            continue
        found_any = True
        meta  = SPEC_META.get(spec_type, {})
        name  = meta.get("display", spec_type)
        if result.get("source") == "cache":
            confidence = result.get("confidence", "llm")
            emoji = _CONFIDENCE_EMOJI.get(confidence, "🤖")
            value = result.get("value", "")
            unit  = result.get("unit", "")
            lines.append(f"{emoji} {name}: {value} {unit}".strip())
            if confidence == "llm":
                lines.append("   ⚠️ מקור: הערכת מודל — לא מאומת מול ספר היצרן")
        else:
            snippets = result.get("snippets", [])
            lines.append(f"🌐 {name} — תוצאות חיפוש (לא מאומת):")
            for s in snippets[:2]:
                lines.append(f"   • {s[:120]}")

    if not found_any:
        return ""

    lines.append(
        "\n⚠️ דיסקליימר מקור נתונים: ערכים המסומנים ב-🤖 או 🌐 אינם מאומתים מול ספר היצרן המקורי. "
        "השתמש בהם כנקודת מוצא ובדוק מול מדריך הרכב שלך לפני ביצוע."
    )
    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli_main():
    """
    CLI: python rag/retriever.py <make> <model> <year> <message>
    מחזיר JSON ל-stdout — תמיד, גם בכשל.
    """
    try:
        if len(sys.argv) < 5:
            print(json.dumps({"found": False, "error": "usage: retriever.py <make> <model> <year> <message>"}))
            return

        make, model, year_str, message = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        try:
            year = int(year_str)
        except ValueError:
            year = 0

        vehicle: VehicleInfo = {"manufacturer": make, "model": model, "year": year}
        spec_types = _detect_relevant_specs(message)

        if not spec_types:
            print(json.dumps({"found": False, "reason": "no relevant keywords"}))
            return

        results = {}
        missing = []
        for spec_type in spec_types:
            result = get_spec(vehicle, spec_type)
            if result:
                results[spec_type] = result
            else:
                missing.append(spec_type)

        if results:
            payload = {"found": True, "specs": results}
            if missing:
                # חלק מהספציפיקציות לא נמצאו — חובה להציג אזהרה על אלו
                payload["partial_miss"] = missing
                payload["parametric_warning"] = True
            print(json.dumps(payload, ensure_ascii=False))
        else:
            # שום ספציפיקציה לא נמצאה ב-cache — כל התשובה תהיה Parametric
            print(json.dumps({
                "found": False,
                "parametric_warning": True,
                "reason": "no data in verified cache",
                "missing_specs": spec_types,
            }, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({"found": False, "error": str(exc)}))


if __name__ == "__main__":
    _cli_main()
