"""
שכבת ה-cache ב-Supabase — שמירה ושליפה של ספציפיקציות רכב.

כל גישה ל-DB עוברת דרך כאן.
ה-client נוצר פעם אחת (singleton) ונשמר לשימוש חוזר.
"""
import os
from typing import Optional

from supabase import create_client, Client

from state import VehicleInfo

_client: Optional[Client] = None


def _get_client() -> Client:
    """
    מחזיר מופע singleton של Supabase client.

    נוצר בקריאה הראשונה ומשותף לכל הקריאות הבאות.
    זורק EnvironmentError אם חסרים SUPABASE_URL / SUPABASE_KEY ב-.env.
    """
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        if not url or not key:
            raise EnvironmentError(
                "חסרים SUPABASE_URL / SUPABASE_KEY ב-.env — ראה SETUP.md"
            )
        _client = create_client(url, key)
    return _client


def get_spec(vehicle: VehicleInfo, spec_type: str) -> Optional[dict]:
    """
    מחפש ספציפיקציה ב-Supabase לפי רכב + סוג.

    חיפוש: שנת הרכב חייבת להיות בטווח start_year–end_year.
    מנסה שני חיפושים:
    1. עם מנוע ספציפי (engine/engine_code) — הכי מדויק.
    2. ללא מנוע — ספציפיקציה כללית לדגם.

    מחזיר dict עם value/unit/source_url/confidence, או None.
    """
    try:
        client = _get_client()
        make        = vehicle.get("manufacturer", "")
        model       = vehicle.get("model", "")
        year        = vehicle.get("year", 0)
        engine      = vehicle.get("engine", "")
        engine_code = vehicle.get("engine_code", "")

        def _query(eng: str):
            return (
                client.table("vehicle_specs")
                .select("value,unit,source_url,confidence,engine_code")
                .ilike("make", make)
                .ilike("model", model)
                .lte("start_year", year)
                .gte("end_year", year)
                .eq("engine", eng)
                .eq("spec_type", spec_type)
                .order("confidence")          # verified > scraped > llm
                .limit(1)
                .execute()
            )

        # 1. חיפוש לפי engine_code מדויק
        if engine_code:
            result = (
                client.table("vehicle_specs")
                .select("value,unit,source_url,confidence,engine_code")
                .ilike("make", make)
                .ilike("model", model)
                .lte("start_year", year)
                .gte("end_year", year)
                .eq("engine_code", engine_code)
                .eq("spec_type", spec_type)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]

        # 2. חיפוש לפי engine string (אם קיים)
        if engine:
            result = _query(engine)
            if result.data:
                return result.data[0]

        # 3. Fallback: כל שורה לדגם+שנה+ספציפיקציה, בלי סינון מנוע
        result = (
            client.table("vehicle_specs")
            .select("value,unit,source_url,confidence,engine_code")
            .ilike("make", make)
            .ilike("model", model)
            .lte("start_year", year)
            .gte("end_year", year)
            .eq("spec_type", spec_type)
            .order("confidence")
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]

        return None

    except Exception:
        return None


def save_spec(
    vehicle: VehicleInfo,
    spec_type: str,
    value: str,
    unit: str = "",
    source_url: str = "",
    confidence: str = "scraped",
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> bool:
    """
    שומר ספציפיקציה ב-Supabase באמצעות upsert.

    start_year/end_year: טווח דור הרכב.
    אם לא סופקו — משתמש ב-year מה-vehicle (נקודתי).
    """
    try:
        client = _get_client()
        year = vehicle.get("year", 0)
        client.table("vehicle_specs").upsert(
            {
                "make":        vehicle.get("manufacturer", ""),
                "model":       vehicle.get("model", ""),
                "year":        year,
                "start_year":  start_year if start_year is not None else year,
                "end_year":    end_year   if end_year   is not None else year,
                "engine":      vehicle.get("engine", ""),
                "engine_code": vehicle.get("engine_code", ""),
                "spec_type":   spec_type,
                "value":       value,
                "unit":        unit,
                "source_url":  source_url,
                "confidence":  confidence,
            },
            on_conflict="make,model,start_year,end_year,engine,spec_type",
        ).execute()
        return True

    except Exception:
        return False
