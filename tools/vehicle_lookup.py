"""
כלי זיהוי רכב לפי מספר רישוי — API ממשלתי (data.gov.il).

resource_id: 053cea08-09bc-40ec-8f7a-156f0677aff3
מחזיר: יצרן, דגם, שנה, קוד מנוע, דלק, צמיגים.

CLI: python tools/vehicle_lookup.py <מספר_רישוי>
פלט: JSON ל-stdout
"""
import json
import sys
import urllib.parse
import urllib.request
import warnings

warnings.filterwarnings("ignore")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESOURCE_ID = "053cea08-09bc-40ec-8f7a-156f0677aff3"
BASE_URL     = "https://data.gov.il/api/3/action/datastore_search"


def _normalize_plate(plate: str) -> str:
    """מסיר מקפים, רווחים, אותיות — מחזיר ספרות בלבד."""
    return "".join(ch for ch in plate if ch.isdigit())


def lookup_by_plate(plate: str) -> dict | None:
    """
    מחפש רכב לפי מספר רישוי ב-API הממשלתי.
    מחזיר dict עם פרטי הרכב, או None אם לא נמצא.
    """
    plate_clean = _normalize_plate(plate)
    if not plate_clean:
        return None

    try:
        params = urllib.parse.urlencode({
            "resource_id": RESOURCE_ID,
            "filters":     json.dumps({"mispar_rechev": int(plate_clean)}),
            "limit":       1,
        })
        req = urllib.request.Request(
            f"{BASE_URL}?{params}",
            headers={"User-Agent": "jack-skill/1.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())

        records = data.get("result", {}).get("records", [])
        if not records:
            return None

        r = records[0]
        return {
            "manufacturer":  (r.get("tozeret_nm") or "").strip(),
            "model":         (r.get("kinuy_mishari") or r.get("degem_nm") or "").strip(),
            "year":          int(r.get("shnat_yitzur") or 0),
            "engine_code":   (r.get("degem_manoa") or "").strip(),
            "fuel_type":     (r.get("sug_delek_nm") or "").strip(),
            "license_plate": plate_clean,
            "tire_front":    (r.get("zmig_kidmi") or "").strip(),
            "tire_rear":     (r.get("zmig_ahori") or "").strip(),
        }
    except Exception:
        return None


# ─── CLI ──────────────────────────────────────────────────────────────────────

def _cli_main():
    """CLI: python tools/vehicle_lookup.py <מספר_רישוי>"""
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"found": False, "error": "usage: vehicle_lookup.py <license_plate>"}))
            return

        plate = " ".join(sys.argv[1:])
        result = lookup_by_plate(plate)

        if result:
            print(json.dumps({"found": True, **result}, ensure_ascii=False))
        else:
            print(json.dumps({"found": False, "reason": "plate not found in registry"}))

    except Exception as exc:
        print(json.dumps({"found": False, "error": str(exc)}))


if __name__ == "__main__":
    _cli_main()
