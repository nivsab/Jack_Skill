"""
מידע מזהה של הרכב — משותף לכל כלי ה-Python.
"""
from typing import Optional
from typing_extensions import TypedDict


class VehicleInfo(TypedDict, total=False):
    manufacturer:  str  # יצרן (Toyota, Hyundai…)
    model:         str  # דגם (Corolla, i20…)
    year:          int  # שנת ייצור
    engine:        str  # סוג מנוע (1.6, 2.0T, Hybrid…)
    engine_code:   str  # קוד מנוע מדויק מה-API (2ZR-FXE, B48B20…)
    license_plate: str  # מספר רישוי (ספרות בלבד, ללא מקפים)
    fuel_type:     str  # סוג דלק (בנזין, דיזל, היברידי…)
