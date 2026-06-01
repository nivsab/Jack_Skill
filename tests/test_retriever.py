"""
בדיקות יחידה ל-_detect_relevant_specs — זיהוי ספציפיקציות רלוונטיות לפי מילות מפתח.

הפונקציה קובעת אילו spec_type-ים ייאספו מ-Supabase/רשת לכל הודעת משתמש.
שגיאה כאן → ספציפיקציות לא נשלפות → LLM מנחש ערכים במקום לדעת.
אין LLM, אין רשת, אין Supabase.
"""
import pytest
from rag.retriever import _detect_relevant_specs


class TestDetectRelevantSpecs:

    # ─── שמן ─────────────────────────────────────────────────────────────────────

    def test_hebrew_oil_keyword(self):
        specs = _detect_relevant_specs("איך מחליפים שמן מנוע?")
        assert "engine_oil_type" in specs
        assert "engine_oil_capacity" in specs
        assert "oil_drain_plug_torque" in specs

    def test_english_oil_keyword(self):
        specs = _detect_relevant_specs("how to do an oil change")
        assert "engine_oil_type" in specs

    def test_oil_filter_keyword(self):
        specs = _detect_relevant_specs("מסנן שמן טויוטה קורולה")
        assert "oil_drain_plug_torque" in specs

    # ─── בלמים ───────────────────────────────────────────────────────────────────

    def test_brake_keywords(self):
        specs = _detect_relevant_specs("החלפת רפידות בלמים")
        assert "brake_caliper_torque" in specs
        assert "brake_fluid_type" in specs

    def test_english_brake_keyword(self):
        specs = _detect_relevant_specs("brake pad replacement")
        assert "brake_caliper_torque" in specs

    # ─── נרות הצתה ───────────────────────────────────────────────────────────────

    def test_spark_plug_hebrew(self):
        specs = _detect_relevant_specs("החלפת נרות הצתה")
        assert "spark_plug_torque" in specs
        assert "spark_plug_type" in specs
        assert "spark_plug_gap" in specs

    def test_spark_plug_english(self):
        specs = _detect_relevant_specs("spark plug replacement")
        assert "spark_plug_type" in specs

    # ─── מצבר ────────────────────────────────────────────────────────────────────

    def test_battery_hebrew(self):
        specs = _detect_relevant_specs("החלפת מצבר")
        assert "battery_capacity_ah" in specs
        assert "battery_cca" in specs

    def test_battery_english(self):
        specs = _detect_relevant_specs("car battery replacement")
        assert "battery_capacity_ah" in specs

    # ─── נורות ───────────────────────────────────────────────────────────────────

    def test_headlight_bulb_hebrew(self):
        specs = _detect_relevant_specs("החלפת נורה בפנס קדמי")
        assert "headlight_low_beam_bulb" in specs
        assert "headlight_high_beam_bulb" in specs

    def test_bulb_english(self):
        specs = _detect_relevant_specs("headlight bulb replacement")
        assert "headlight_low_beam_bulb" in specs

    # ─── גלגל ────────────────────────────────────────────────────────────────────

    def test_wheel_torque_hebrew(self):
        specs = _detect_relevant_specs("כמה מומנט לבורגי הגלגל?")
        assert "wheel_torque" in specs

    # ─── ריק ─────────────────────────────────────────────────────────────────────

    def test_unrelated_text_returns_empty(self):
        specs = _detect_relevant_specs("מה שעת הפתיחה של המוסך?")
        assert specs == []

    def test_empty_string_returns_empty(self):
        assert _detect_relevant_specs("") == []

    # ─── איכות רשימה ─────────────────────────────────────────────────────────────

    def test_no_duplicates_with_overlapping_keywords(self):
        specs = _detect_relevant_specs("שמן oil מסנן שמן")  # שלוש מילות מפתח, אותה קטגוריה
        assert len(specs) == len(set(specs))

    def test_multiple_categories_combined(self):
        specs = _detect_relevant_specs("שמן מנוע ובלמים")
        assert "engine_oil_type" in specs
        assert "brake_caliper_torque" in specs
