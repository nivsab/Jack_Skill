"""
fill_missing.py — ממלא ספציפיקציות חסרות ב-Supabase ישירות דרך Groq (ללא DDG).

מזהה את הצירופים החסרים (make × model × engine × spec_type) ומבקש מ-Groq
לספק את הערך מתוך ידע האימון שלו.

פוסט-פרוסס מובנה:
  - spark_plug_gap: המרת inches ל-mm אוטומטית
  - wheel_torque: המרת ft-lb ל-Nm אוטומטית

CLI:
  python fill_missing.py                   # כל הספציפיקציות החסרות
  python fill_missing.py spark_plug_gap    # רק spec_type ספציפי
"""
import json
import os
import re
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from seed import COMMON_CARS, GROQ_MODEL

SPEC_META: dict[str, dict] = {
    "engine_oil_type": {
        "unit": "",
        "prompt_hint": "Viscosity grade (e.g. 0W-20, 5W-30). Never return null.",
    },
    "engine_oil_capacity": {
        "unit": "L",
        "prompt_hint": "Engine oil capacity in LITERS with filter change. Never return null.",
    },
    "oil_drain_plug_torque": {
        "unit": "Nm",
        "prompt_hint": "Oil drain plug torque in Nm. Convert ft-lb to Nm if needed (1 ft-lb = 1.356 Nm). Never return null.",
    },
    "wheel_torque": {
        "unit": "Nm",
        "prompt_hint": "Wheel lug nut torque in Nm. Convert ft-lb to Nm if needed (1 ft-lb = 1.356 Nm). Typical range 85-160 Nm. Never return null.",
    },
    "spark_plug_type": {
        "unit": "",
        "prompt_hint": "OEM spark plug part number (e.g. NGK DILKAR7A11). Never return null unless EV/diesel.",
    },
    "spark_plug_gap": {
        "unit": "mm",
        "prompt_hint": "Spark plug gap in MILLIMETERS. Convert inches to mm (1 in = 25.4 mm). Examples: 0.028 in = 0.71 mm, 0.032 in = 0.81 mm, 0.044 in = 1.12 mm. Typical range 0.7-1.3 mm. Never return null unless EV/diesel.",
    },
}

NO_SPARK_ENGINES = {"ev", "diesel", "tdi", "cdi", "dci", "hdi", "d4d"}


def _is_ev_or_diesel(engine: str) -> bool:
    e = engine.lower()
    return any(k in e for k in NO_SPARK_ENGINES)


def _post_process(spec_type: str, value: str, unit: str) -> tuple[str, str]:
    """המרת יחידות לאחר קבלה מ-Groq."""
    if spec_type == "spark_plug_gap":
        # זהה ערך inch ותמיר ל-mm
        nums = re.findall(r"[\d.]+", value)
        if nums:
            first = float(nums[0])
            if first < 0.5:  # inch-scale
                mm_vals = [f"{float(n) * 25.4:.2f}" for n in nums]
                return "-".join(mm_vals), "mm"
        return value, "mm"

    if spec_type in ("wheel_torque", "oil_drain_plug_torque"):
        # זהה ft-lb ותמיר ל-Nm
        u = unit.lower().replace("-", "").replace(".", "")
        if "ftlb" in u or "ftlbs" in u or "lbft" in u:
            nums = re.findall(r"[\d.]+", value)
            if nums:
                nm = round(float(nums[0]) * 1.356)
                return str(nm), "Nm"
        return value, "Nm"

    return value, unit


def _groq_extract(groq, make: str, model: str, year: int, engine: str,
                  spec_type: str) -> dict | None:
    meta = SPEC_META[spec_type]
    unit = meta["unit"]
    hint = meta["prompt_hint"]

    prompt = f"""You are an automotive specifications database. Provide the {spec_type} for:
Vehicle: {year} {make} {model} {engine}

{hint}

Return ONLY a JSON object: {{"value": "<value>", "unit": "{unit}"}}

If this vehicle type genuinely cannot have this spec (e.g., EV has no spark plug gap), return:
{{"value": null, "unit": "{unit}"}}

No explanation, no markdown, ONLY the JSON."""

    try:
        resp = groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=80,
        )
        text = resp.choices[0].message.content.strip()
        s = text.find("{")
        e = text.rfind("}") + 1
        if s == -1 or e == 0:
            return None
        data = json.loads(text[s:e])
        if data.get("value") is None:
            return None
        raw_value = str(data["value"])
        raw_unit  = data.get("unit", unit)
        value, final_unit = _post_process(spec_type, raw_value, raw_unit)
        return {"value": value, "unit": final_unit}
    except Exception:
        return None


def main() -> None:
    from rag.cache import get_spec, save_spec
    from groq import Groq

    filter_spec = sys.argv[1] if len(sys.argv) > 1 else None
    specs_to_run = [filter_spec] if filter_spec else list(SPEC_META.keys())

    groq = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

    total = skipped = failed = 0

    for car in COMMON_CARS:
        make       = car["manufacturer"]
        model      = car["model"]
        start_year = car["start_year"]
        end_year   = car["end_year"]
        engine     = car["engine"]
        mid_year   = (start_year + end_year) // 2

        print(f"🚗 {make} {model} {start_year}-{end_year} {engine}")

        for spec_type in specs_to_run:
            # דלג על spark plug לרכבי EV/diesel
            if spec_type in ("spark_plug_type", "spark_plug_gap") and _is_ev_or_diesel(engine):
                skipped += 1
                continue

            # בדוק אם כבר קיים
            existing = get_spec(
                {"manufacturer": make, "model": model, "year": start_year, "engine": engine},
                spec_type,
            )
            if existing:
                print(f"   ⏭️  {spec_type}: {existing['value']}")
                skipped += 1
                continue

            result = _groq_extract(groq, make, model, mid_year, engine, spec_type)
            if not result:
                print(f"   ❌ {spec_type}: Groq לא מצא ערך")
                failed += 1
                time.sleep(0.3)
                continue

            ok = save_spec(
                vehicle={"manufacturer": make, "model": model,
                         "year": start_year, "engine": engine},
                spec_type=spec_type,
                value=result["value"],
                unit=result["unit"],
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

            time.sleep(0.2)

        print()

    print(f"✅ סה\"כ: {total} נשמרו | {skipped} דולגו | {failed} נכשלו")


if __name__ == "__main__":
    main()
