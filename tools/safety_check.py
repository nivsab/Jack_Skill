"""
בדיקת Hard Stop — מחסום בטיחות ברמת קוד לפני כל הדרכת DIY.

מזהה פעולות מסוכנות לפי מילות מפתח ומחזיר JSON.
Claude חייב לקרוא לכלי זה לפני כל הדרכה — גם בהודעה ה-40 בשיחה.

CLI: python tools/safety_check.py "<message>"
פלט:
  {"safe_for_diy": true}
  {"safe_for_diy": false, "layer": 1, "reason": "...", "action": "mechanic_script"}
  {"safe_for_diy": null,  "layer": 3, "reason": "...", "action": "ask_user_level"}
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")


# ─── רשימת Hard Stop — שלוש שכבות ─────────────────────────────────────────────
# (layer, keywords_tuple, reason_he)
# safe_for_diy=False  → מוסך תמיד
# safe_for_diy=None   → תלוי ברמת ניסיון (timing belt)

_HARD_STOPS: list[tuple[int, bool | None, tuple[str, ...], str]] = [

    # ── שכבה 1: בטיחות נהיגה ישירה ──────────────────────────────────────────
    (1, False, (
        "קליפר", "caliper",
        "צינור בלמים", "brake line", "brake hose", "brake pipe",
        "מאסטר סילינדר", "master cylinder",
    ), "מערכת בלמים — מוסך בלבד (Hard Stop שכבה 1)"),

    (1, False, (
        "מוט גרירה", "tie rod", "tie-rod",
        "תיבת הגה", "steering rack", "steering box", "steering gear",
        "זרוע היגוי", "steering arm",
    ), "מערכת היגוי — מוסך בלבד (Hard Stop שכבה 1)"),

    (1, False, (
        "ג'וינט כדורי", "ball joint",
        "ציר הינע", "cv axle", "cv joint", "driveshaft", "drive shaft",
        "half shaft",
    ), "מתלים / ציר — מוסך בלבד (Hard Stop שכבה 1)"),

    # ── שכבה 2: סיכון גופני ─────────────────────────────────────────────────
    (2, False, (
        "משאבת דלק", "fuel pump",
        "מזרק", "injector", "fuel injector",
        "צינור דלק", "fuel line", "fuel hose",
    ), "מערכת דלק — סיכון אש (Hard Stop שכבה 2)"),

    (2, False, (
        "איירבג", "airbag", "air bag",
        "srs", "חגורת בטיחות", "seatbelt", "seat belt",
        "pretensioner",
    ), "SRS / איירבגים — מוסך בלבד (Hard Stop שכבה 2)"),

    (2, False, (
        "מתח גבוה", "high voltage",
        "פאק סוללה", "battery pack", "hv battery",
        "inverter", "אינוורטר", "converter",
        "hybrid battery", "ev battery",
    ), "מתח גבוה היברידי/חשמלי — מוסך בלבד (Hard Stop שכבה 2)"),

    # ── שכבה 3: תלוי ניסיון / תמיד מוסך ───────────────────────────────────
    (3, None, (
        "רצועת תזמון", "timing belt",
        "שרשרת תזמון", "timing chain",
    ), "רצועת תזמון — רמת 🔧 בלבד. רמות 🔑🆘 → מוסך (Hard Stop שכבה 3)"),

    (3, False, (
        "גסקט ראש", "head gasket",
        "ראש מנוע", "cylinder head",
    ), "גסקט ראש מנוע — מוסך תמיד (Hard Stop שכבה 3)"),
]


# ─── Prompt Injection patterns ────────────────────────────────────────────────
# זיהוי ניסיונות לעקוף את חוקי המערכת — עברית ואנגלית

_PI_PATTERNS: list[str] = [
    # אנגלית — ניסיונות קלאסיים
    "ignore previous", "ignore all previous", "ignore your instructions",
    "forget everything", "forget your instructions", "forget previous",
    "override", "bypass", "disregard",
    "you are now", "act as", "pretend you are", "pretend to be",
    "new persona", "new role", "roleplay as",
    "jailbreak", "dan mode", "developer mode", "god mode",
    "do anything now", "no restrictions",
    "system prompt", "initial prompt", "hidden prompt",
    "repeat after me", "print your instructions",
    "reveal your system", "show me your prompt",
    # עברית — ניסיונות עקיפה
    "התעלם מהוראות", "התעלם מכל", "שכח את ההוראות",
    "עקוף את", "עקוף הגבלות",
    "אתה עכשיו", "התנהג כ", "עכשיו אתה",
    "ללא הגבלות", "ללא חוקים",
    "הצג את הפרומפט", "הצג הוראות מערכת",
    "מצב פיתוח", "מצב אל", "מצב חופשי",
]


def check_injection(message: str) -> dict:
    """
    בודק ניסיון Prompt Injection בהודעה.

    מחזיר:
      {"injection_detected": false}                             — הודעה תקינה
      {"injection_detected": true, "pattern": "...",
       "action": "block", "response": "..."}                   — חסימה
    """
    text_lower = message.lower()
    for pattern in _PI_PATTERNS:
        if pattern in text_lower:
            return {
                "injection_detected": True,
                "pattern":  pattern,
                "action":   "block",
                "response": "אני מזהה ניסיון לשנות את חוקי הפעולה שלי. אני לא יכול לפעול מחוץ לגבולות הבטיחות שהוגדרו לי.",
            }
    return {"injection_detected": False}


def check(message: str) -> dict:
    """
    בודק אם הבקשה מכילה מילות מפתח של Hard Stop.

    מחזיר:
      {"safe_for_diy": true}                                     — בטוח להדרכה
      {"safe_for_diy": false, "layer": N, "reason": "...",
       "action": "mechanic_script"}                              — מוסך בלבד
      {"safe_for_diy": null,  "layer": 3, "reason": "...",
       "action": "ask_user_level"}                               — תלוי ברמת ניסיון
    """
    text = message.lower()

    for layer, safe_value, keywords, reason in _HARD_STOPS:
        if any(kw.lower() in text for kw in keywords):
            if safe_value is False:
                return {
                    "safe_for_diy": False,
                    "layer":        layer,
                    "reason":       reason,
                    "action":       "mechanic_script",
                }
            # safe_value is None → timing belt — תלוי ברמת ניסיון
            return {
                "safe_for_diy": None,
                "layer":        layer,
                "reason":       reason,
                "action":       "ask_user_level",
            }

    return {"safe_for_diy": True}


if __name__ == "__main__":
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"error": "usage: safety_check.py <message>"}))
            sys.exit(0)

        msg = " ".join(sys.argv[1:])

        # בדיקת Prompt Injection קודמת — אם מזוהה, חסום מיד
        pi = check_injection(msg)
        if pi["injection_detected"]:
            print(json.dumps(pi, ensure_ascii=False))
            sys.exit(0)

        result = check(msg)
        print(json.dumps(result, ensure_ascii=False))

    except Exception as exc:
        print(json.dumps({"safe_for_diy": True, "warning": str(exc)}))
