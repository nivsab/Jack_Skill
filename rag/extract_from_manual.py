"""
rag/extract_from_manual.py — חילוץ ספציפיקציות מספר יצרן PDF ושמירה ל-vehicle_specs.

תהליך:
  1. חיפוש chunks רלוונטיים ב-doc_chunks לפי מילות מפתח (keyword ILIKE)
  2. שליחה ל-Groq לחילוץ ערך מובנה מתוך טקסט המדריך
  3. שמירה ל-vehicle_specs עם confidence="manual"

CLI:
  python rag/extract_from_manual.py \\
    --make Toyota --model Yaris \\
    --start-year 2019 --end-year 2020 --engine "1.5 Hybrid" \\
    --pdf BOOK_YARIS_HYBRID_OM52A96H_2019-2020.pdf

  python rag/extract_from_manual.py \\
    --make Kia --model Rio \\
    --start-year 2017 --end-year 2024 --engine "1.0T" \\
    --pdf Rio-SC-2017.pdf \\
    --spec engine_oil_type          # מיצוי ספציפי אחד בלבד
"""
import argparse
import json
import os
import re
import sys
import time
import warnings

warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

# ─── מילות מפתח לכל spec_type (אנגלית — כפי שמופיעות במדריכי יצרן) ──────────────

SPEC_KEYWORDS: dict[str, list[str]] = {
    "engine_oil_type": [
        "oil type", "engine oil", "viscosity", "SAE", "0W-", "5W-", "10W-",
        "recommended oil", "motor oil grade",
    ],
    "engine_oil_capacity": [
        "oil capacity", "engine oil capacity", "oil volume", "with filter",
        "without filter", "oil refill", "liters", "quarts",
    ],
    "oil_drain_plug_torque": [
        "drain plug", "oil drain plug", "drain bolt torque", "oil pan plug",
    ],
    "oil_change_interval": [
        "oil change interval", "oil maintenance", "change oil every", "service interval",
        "oil life", "scheduled maintenance",
    ],
    "wheel_torque": [
        "wheel nut torque", "lug nut torque", "wheel bolt torque",
        "tightening torque", "wheel fastener", "hub nut",
    ],
    "spark_plug_torque": [
        "spark plug torque", "spark plug tightening", "plug installation torque",
    ],
    "spark_plug_type": [
        "spark plug", "NGK", "Denso", "Champion", "plug type", "plug part number",
        "ignition plug",
    ],
    "spark_plug_gap": [
        "spark plug gap", "plug gap", "electrode gap", "gap setting",
    ],
    "brake_fluid_type": [
        "brake fluid", "DOT 3", "DOT 4", "DOT 5", "brake fluid type",
    ],
    "coolant_type": [
        "coolant type", "antifreeze", "engine coolant", "coolant color",
        "radiator fluid", "LLC", "super long life",
    ],
    "battery_capacity_ah": [
        "battery capacity", "amp hour", "Ah", "battery specification", "12V battery",
    ],
    "battery_cca": [
        "cold cranking", "CCA", "cranking amps", "battery rating",
    ],
    "headlight_low_beam_bulb": [
        "low beam", "headlight bulb", "H4", "H7", "H11", "HB3", "HB4",
        "headlamp bulb", "low beam type",
    ],
    "headlight_high_beam_bulb": [
        "high beam", "headlight", "H1", "H7", "HB3", "high beam bulb",
    ],
    "fog_light_front_bulb": [
        "fog light", "fog lamp", "front fog", "fog bulb", "H8", "H11", "H16",
    ],
    "turn_signal_front_bulb": [
        "turn signal", "turn indicator", "flasher", "front signal bulb",
        "amber bulb", "P21W", "WY21W",
    ],
    "brake_light_bulb": [
        "brake light", "stop light", "brake lamp", "rear stop", "P21W", "W21W",
    ],
    "brake_caliper_torque": [
        "caliper bolt", "caliper torque", "brake caliper", "caliper mounting",
        "sliding pin torque",
    ],
    # ── נורות נוספות ───────────────────────────────────────────────────────────
    "backup_light_bulb": [
        "backup lamp", "reverse lamp", "back-up lamp", "backup light bulb",
        "reverse light bulb", "W16W",
    ],
    "turn_signal_rear_bulb": [
        "rear turn signal", "rear indicator lamp", "rear blinker",
        "rear flasher bulb", "rear combination lamp turn",
    ],
    "parking_light_bulb": [
        "position lamp", "parking light bulb", "position light",
        "front position", "side marker", "W5W",
    ],
    "license_plate_bulb": [
        "license plate lamp", "license plate light", "number plate lamp",
        "registration plate lamp",
    ],
    "rear_fog_light_bulb": [
        "rear fog lamp", "rear fog light", "fog rear",
    ],
    "interior_dome_bulb": [
        "room lamp", "dome light", "map lamp", "interior lamp",
        "ceiling light", "overhead light", "FESTON",
    ],
    # ── מגבים ──────────────────────────────────────────────────────────────────
    "wiper_front_driver_mm": [
        "driver wiper", "front wiper blade", "windshield wiper blade",
        "wiper blade size", "wiper blade length",
    ],
    "wiper_front_passenger_mm": [
        "passenger wiper", "front passenger wiper blade",
        "wiper blade size", "wiper blade length",
    ],
    "wiper_rear_mm": [
        "rear wiper blade", "rear window wiper", "rear wiper length",
        "rear wiper size",
    ],
    # ── מסננים ─────────────────────────────────────────────────────────────────
    "engine_air_filter": [
        "air cleaner element", "air filter element", "air filter replacement",
        "engine air filter", "air cleaner filter",
    ],
    "cabin_air_filter": [
        "cabin air filter", "climate control air filter", "pollen filter",
        "cabin filter replacement", "AC filter", "ventilation filter",
    ],
    # ── צמיגים ─────────────────────────────────────────────────────────────────
    "tire_size_front": [
        "tire size", "tyre size", "P185", "P195", "P205", "P215", "P225",
        "185/", "195/", "205/", "215/", "recommended tire",
    ],
    "tire_pressure_front": [
        "inflation pressure", "tire inflation", "cold tire pressure",
        "tire pressure front", "recommended pressure", "psi", "kPa",
    ],
    "tire_pressure_rear": [
        "inflation pressure", "tire inflation", "cold tire pressure",
        "tire pressure rear", "recommended pressure", "psi", "kPa",
    ],
    # ── קירור ──────────────────────────────────────────────────────────────────
    "coolant_capacity_liters": [
        "coolant capacity", "coolant volume", "cooling system capacity",
        "antifreeze capacity", "coolant refill",
    ],
    # ── מצבר ───────────────────────────────────────────────────────────────────
    "battery_group_size": [
        "battery group", "DIN battery", "battery specification", "battery type",
        "12V battery group", "battery size",
    ],
}

# prompt hint per spec_type (unit + format guidance for Groq)
_SPEC_HINTS: dict[str, str] = {
    "engine_oil_type":         "Viscosity grade only (e.g. 0W-20, 5W-30). No brand names.",
    "engine_oil_capacity":     "Total capacity in LITERS with filter (e.g. 3.7). Number only.",
    "oil_drain_plug_torque":   "Torque in Nm (e.g. 40). Convert ft-lb→Nm if needed (×1.356).",
    "oil_change_interval":     "Interval in km (e.g. 10000). Convert miles→km if needed (×1.609).",
    "wheel_torque":            "Lug nut torque in Nm (e.g. 103). Convert ft-lb→Nm if needed. Typical 85-160 Nm.",
    "spark_plug_torque":       "Torque in Nm (e.g. 18). Convert ft-lb→Nm if needed.",
    "spark_plug_type":         "OEM part number (e.g. NGK DILKAR7A11). If not found, return null.",
    "spark_plug_gap":          "Gap in MILLIMETERS (e.g. 1.1). Convert inches→mm if needed (×25.4). Typical 0.7-1.3 mm.",
    "brake_fluid_type":        "DOT grade only (e.g. DOT 3, DOT 4, DOT 5.1).",
    "coolant_type":            "Color or type (e.g. Toyota Red LLC, Pink, Blue, Green). Be specific.",
    "battery_capacity_ah":     "Capacity in Ah (e.g. 45). Number only.",
    "battery_cca":             "CCA value (e.g. 395). Number only.",
    "headlight_low_beam_bulb": "Bulb type code (e.g. H7, H4, LED). Code only.",
    "headlight_high_beam_bulb":"Bulb type code (e.g. H1, H7, LED). Code only.",
    "fog_light_front_bulb":    "Bulb type code (e.g. H8, H11, LED). Code only.",
    "turn_signal_front_bulb":  "Bulb type code (e.g. P21W, WY21W). Code only.",
    "brake_light_bulb":           "Bulb type code (e.g. P21W, W21W). Code only.",
    "brake_caliper_torque":       "Bolt torque in Nm (e.g. 25). Convert ft-lb→Nm if needed.",
    "backup_light_bulb":          "Bulb type code (e.g. W16W, P21W). Code only.",
    "turn_signal_rear_bulb":      "Bulb type code (e.g. PY21W, P21W). Code only.",
    "parking_light_bulb":         "Bulb type code (e.g. W5W, T10, P21/5W). Code only.",
    "license_plate_bulb":         "Bulb type code (e.g. W5W, C5W). Code only.",
    "rear_fog_light_bulb":        "Bulb type code (e.g. P21W, W21W, LED). Code only.",
    "interior_dome_bulb":         "Bulb type code (e.g. FESTON, W5W, SV8.5). Code only.",
    "wiper_front_driver_mm":      "Length in mm as integer (e.g. 650). Number only.",
    "wiper_front_passenger_mm":   "Length in mm as integer (e.g. 400). Number only.",
    "wiper_rear_mm":              "Length in mm as integer (e.g. 300). Number only.",
    "engine_air_filter":          "OEM part number or code (e.g. 28113-1G000). Code only.",
    "cabin_air_filter":           "OEM part number or code (e.g. 97133-1G000). Code only.",
    "tire_size_front":            "Full tire size code (e.g. 185/65R15, 205/55R16). Size only.",
    "tire_pressure_front":        "Pressure in bar (e.g. 2.3). Convert: PSI÷14.504 or kPa÷100. Number only.",
    "tire_pressure_rear":         "Pressure in bar (e.g. 2.3). Convert: PSI÷14.504 or kPa÷100. Number only.",
    "coolant_capacity_liters":    "Capacity in liters (e.g. 5.5). Convert US qt×0.946 if needed. Number only.",
    "battery_group_size":         "Battery group/DIN code (e.g. DIN 60, L2, Group 47). Code only.",
}

_SPEC_UNITS: dict[str, str] = {
    "engine_oil_type": "", "engine_oil_capacity": "L",
    "oil_drain_plug_torque": "Nm", "oil_change_interval": "km",
    "wheel_torque": "Nm", "spark_plug_torque": "Nm",
    "spark_plug_type": "", "spark_plug_gap": "mm",
    "brake_fluid_type": "", "coolant_type": "",
    "battery_capacity_ah": "Ah", "battery_cca": "CCA",
    "headlight_low_beam_bulb": "", "headlight_high_beam_bulb": "",
    "fog_light_front_bulb": "", "turn_signal_front_bulb": "",
    "brake_light_bulb": "", "brake_caliper_torque": "Nm",
    "backup_light_bulb": "", "turn_signal_rear_bulb": "",
    "parking_light_bulb": "", "license_plate_bulb": "",
    "rear_fog_light_bulb": "", "interior_dome_bulb": "",
    "wiper_front_driver_mm": "mm", "wiper_front_passenger_mm": "mm", "wiper_rear_mm": "mm",
    "engine_air_filter": "", "cabin_air_filter": "",
    "tire_size_front": "", "tire_pressure_front": "bar", "tire_pressure_rear": "bar",
    "coolant_capacity_liters": "L", "battery_group_size": "",
}

GROQ_MODEL = "llama-3.3-70b-versatile"

NO_SPARK_ENGINES = {"ev", "diesel", "tdi", "cdi", "dci", "hdi", "d4d", "electric"}


# ─── Supabase client ────────────────────────────────────────────────────────────

def _get_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("חסרים SUPABASE_URL / SUPABASE_KEY ב-.env")
    return create_client(url, key)


# ─── שלב 1: שליפת chunks מ-doc_chunks לפי מילות מפתח ───────────────────────────

def _fetch_chunks(client, pdf_filename: str, keywords: list[str], max_chunks: int = 6) -> list[str]:
    """
    מחפש chunks ב-doc_chunks לפי source=pdf_filename ומילות מפתח (ILIKE).
    מחזיר עד max_chunks טקסטים ייחודיים.
    """
    seen: set[str] = set()
    results: list[str] = []

    for kw in keywords:
        if len(results) >= max_chunks:
            break
        try:
            resp = (
                client.table("doc_chunks")
                .select("chunk")
                .eq("source", pdf_filename)
                .ilike("chunk", f"%{kw}%")
                .limit(3)
                .execute()
            )
            for row in resp.data or []:
                chunk = (row.get("chunk") or "").strip()
                if chunk and chunk not in seen:
                    seen.add(chunk)
                    results.append(chunk)
                    if len(results) >= max_chunks:
                        break
        except Exception:
            continue

    return results


# ─── שלב 2: חילוץ ערך מ-chunks דרך Groq ────────────────────────────────────────

def _extract_with_groq(
    make: str, model: str, engine: str,
    spec_type: str, chunks: list[str],
) -> dict | None:
    """
    שולח chunks מספר היצרן ל-Groq ומבקש חילוץ ערך מובנה.
    מחזיר {"value": str, "unit": str} או None.
    """
    try:
        from groq import Groq
    except ImportError:
        print("  ⚠️  groq לא מותקן: pip install groq", flush=True)
        return None

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        print("  ⚠️  חסר GROQ_API_KEY ב-.env", flush=True)
        return None

    client = Groq(api_key=api_key)
    hint   = _SPEC_HINTS.get(spec_type, "Extract the value.")
    unit   = _SPEC_UNITS.get(spec_type, "")

    context_text = "\n---\n".join(f"[EXCERPT {i+1}]\n{c[:500]}" for i, c in enumerate(chunks))

    system = (
        "You are a vehicle specification extractor. "
        "Extract ONLY the requested specification from the manual excerpts provided. "
        "Return JSON with keys: value (string or null), unit (string). "
        "If the specification is not found in the excerpts, return {\"value\": null, \"unit\": \"\"}."
    )

    user = (
        f"Vehicle: {make} {model} {engine}\n"
        f"Specification needed: {spec_type}\n"
        f"Unit rule: {hint}\n\n"
        f"Manual excerpts:\n{context_text}\n\n"
        f"Return JSON only. Example: {{\"value\": \"5W-30\", \"unit\": \"\"}}"
    )

    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0,
            max_tokens=80,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        data = json.loads(raw)
        value = data.get("value")
        if value is None or str(value).lower() in ("null", "none", "n/a", ""):
            return None
        return {"value": str(value).strip(), "unit": data.get("unit", unit) or unit}
    except Exception as e:
        print(f"  ⚠️  Groq error: {e}", flush=True)
        return None


# ─── פוסט-פרוסס יחידות ─────────────────────────────────────────────────────────

def _post_process(spec_type: str, value: str, unit: str) -> tuple[str, str]:
    if spec_type == "spark_plug_gap":
        nums = re.findall(r"[\d.]+", value)
        if nums:
            first = float(nums[0])
            if first < 0.5:
                converted = [f"{float(n) * 25.4:.2f}" for n in nums]
                return "-".join(converted), "mm"
        return value, "mm"

    if spec_type in ("wheel_torque", "oil_drain_plug_torque", "spark_plug_torque", "brake_caliper_torque"):
        u = unit.lower().replace("-", "").replace(".", "").replace(" ", "")
        if "ftlb" in u or "lbft" in u or "ftlbs" in u:
            nums = re.findall(r"[\d.]+", value)
            if nums:
                nm_val = round(float(nums[0]) * 1.356)
                return str(nm_val), "Nm"

    if spec_type == "oil_change_interval":
        u = unit.lower()
        if "mile" in u:
            nums = re.findall(r"[\d.]+", value)
            if nums:
                km_val = round(float(nums[0]) * 1.609)
                return str(km_val), "km"

    if spec_type in ("tire_pressure_front", "tire_pressure_rear"):
        u = unit.lower().replace(" ", "")
        nums = re.findall(r"[\d.]+", value)
        if nums:
            first = float(nums[0])
            if "psi" in u or (not u and first > 10):
                bar_val = round(first / 14.504, 2)
                return str(bar_val), "bar"
            if "kpa" in u or (not u and first > 100):
                bar_val = round(first / 100, 2)
                return str(bar_val), "bar"
        return value, "bar"

    return value, unit


# ─── שמירה ל-vehicle_specs ─────────────────────────────────────────────────────

def _save(client, make, model, start_year, end_year, engine, spec_type, value, unit) -> bool:
    try:
        client.table("vehicle_specs").upsert(
            {
                "make":        make,
                "model":       model,
                "year":        start_year,
                "start_year":  start_year,
                "end_year":    end_year,
                "engine":      engine,
                "engine_code": "",
                "spec_type":   spec_type,
                "value":       value,
                "unit":        unit,
                "source_url":  "",
                "confidence":  "manual",
            },
            on_conflict="make,model,start_year,end_year,engine,spec_type",
        ).execute()
        return True
    except Exception as e:
        print(f"  ❌ שגיאת שמירה: {e}", flush=True)
        return False


# ─── רישום ב-vehicle_manuals ───────────────────────────────────────────────────

def _register_manual(client, make, model, start_year, end_year, engine, pdf_filename) -> bool:
    """רושם את המיפוי רכב ↔ PDF ב-vehicle_manuals (אם הטבלה קיימת)."""
    try:
        client.table("vehicle_manuals").upsert(
            {
                "make":         make,
                "model":        model,
                "start_year":   start_year,
                "end_year":     end_year,
                "engine":       engine,
                "pdf_filename": pdf_filename,
            },
            on_conflict="make,model,start_year,end_year,engine",
        ).execute()
        return True
    except Exception:
        return False


# ─── פייפליין ראשי ──────────────────────────────────────────────────────────────

def extract_from_manual(
    make: str,
    model: str,
    start_year: int,
    end_year: int,
    engine: str,
    pdf_filename: str,
    spec_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    מחלץ ספציפיקציות ממדריך היצרן ושומר ל-Supabase.

    מחזיר: {"extracted": N, "saved": N, "skipped": N}
    """
    client = _get_client()

    is_ev_diesel = any(k in engine.lower() for k in NO_SPARK_ENGINES)
    skip_spark = {"spark_plug_type", "spark_plug_gap", "spark_plug_torque"}

    spec_types = list(SPEC_KEYWORDS.keys())
    if spec_filter:
        spec_types = [s for s in spec_types if s == spec_filter]
        if not spec_types:
            print(f"spec_type לא קיים: {spec_filter}")
            return {}

    print(f"\n📖 מחלץ מ: {pdf_filename}", flush=True)
    print(f"   רכב: {make} {model} {engine} ({start_year}–{end_year})", flush=True)
    print(f"   סוגי ספציפיקציות: {len(spec_types)}\n", flush=True)

    stats = {"extracted": 0, "saved": 0, "skipped": 0}

    for spec_type in spec_types:
        if is_ev_diesel and spec_type in skip_spark:
            print(f"  ⏭️  {spec_type} — מדולג (EV/diesel)", flush=True)
            stats["skipped"] += 1
            continue

        keywords = SPEC_KEYWORDS[spec_type]
        chunks   = _fetch_chunks(client, pdf_filename, keywords, max_chunks=6)

        if not chunks:
            print(f"  ❌ {spec_type} — לא נמצאו chunks", flush=True)
            stats["skipped"] += 1
            continue

        print(f"  🔍 {spec_type} — {len(chunks)} chunks נמצאו", end="", flush=True)

        result = _extract_with_groq(make, model, engine, spec_type, chunks)
        time.sleep(0.5)  # Groq rate limit

        if result is None:
            print(f" → לא הצליח", flush=True)
            stats["skipped"] += 1
            continue

        value, unit = _post_process(spec_type, result["value"], result["unit"])
        stats["extracted"] += 1
        print(f" → {value} {unit}", flush=True)

        if not dry_run:
            ok = _save(client, make, model, start_year, end_year, engine, spec_type, value, unit)
            if ok:
                stats["saved"] += 1

    if not dry_run:
        _register_manual(client, make, model, start_year, end_year, engine, pdf_filename)

    print(f"\n✅ סיכום: {stats['extracted']} חולצו, {stats['saved']} נשמרו, {stats['skipped']} דולגו")
    return stats


# ─── CLI ────────────────────────────────────────────────────────────────────────

def _cli():
    parser = argparse.ArgumentParser(description="חלץ ספציפיקציות ממדריך יצרן ב-Supabase")
    parser.add_argument("--make",       required=True,  help="יצרן (Toyota)")
    parser.add_argument("--model",      required=True,  help="דגם (Yaris)")
    parser.add_argument("--start-year", required=True,  type=int, dest="start_year")
    parser.add_argument("--end-year",   required=True,  type=int, dest="end_year")
    parser.add_argument("--engine",     required=True,  help="מנוע (1.5 Hybrid)")
    parser.add_argument("--pdf",        required=True,  help="שם קובץ PDF (כפי שנשמר ב-doc_chunks)")
    parser.add_argument("--spec",       default=None,   help="מיצוי spec_type ספציפי בלבד")
    parser.add_argument("--dry-run",    action="store_true", help="הצג בלי לשמור")
    args = parser.parse_args()

    extract_from_manual(
        make=args.make,
        model=args.model,
        start_year=args.start_year,
        end_year=args.end_year,
        engine=args.engine,
        pdf_filename=args.pdf,
        spec_filter=args.spec,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    _cli()
