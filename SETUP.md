# מדריך הגדרות ידניות — ג'ק 🔧

מסמך זה מפרט **כל ערך** שצריך להזין ידנית כדי שהמערכת תעבוד,
מאיפה הוא מגיע ומה ברירת המחדל שלו.

---

## 🔴 חובה — בלי אלה הקוד לא יעבוד

### 1. צור קובץ `.env`

העתק את `.env.example` ל-`.env` (אותה תיקייה):

```bash
cp .env.example .env
```

לאחר מכן מלא את שני השדות הבאים:

---

#### `JACK_LLM_PROVIDER`
**קובץ:** `.env`  
**מה זה:** איזה ספק AI להשתמש בו.  
**ערכים אפשריים:** `openai` / `anthropic` / `gemini`  
**ברירת מחדל:** `openai`

```
JACK_LLM_PROVIDER=openai
```

---

#### מפתח API של הספק שבחרת

**קובץ:** `.env`  
רק את המפתח של הספק שבחרת — השאר אפשר להשאיר ריקים.

| ספק | שם המשתנה | איפה מקבלים |
|-----|-----------|-------------|
| OpenAI | `OPENAI_API_KEY` | platform.openai.com/api-keys |
| Anthropic | `ANTHROPIC_API_KEY` | console.anthropic.com/keys |
| Google Gemini | `GOOGLE_API_KEY` | aistudio.google.com/apikey |

**דוגמה (OpenAI):**
```
OPENAI_API_KEY=sk-proj-...
```

---

## 🟡 אופציונלי — ברירות מחדל קיימות, אפשר לשנות

### 2. שם המודל

**קובץ:** `config.py` — שורות 13–16  
**מה זה:** איזה גרסת מודל לקרוא בתוך כל ספק.

```python
_MODEL_DEFAULTS = {
    "openai":    "gpt-4o",           # ← שנה כאן לדגם אחר (למשל gpt-4o-mini לחיסכון)
    "anthropic": "claude-sonnet-4-6", # ← שנה כאן (למשל claude-haiku-4-5-20251001 לחיסכון)
    "gemini":    "gemini-1.5-pro",   # ← שנה כאן (למשל gemini-1.5-flash לחיסכון)
}
```

> אפשר גם לדרוס דרך `.env` בלי לגעת בקוד:
> ```
> JACK_OPENAI_MODEL=gpt-4o-mini
> ```

---

### 3. תקציב ברירת מחדל ל-Mechanic Script

**קובץ:** `prompts.py` — שורה 76  
**מה זה:** הסכום שג'ק יציע כסף הגנה ("בקש אישור לפני עבודה מעל X₪").  
**ברירת מחדל:** `300₪`

```python
# prompts.py שורה 76
"...ואבקש אישור לפני כל עבודה מעל [סכום — ברירת מחדל 300]₪."
#                                                         ^^^
#                                              שנה ל-500 / 200 / כל מה שרוצים
```

---

### 4. גבול היסטוריית הודעות — ראוטר

**קובץ:** `nodes/router.py` — שורה 73  
**מה זה:** כמה הודעות אחרונות הראוטר רואה בכל קריאה.  
**ברירת מחדל:** `4`  
**טווח מומלץ:** 2–6 (יותר = מדויק יותר, יקר יותר בטוקנים)

```python
recent_messages = state["messages"][-4:]  # ← שנה את 4
```

---

### 5. גבול היסטוריית הודעות — נודים מגיבים

**קובץ:** `nodes/responder.py` — שורה 74  
**מה זה:** כמה הודעות אחרונות כל נוד תשובה רואה בכל קריאה.  
**ברירת מחדל:** `6`  
**טווח מומלץ:** 4–10

```python
messages = [SystemMessage(content=full_system), *state["messages"][-6:]]  # ← שנה את 6
```

---

### 6. ערכי Temperature לכל נוד

**קובץ:** `nodes/responder.py`  
**מה זה:** כמה "יצירתי" כל נוד — 0.0 = דטרמיניסטי לחלוטין, 1.0 = יצירתי מאוד.

| נוד | שורה | ערך נוכחי | הגיון |
|-----|------|-----------|-------|
| `router` | `router.py:67` | `0.0` | חייב להיות עקבי תמיד |
| `safety_node` | `responder.py:87` | `0.1` | חירום — דטרמיניסטי |
| `price_check_node` | `responder.py:143` | `0.2` | מספרים — עקביות |
| `vehicle_id_node` | `responder.py:156` | `0.2` | שאלה פשוטה |
| `ask_user_level_node` | `responder.py:168` | `0.1` | פורמט קבוע |
| `diagnosis_node` | `responder.py:101` | `0.3` | מאוזן |
| `mechanic_script_node` | `responder.py:131` | `0.3` | מאוזן |
| `guidance_node` | `responder.py:116` | `0.4` | קצת יצירתיות |
| `general_node` | `responder.py:179` | `0.5` | שיחה חופשית |

---

## ✅ שלב 2 — זיהוי רכב לפי מספר רישוי (API ממשלתי)

אין הגדרה נוספת — API חינמי של data.gov.il, ללא מפתח.

**שימוש:**
```
אתה: מספר הרישוי שלי הוא 12-345-67
ג'ק: python tools/vehicle_lookup.py 1234567
ג'ק: 🚗 טויוטה קורולה | 📅 2021 | 🔧 2ZR-FXE | ⛽ בנזין — נכון?
אתה: כן
ג'ק: מצוין — מכיר את הטויוטה קורולה. בוא נראה מה אפשר לחסוך. 😊
```

**מה מתקבל מה-API:**
- יצרן + כינוי מסחרי (שם מסחרי עברי)
- שנת ייצור
- קוד מנוע מדויק (לדוגמה: `2ZR-FXE`)
- סוג דלק
- גודל צמיגים קדמי ואחורי

---

## ✅ שלב 3 — RAG ספציפיקציות רכב (מומש)

מחייב הגדרת Supabase ב-`.env`:

```
SUPABASE_URL=https://qmiahkpkamehjfrwvahv.supabase.co
SUPABASE_KEY=eyJ...   # anon key מ-Supabase → Settings → API
```

**מה עובד אוטומטית:**
- `guidance_node` ו-`price_check_node` שולפים ספציפיקציות לפי מילות מפתח בשיחה
- שרשרת: Supabase cache (0ms) → DuckDuckGo → LLM fallback
- כל ספציפיקציה שנשלפת נשמרת לצמיתות (מומנטים לא משתנים)

**טבלה ב-Supabase:** `vehicle_specs`

| spec_type | דוגמה |
|-----------|-------|
| `oil_drain_plug_torque` | `40 Nm` |
| `engine_oil_type` | `5W-30 Full Synthetic` |
| `engine_oil_capacity` | `4.5 L` |
| `wheel_torque` | `103 Nm` |
| `spark_plug_torque` | `25 Nm` |
| `brake_caliper_torque` | `34 Nm` |
| `coolant_type` | `Toyota Super Long Life` |
| `brake_fluid_type` | `DOT 3` |
| `oil_change_interval` | `15000 km` |

**אמינות תוצאה מסומנת בפרומפט:**
- `✅` verified — מקור רשמי יצרן
- `🌐` scraped — נשלף מהרשת
- `🤖` llm — ידע מודל (עם אזהרה)

---

## ✅ שלב 4 — YouTube + מחירי חלפים (מומש)

### YouTube — סרטוני הדרכה

**אופן פעולה:** עברית קודם → אנגלית אם לא נמצא → cache לצמיתות.

| מצב | התנהגות |
|-----|---------|
| `YOUTUBE_API_KEY` מוגדר | YouTube Data API v3 — תוצאות רשמיות |
| ללא מפתח | DuckDuckGo video search — חינמי, אוטומטי |

```
# אופציונלי — מ-console.cloud.google.com → YouTube Data API v3
YOUTUBE_API_KEY=AIza...
```

**טבלה ב-Supabase:** `youtube_cache`

**פעולות מזוהות אוטומטית:** שמן, בלמים, מסנן אוויר, נרות, גלגל, מצבר, מגבים.

---

### מחירי חלפים — ישראל ואליאקספרס

**אין API key — DuckDuckGo בלבד, ללא cache** (מחירים משתנים).

| סוג חלף | המלצה אוטומטית |
|---------|----------------|
| מסנן שמן, בלמים, נרות, מצבר | ישראל (חלף קריטי) |
| מסנן אוויר, מגבים | AliExpress (חיסכון 40%+) |

**תהליך:** שני חיפושי DDG (ישראל + AliExpress) → LLM מחלץ טווח מחירים → המלצה אוטומטית.

---

## סיכום — צ'קליסט להרצה ראשונה

```
# חובה
[ ] 1. העתקתי .env.example → .env
[ ] 2. הגדרתי JACK_LLM_PROVIDER (openai / anthropic / gemini)
[ ] 3. הכנסתי מפתח API של הספק שבחרתי
[ ] 4. הכנסתי SUPABASE_URL + SUPABASE_KEY
[ ] 5. התקנתי חבילות: pip install -r requirements.txt
[ ] 6. הרצתי: python main.py

# שלב 2 — זיהוי לפי מספר רישוי (API ממשלתי, ללא הגדרה)
[ ] 7. המשתמש מקליד מספר רישוי → ג'ק קורא ל-vehicle_lookup.py אוטומטית

# שלב 4 — YouTube (אופציונלי)
[ ] 8. הגדרתי YOUTUBE_API_KEY לתוצאות מדויקות יותר
       (בלי זה: DuckDuckGo עובד אוטומטית)
```
