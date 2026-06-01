"""
seed.py — ניהול cache ספציפיקציות ב-Supabase.

שלושה מצבים:
  python seed.py --seed              # מילוי אוטומטי דרך DDG + Groq
  python seed.py --export specs.csv  # מייצא נתונים קיימים ל-CSV לאימות ידני
  python seed.py --import specs.csv  # מייבא CSV מאומת ומעלה confidence=verified

תהליך מומלץ לנתונים מאומתים:
  1. אסוף נתונים ידנית / מאתרי יצרנים ב-specs.csv
  2. סמן verified=true בשורות שאומתו
  3. python seed.py --import specs.csv
"""
import argparse
import csv
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

# ─── רשימת רכבים נפוצים ────────────────────────────────────────────────────────

# פורמט: manufacturer, model, start_year, end_year, engine
COMMON_CARS: list[dict] = [
    # ── עיר / קטן ─────────────────────────────────────────────────────────────
    {"manufacturer": "Kia",         "model": "Picanto",         "start_year": 2017, "end_year": 2024, "engine": "1.0"},
    {"manufacturer": "Kia",         "model": "Picanto",         "start_year": 2017, "end_year": 2024, "engine": "1.2"},
    {"manufacturer": "Hyundai",     "model": "i10",             "start_year": 2020, "end_year": 2024, "engine": "1.0"},
    {"manufacturer": "Hyundai",     "model": "i10",             "start_year": 2020, "end_year": 2024, "engine": "1.2"},
    {"manufacturer": "Suzuki",      "model": "Alto",            "start_year": 2022, "end_year": 2024, "engine": "1.0"},
    {"manufacturer": "Chevrolet",   "model": "Spark",           "start_year": 2016, "end_year": 2022, "engine": "1.0"},
    {"manufacturer": "Toyota",      "model": "Aygo",            "start_year": 2014, "end_year": 2021, "engine": "1.0"},

    # ── תת-קומפקט ─────────────────────────────────────────────────────────────
    {"manufacturer": "Toyota",      "model": "Yaris",           "start_year": 2020, "end_year": 2024, "engine": "1.5"},
    {"manufacturer": "Toyota",      "model": "Yaris",           "start_year": 2020, "end_year": 2024, "engine": "1.5 Hybrid"},
    {"manufacturer": "Mazda",       "model": "2",               "start_year": 2015, "end_year": 2022, "engine": "1.5"},
    {"manufacturer": "Suzuki",      "model": "Swift",           "start_year": 2017, "end_year": 2023, "engine": "1.2"},
    {"manufacturer": "Suzuki",      "model": "Swift",           "start_year": 2017, "end_year": 2023, "engine": "1.0 BoosterJet"},
    {"manufacturer": "Hyundai",     "model": "i20",             "start_year": 2020, "end_year": 2024, "engine": "1.0T"},
    {"manufacturer": "Hyundai",     "model": "i20",             "start_year": 2020, "end_year": 2024, "engine": "1.2"},
    {"manufacturer": "Kia",         "model": "Rio",             "start_year": 2017, "end_year": 2024, "engine": "1.0T"},
    {"manufacturer": "Kia",         "model": "Rio",             "start_year": 2017, "end_year": 2024, "engine": "1.4"},
    {"manufacturer": "Skoda",       "model": "Fabia",           "start_year": 2021, "end_year": 2024, "engine": "1.0 TSI"},
    {"manufacturer": "Skoda",       "model": "Fabia",           "start_year": 2021, "end_year": 2024, "engine": "1.5 TSI"},
    {"manufacturer": "Seat",        "model": "Ibiza",           "start_year": 2017, "end_year": 2024, "engine": "1.0 TSI"},
    {"manufacturer": "Seat",        "model": "Ibiza",           "start_year": 2017, "end_year": 2024, "engine": "1.5 TSI"},

    # ── קומפקט ────────────────────────────────────────────────────────────────
    {"manufacturer": "Toyota",      "model": "Corolla",         "start_year": 2019, "end_year": 2024, "engine": "1.8 Hybrid"},
    {"manufacturer": "Toyota",      "model": "Corolla",         "start_year": 2019, "end_year": 2024, "engine": "2.0 Hybrid"},
    {"manufacturer": "Toyota",      "model": "Corolla",         "start_year": 2019, "end_year": 2024, "engine": "1.6"},
    {"manufacturer": "Mazda",       "model": "3",               "start_year": 2019, "end_year": 2024, "engine": "2.0"},
    {"manufacturer": "Mazda",       "model": "3",               "start_year": 2019, "end_year": 2024, "engine": "2.5"},
    {"manufacturer": "Hyundai",     "model": "Elantra",         "start_year": 2021, "end_year": 2024, "engine": "1.6"},
    {"manufacturer": "Hyundai",     "model": "Elantra",         "start_year": 2021, "end_year": 2024, "engine": "2.0"},
    {"manufacturer": "Skoda",       "model": "Octavia",         "start_year": 2020, "end_year": 2024, "engine": "1.0 TSI"},
    {"manufacturer": "Skoda",       "model": "Octavia",         "start_year": 2020, "end_year": 2024, "engine": "1.5 TSI"},
    {"manufacturer": "Skoda",       "model": "Octavia",         "start_year": 2020, "end_year": 2024, "engine": "2.0 TDI"},
    {"manufacturer": "Honda",       "model": "Civic",           "start_year": 2021, "end_year": 2024, "engine": "1.5T"},
    {"manufacturer": "Honda",       "model": "Civic",           "start_year": 2021, "end_year": 2024, "engine": "2.0 e:HEV"},
    {"manufacturer": "Kia",         "model": "Forte",           "start_year": 2019, "end_year": 2024, "engine": "2.0"},
    {"manufacturer": "Kia",         "model": "Forte",           "start_year": 2019, "end_year": 2024, "engine": "1.6T"},
    {"manufacturer": "Toyota",      "model": "Camry",           "start_year": 2019, "end_year": 2024, "engine": "2.5 Hybrid"},

    # ── SUV ───────────────────────────────────────────────────────────────────
    {"manufacturer": "Hyundai",     "model": "Tucson",          "start_year": 2021, "end_year": 2024, "engine": "1.6T"},
    {"manufacturer": "Hyundai",     "model": "Tucson",          "start_year": 2021, "end_year": 2024, "engine": "1.6 Hybrid"},
    {"manufacturer": "Kia",         "model": "Sportage",        "start_year": 2022, "end_year": 2024, "engine": "1.6T"},
    {"manufacturer": "Kia",         "model": "Sportage",        "start_year": 2022, "end_year": 2024, "engine": "1.6 Hybrid"},
    {"manufacturer": "Toyota",      "model": "RAV4",            "start_year": 2019, "end_year": 2024, "engine": "2.0"},
    {"manufacturer": "Toyota",      "model": "RAV4",            "start_year": 2019, "end_year": 2024, "engine": "2.5 Hybrid"},
    {"manufacturer": "Hyundai",     "model": "Kona",            "start_year": 2023, "end_year": 2024, "engine": "1.0T"},
    {"manufacturer": "Hyundai",     "model": "Kona",            "start_year": 2023, "end_year": 2024, "engine": "1.6T"},
    {"manufacturer": "Toyota",      "model": "Corolla Cross",   "start_year": 2020, "end_year": 2024, "engine": "1.8 Hybrid"},
    {"manufacturer": "Mitsubishi",  "model": "Outlander",       "start_year": 2021, "end_year": 2024, "engine": "2.5"},
    {"manufacturer": "Mitsubishi",  "model": "Outlander",       "start_year": 2021, "end_year": 2024, "engine": "2.4 PHEV"},
    {"manufacturer": "Nissan",      "model": "Qashqai",         "start_year": 2021, "end_year": 2024, "engine": "1.3T"},
    {"manufacturer": "Nissan",      "model": "Qashqai",         "start_year": 2021, "end_year": 2024, "engine": "1.5 e-Power"},

    # ── היברידי / חשמלי ───────────────────────────────────────────────────────
    {"manufacturer": "Kia",         "model": "Niro",            "start_year": 2022, "end_year": 2024, "engine": "HEV"},
    {"manufacturer": "Kia",         "model": "Niro",            "start_year": 2022, "end_year": 2024, "engine": "EV"},
    {"manufacturer": "BYD",         "model": "Atto 3",          "start_year": 2022, "end_year": 2024, "engine": "EV"},
    {"manufacturer": "Tesla",       "model": "Model Y",         "start_year": 2021, "end_year": 2024, "engine": "EV"},
    {"manufacturer": "Tesla",       "model": "Model 3",         "start_year": 2017, "end_year": 2024, "engine": "EV"},

    # ── פרימיום ───────────────────────────────────────────────────────────────
    {"manufacturer": "Skoda",       "model": "Superb",          "start_year": 2019, "end_year": 2024, "engine": "1.5 TSI"},
    {"manufacturer": "Skoda",       "model": "Superb",          "start_year": 2019, "end_year": 2024, "engine": "2.0 TDI"},
    {"manufacturer": "Audi",        "model": "A4",              "start_year": 2016, "end_year": 2024, "engine": "2.0 TFSI"},
    {"manufacturer": "Audi",        "model": "A4",              "start_year": 2016, "end_year": 2024, "engine": "2.0 TDI"},
    {"manufacturer": "BMW",         "model": "3 Series",        "start_year": 2019, "end_year": 2024, "engine": "2.0i"},
    {"manufacturer": "BMW",         "model": "3 Series",        "start_year": 2019, "end_year": 2024, "engine": "2.0d"},
    {"manufacturer": "Mercedes-Benz","model": "C-Class",        "start_year": 2021, "end_year": 2024, "engine": "1.5T"},
    {"manufacturer": "Mercedes-Benz","model": "C-Class",        "start_year": 2021, "end_year": 2024, "engine": "2.0T"},
    {"manufacturer": "Volvo",       "model": "S60",             "start_year": 2019, "end_year": 2024, "engine": "B4"},
    {"manufacturer": "Volvo",       "model": "S60",             "start_year": 2019, "end_year": 2024, "engine": "T8"},
]

# ספציפיקציות לחיפוש — שאילתה ויחידה
SPEC_QUERIES: dict[str, dict] = {
    "engine_oil_type":        {"q": "engine oil type viscosity grade",           "unit": "",   "note": ""},
    "engine_oil_capacity":    {"q": "engine oil capacity liters with filter",    "unit": "L",  "note": ""},
    "oil_drain_plug_torque":  {"q": "oil drain plug torque Nm",                  "unit": "Nm", "note": "Always in Nm. Convert ft-lb to Nm if needed (1 ft-lb = 1.356 Nm)."},
    "wheel_torque":           {"q": "wheel lug nut torque Nm",                   "unit": "Nm", "note": "Always in Nm. Convert ft-lb to Nm if needed (1 ft-lb = 1.356 Nm). Typical range: 85-160 Nm."},
    "spark_plug_type":        {"q": "spark plug OEM part number type",           "unit": "",   "note": ""},
    "spark_plug_gap":         {"q": "spark plug gap mm",                         "unit": "mm", "note": "Always in mm. Convert inches to mm if needed (1 in = 25.4 mm). Typical range: 0.7-1.3 mm. Example: 0.028 in = 0.71 mm, 0.044 in = 1.12 mm."},
}

GROQ_MODEL = "llama-3.3-70b-versatile"


# ─── עזרים ────────────────────────────────────────────────────────────────────

def _supabase_client():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        print("❌ חסרים SUPABASE_URL / SUPABASE_KEY ב-.env")
        sys.exit(1)
    return create_client(url, key)


def _groq_client():
    from groq import Groq
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        print("❌ חסר GROQ_API_KEY ב-.env")
        sys.exit(1)
    return Groq(api_key=key)


def _ddg_search(query: str, max_results: int = 5) -> str:
    """חיפוש DDG — מחזיר snippets כטקסט."""
    try:
        from duckduckgo_search import DDGS
        with DDGS(timeout=5) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return "\n".join(r.get("body", "") for r in results if r.get("body"))
    except Exception:
        return ""


def _extract_with_groq(groq, make: str, model: str, year: int, engine: str,
                       spec_type: str, unit: str, note: str, snippets: str) -> dict | None:
    """
    שולח snippets ל-Groq ומחלץ ערך מובנה.
    מחזיר {"value": "...", "unit": "..."} או None.
    """
    unit_note = f"\n- {note}" if note else ""
    prompt = f"""You are an automotive specifications expert. Provide the {spec_type} for:
Vehicle: {year} {make} {model} {engine}

Web search snippets (use as reference):
{snippets[:2000]}

Return ONLY a JSON object:
{{"value": "<the spec value>", "unit": "{unit}"}}

Rules:
- Use the snippets as primary source. If snippets are insufficient, use your training knowledge.
- value must be specific (e.g. "5W-30", "4.2", "103", "NGK DILKAR7A11"){unit_note}
- Only return {{"value": null}} if you truly have no knowledge of this spec for this vehicle.
- No explanation, no markdown, only the JSON object."""

    try:
        resp = groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=100,
        )
        text = resp.choices[0].message.content.strip()
        # חילוץ JSON מהתשובה
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        data = json.loads(text[start:end])
        if data.get("value") is None:
            return None
        return {"value": str(data["value"]), "unit": data.get("unit", unit)}
    except Exception:
        return None


# ─── פקודות ───────────────────────────────────────────────────────────────────

def cmd_seed() -> None:
    """--seed: מחפש ספציפיקציות דרך DDG ומחלץ דרך Groq → שומר ל-Supabase."""
    from rag.cache import get_spec, save_spec

    groq      = _groq_client()
    total     = 0
    skipped   = 0
    failed    = 0

    print(f"🚀 מתחיל seed — {len(COMMON_CARS)} רכבים × {len(SPEC_QUERIES)} ספציפיקציות\n")

    for car in COMMON_CARS:
        make       = car["manufacturer"]
        model      = car["model"]
        start_year = car["start_year"]
        end_year   = car["end_year"]
        engine     = car["engine"]
        mid_year   = (start_year + end_year) // 2  # שנת אמצע לחיפוש DDG

        print(f"🚗 {make} {model} {start_year}-{end_year} {engine}")

        for spec_type, spec_meta in SPEC_QUERIES.items():
            # בדוק אם כבר קיים ב-DB (חיפוש לפי start_year)
            existing = get_spec(
                {"manufacturer": make, "model": model, "year": start_year, "engine": engine},
                spec_type,
            )
            if existing:
                print(f"   ⏭️  {spec_type}: כבר קיים ({existing['value']})")
                skipped += 1
                continue

            # חיפוש DDG
            query    = f"{make} {model} {mid_year} {engine} {spec_meta['q']}"
            snippets = _ddg_search(query)
            time.sleep(1)  # הגנה מפני rate limit של DDG

            # חילוץ Groq (גם ללא snippets — Groq ישתמש בידע שלו)
            result = _extract_with_groq(
                groq, make, model, mid_year, engine,
                spec_type, spec_meta["unit"], spec_meta.get("note", ""), snippets,
            )
            if not result:
                print(f"   ❌ {spec_type}: Groq לא מצא ערך")
                failed += 1
                continue

            # שמירה ל-Supabase עם טווח שנים
            ok = save_spec(
                vehicle={"manufacturer": make, "model": model,
                         "year": start_year, "engine": engine},
                spec_type=spec_type,
                value=result["value"],
                unit=result["unit"],
                source_url="",
                confidence="llm",
                start_year=start_year,
                end_year=end_year,
            )
            if ok:
                print(f"   ✅ {spec_type}: {result['value']} {result['unit']}")
                total += 1
            else:
                print(f"   ❌ {spec_type}: שגיאת Supabase")
                failed += 1

        print()

    print(f"✅ סה\"כ: {total} נשמרו | {skipped} דולגו (קיימים) | {failed} נכשלו")


def cmd_export(csv_path: str) -> None:
    """מייצא את כל הנתונים מ-Supabase ל-CSV לאימות ידני."""
    client = _supabase_client()
    resp   = client.table("vehicle_specs").select("*").execute()
    rows   = resp.data or []

    if not rows:
        print("⚠️  אין נתונים ב-Supabase עדיין.")
        return

    fieldnames = ["make", "model", "start_year", "end_year", "engine", "engine_code",
                  "spec_type", "value", "unit", "confidence", "verified"]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "make":        row.get("make", ""),
                "model":       row.get("model", ""),
                "start_year":  row.get("start_year", ""),
                "end_year":    row.get("end_year", ""),
                "engine":      row.get("engine", ""),
                "engine_code": row.get("engine_code", ""),
                "spec_type":   row.get("spec_type", ""),
                "value":       row.get("value", ""),
                "unit":        row.get("unit", ""),
                "confidence":  row.get("confidence", ""),
                "verified":    "false",
            })

    print(f"✅ יוצאו {len(rows)} שורות → {csv_path}")
    print(f"   לאחר אימות: python seed.py --import {csv_path}")


def cmd_import(csv_path: str) -> None:
    """מייבא CSV מאומת — מעדכן confidence=verified לשורות עם verified=true."""
    from rag.cache import save_spec

    if not os.path.exists(csv_path):
        print(f"❌ קובץ לא נמצא: {csv_path}")
        sys.exit(1)

    updated = skipped = 0

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("verified", "").strip().lower() != "true":
                skipped += 1
                continue

            # תמיכה בפורמט ישן (year) ובפורמט חדש (start_year/end_year)
            start_year = int(row["start_year"]) if row.get("start_year") else None
            end_year   = int(row["end_year"])   if row.get("end_year")   else None
            year       = start_year or int(row.get("year", 0) or 0)

            ok = save_spec(
                vehicle={
                    "manufacturer": row["make"],
                    "model":        row["model"],
                    "year":         year,
                    "engine":       row.get("engine", ""),
                    "engine_code":  row.get("engine_code", ""),
                },
                spec_type=row["spec_type"],
                value=row["value"],
                unit=row.get("unit", ""),
                source_url="",
                confidence="verified",
                start_year=start_year,
                end_year=end_year,
            )
            updated += 1 if ok else 0

    print(f"✅ עודכנו {updated} ספציפיקציות ל-verified. דולגו {skipped}.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="seed.py — ניהול cache ג'ק")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed",   action="store_true", help="מילוי אוטומטי דרך DDG + Groq")
    group.add_argument("--export", metavar="CSV",       help="ייצוא נתונים ל-CSV")
    group.add_argument("--import", metavar="CSV",       dest="import_csv", help="ייבוא CSV מאומת")

    args = parser.parse_args()
    if args.seed:
        cmd_seed()
    elif args.export:
        cmd_export(args.export)
    elif args.import_csv:
        cmd_import(args.import_csv)


if __name__ == "__main__":
    main()
