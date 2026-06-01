"""
בדיקות יחידה ללוגיקת tools/parts.py — חישובי המלצות וזיהוי פעולות.

הפונקציות כאן הן Python טהור — אין DDG, אין LLM, אין I/O.
"""
import pytest
from tools.parts import _build_recommendation, _detect_operation, _snippets_to_text


class TestBuildRecommendation:

    def test_critical_part_always_recommends_israel(self):
        prices = {"israel_min": 100, "israel_max": 200,
                  "aliexpress_min": 15, "aliexpress_max": 40}
        rec, emoji = _build_recommendation(prices, is_critical=True)
        assert "ישראל" in rec
        assert "קריטי" in rec
        assert emoji == "⚠️"

    def test_critical_part_recommends_israel_even_with_huge_savings(self):
        prices = {"israel_min": 200, "israel_max": 300,
                  "aliexpress_min": 5, "aliexpress_max": 10}
        rec, emoji = _build_recommendation(prices, is_critical=True)
        assert "ישראל" in rec

    def test_non_critical_big_savings_recommends_aliexpress(self):
        # 80% savings — מעל סף 40%
        prices = {"israel_min": 100, "israel_max": 150,
                  "aliexpress_min": 20, "aliexpress_max": 35}
        rec, emoji = _build_recommendation(prices, is_critical=False)
        assert "אליאקספרס" in rec
        assert emoji == "✅"

    def test_non_critical_small_savings_recommends_israel(self):
        # 10% savings — מתחת לסף 40%
        prices = {"israel_min": 100, "israel_max": 150,
                  "aliexpress_min": 90, "aliexpress_max": 130}
        rec, emoji = _build_recommendation(prices, is_critical=False)
        assert "ישראל" in rec
        assert emoji == "🔵"

    def test_non_critical_exactly_40pct_recommends_israel(self):
        # בדיוק 40% — הסף הוא >=40 אז צריך להמליץ aliexpress
        prices = {"israel_min": 100, "aliexpress_min": 60,
                  "israel_max": 150, "aliexpress_max": 90}
        rec, emoji = _build_recommendation(prices, is_critical=False)
        assert "אליאקספרס" in rec

    def test_missing_aliexpress_price_recommends_israel(self):
        prices = {"israel_min": 100, "israel_max": 150,
                  "aliexpress_min": None, "aliexpress_max": None}
        rec, _ = _build_recommendation(prices, is_critical=False)
        assert "ישראל" in rec

    def test_missing_both_prices_recommends_israel(self):
        prices = {"israel_min": None, "israel_max": None,
                  "aliexpress_min": None, "aliexpress_max": None}
        rec, _ = _build_recommendation(prices, is_critical=False)
        assert "ישראל" in rec


class TestDetectOperation:

    @pytest.mark.parametrize("text,expected", [
        ("החלפת שמן מנוע",         "oil_change"),
        ("oil filter replacement",  "oil_change"),
        ("פקק שמן",                 "oil_change"),
        ("brake pad replacement",   "brake_pad_replacement"),
        ("החלפת רפידות בלמים",      "brake_pad_replacement"),
        ("דיסק בלם",                "brake_pad_replacement"),
        ("air filter",              "air_filter"),
        ("מסנן אוויר",             "air_filter"),
        ("spark plug",              "spark_plug"),
        ("נרות הצתה",              "spark_plug"),
        ("tire change",             "tire_change"),
        ("החלפת גלגל",             "tire_change"),
        ("צמיג פנצ'ר",             "tire_change"),
        ("car battery",             "battery"),
        ("מצבר לא מתניע",          "battery"),
        ("wiper blades",            "wiper"),
        ("מגבים שרוטים",           "wiper"),
    ])
    def test_detects_operation_from_text(self, text, expected):
        assert _detect_operation(text) == expected

    def test_unrelated_text_returns_none(self):
        assert _detect_operation("מה מזג האוויר היום?") is None

    def test_empty_string_returns_none(self):
        assert _detect_operation("") is None

    def test_case_insensitive(self):
        assert _detect_operation("OIL FILTER") == "oil_change"
        assert _detect_operation("Brake Pad") == "brake_pad_replacement"


class TestSnippetsToText:

    def test_empty_list_returns_no_results_message(self):
        assert _snippets_to_text([]) == "לא נמצאו תוצאות"

    def test_single_snippet_formatted_correctly(self):
        result = _snippets_to_text([{"body": "מחיר 100 שקל"}])
        assert "[1]" in result
        assert "מחיר 100 שקל" in result

    def test_multiple_snippets_numbered(self):
        snippets = [{"body": "תוצאה א"}, {"body": "תוצאה ב"}]
        result = _snippets_to_text(snippets)
        assert "[1]" in result
        assert "[2]" in result

    def test_missing_body_handled_gracefully(self):
        result = _snippets_to_text([{"title": "רק כותרת, אין body"}])
        assert "[1]" in result  # לא קורס
