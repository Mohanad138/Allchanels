# -*- coding: utf-8 -*-
"""
بوت الريلي الموحد — حساب شخصي واحد (Telethon) يفحص 8 قنوات مصدر كل تشغيل
(بولينغ، بدون استماع مباشر مستمر) وينشر الجديد بـ 8 قنوات هدف.

الفرق عن النسخة السابقة: هذه النسخة لا تفتح اتصال طويل الأمد ولا تستخدم
events.NewMessage. كل تشغيلة تفحص الرسائل الفائتة فقط ثم تُغلق الاتصال —
مصمم ليُستدعى بشكل متكرر (مثلاً كل 5 دقائق) عبر GitHub Actions cron،
بدون مخالفة سياسة الاستخدام المقبول لـ GitHub (ممنوع تشغيل عمليات طويلة/
مستمرة عبر Actions كأنها خادم دائم).
"""

import os
import re
import json
import time
import asyncio
import subprocess

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl
import requests

# ==================== الإعدادات العامة ====================

TG_API_ID = int(os.getenv("TG_API_ID"))
TG_API_HASH = os.getenv("TG_API_HASH")
TG_SESSION = os.getenv("TG_SESSION")

GEMINI_KEY_FABRIZ = os.getenv("GEMINI_KEY_FABRIZ")
GEMINI_KEY_TECH = os.getenv("GEMINI_KEY_TECH")
GEMINI_KEY_GTA = os.getenv("GEMINI_KEY_GTA")
GEMINI_KEY_GENERAL = os.getenv("GEMINI_KEY_GENERAL")
GEMINI_KEY_SHAKO = os.getenv("GEMINI_KEY_SHAKO")
GEMINI_KEY_MEDIA = os.getenv("GEMINI_KEY_MEDIA")
GEMINI_KEY_AFLAM = os.getenv("GEMINI_KEY_AFLAM")
GEMINI_KEY_HADAF = os.getenv("GEMINI_KEY_HADAF")

GEMINI_MODEL = "gemini-flash-lite-latest"

STATE_FILE = "relay_state.json"
DOWNLOAD_DIR = "downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==================== إعدادات القنوات الثمانية ====================
# mode:
#   "copy"            -> نشر كما هو (بعد تنظيف الروابط) + فحص إعلانات فقط
#   "translate_en_ar"  -> ترجمة انجليزي -> عربي طبيعي + فحص إعلانات
#   "rephrase_ar"      -> إعادة صياغة صحفية بالعربي + فحص إعلانات
#   "fabrizio_special" -> نفس الترجمة لكن بمعايير نشر خاصة بفابريزيو

CHANNELS = {
    -1001344466508: {
        "name": "فابريزيو رومانو بالعربي",
        "target": -1002015818715,
        "mode": "fabrizio_special",
        "gemini_key": GEMINI_KEY_FABRIZ,
        "source_username": "@FabrizioRomanoTG",
    },
    -1009003922419: {
        "name": "أفلام ومسلسلات",
        "target": -1002651737980,
        "mode": "translate_en_ar",
        "gemini_key": GEMINI_KEY_AFLAM,
        "source_username": "@movie",
        "add_link": True,
        "link": "https://t.me/AflamMusalsalat4U",
    },
    -1001565832101: {
        "name": "شكو ماكو بـ كركوك",
        "target": -1001812867607,
        "mode": "rephrase_ar",
        "gemini_key": GEMINI_KEY_SHAKO,
        "source_username": "@kirkukdiary",
        "add_link": True,
        "link": "https://t.me/ShakoMakoKirkuk",
    },
    -1009001498074: {
        "name": "أخبار المال",
        "target": "@MalNewsAr",
        "mode": "translate_en_ar",
        "gemini_key": GEMINI_KEY_TECH,
        "source_username": "@WatcherGuru",
        "add_link": True,
        "link": "@MalNewsAr",
    },
    -1009001073232: {
        "name": "العراق الآن",
        "target": "@IQNowNews",
        "mode": "copy",
        "gemini_key": GEMINI_KEY_GENERAL,
        "source_username": "@RN24_IQ",
        "add_link": True,
        "link": "https://t.me/IQNowNews",
    },
    -1004443585067: {
        "name": "اهداف المباريات",
        "target": -1001877383586,
        "mode": "copy",
        "gemini_key": GEMINI_KEY_HADAF,
        "source_username": "@nar0015",
        "add_link": True,
        "link": "https://t.me/FabriAr3",
    },
    -1001530089992: {
        "name": "مكتبة الطالب العراقي",
        "target": -1001743729724,
        "mode": "copy",
        "gemini_key": GEMINI_KEY_MEDIA,
        "source_username": "@eduiq23",
        "add_link": True,
        "link": "https://t.me/TalibLib",
    },
    -1003946450145: {
        "name": "تسريبات GTA 6",
        "target": -1002218686576,
        "mode": "translate_en_ar",
        "gemini_key": GEMINI_KEY_GTA,
        "source_username": "@GTAVIStar",
        "add_link": True,
        "link": "https://t.me/GTA6AR",
    },
    -1009917651232: {
        "name": "بثوث المباريات",
        "target": "@FabriAr2",
        "mode": "match_links",
        "gemini_key": GEMINI_KEY_GENERAL,
        "source_username": "@Arena8x",
        # بدون add_link عمداً — ما نضيف رابط قناتنا بهذي القناة
    },
}

client = TelegramClient(StringSession(TG_SESSION), TG_API_ID, TG_API_HASH)

# ==================== الحالة (last_id لكل قناة) ====================

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

state = load_state()

def commit_state():
    """يحفظ relay_state.json على GitHub — يُستدعى مرة واحدة بنهاية كل تشغيلة."""
    try:
        subprocess.run(["git", "add", STATE_FILE], check=False)
        subprocess.run(["git", "commit", "-m", "update relay state"], check=False,
                        capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False,
                        capture_output=True)
        subprocess.run(["git", "push"], check=False, capture_output=True)
    except Exception as e:
        print(f"⚠️ git commit error: {e}")

# ==================== تنظيف النص ====================

def extract_hidden_link_urls(message, source_username=None):
    """يرجع روابط 'مخفية' خلف نص مقنّع زي 'اضغط هنا للمشاهدة' — نص الرسالة العادي ما يحتوي
    الرابط الحقيقي أصلاً، فبدون هذا الاستخراج يضيع الرابط بالكامل عند النشر.
    يتجاهل رابط قناة المصدر نفسها (يبقى يُحذف زي باقي إشاراتها)."""
    if not message or not getattr(message, "entities", None):
        return []
    handle = (source_username or "").lstrip("@").lower()
    urls = []
    try:
        for entity, _ in message.get_entities_text(MessageEntityTextUrl):
            url = entity.url
            if handle and f"t.me/{handle}".lower() in url.lower():
                continue
            urls.append(url)
    except Exception:
        pass
    return urls


def clean_text(text, source_username=None, strip_telegram_links=True):
    if not text:
        return ""
    cleaned = text
    cleaned = cleaned.replace('📊', '')
    if source_username:
        cleaned = re.sub(re.escape(source_username), '', cleaned, flags=re.IGNORECASE)
    if strip_telegram_links:
        # احذف أي رابط تيليجرام (قناة أو مجموعة أو دعوة انضمام) موجود بالنص — سواء قناة
        # المصدر نفسها أو أي قناة/مجموعة ثانية يروّجلها. أي رابط خارجي غير t.me (موقع رسمي،
        # نتائج، إلخ) يبقى كما هو ولا يُحذف
        cleaned = re.sub(r'(https?://)?t\.me/\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?i)forwarded from.*', '', cleaned)
    cleaned = re.sub(r'أعيد التوجيه من.*', '', cleaned)
    # حذف سطر التوقيع/الشكر اللي تضيفه قنوات ثانية بمنشورها (زي "نيمار ابن الانبار || @IRAQEDU")
    # — يشتغل بكل القنوات، على أي سطر يحتوي هذا التوقيع بغض النظر عن الصيغة بالضبط
    cleaned = re.sub(r'^.*نيمار\s*ابن\s*الانبار.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'^.*@?IRAQEDU.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def contains_click_here_phrase(text):
    """يفحص وجود عبارة 'اضغط هنا للمشاهدة' (وتنويعاتها) — منشورات بهذي الصيغة تُستبعد
    بالكامل بناءً على طلب المستخدم (كثير منها طلع منشورات احتيال/تصيّد)."""
    if not text:
        return False
    return bool(re.search(r'اضغط\s*هنا.{0,15}(للمشاهدة|لمشاهدة|مشاهدة)', text))

# ==================== Gemini ====================

def call_gemini(prompt, api_key, max_retries=3):
    if not api_key:
        raise RuntimeError("no gemini key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = 2 ** attempt
                print(f"⏳ Gemini إرجاع {resp.status_code} — إعادة محاولة {attempt}/{max_retries} بعد {wait}ث")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            return json.loads(raw)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"⏳ خطأ اتصال بـ Gemini — إعادة محاولة {attempt}/{max_retries} بعد {wait}ث: {e}")
                time.sleep(wait)
                continue
            raise
        except Exception:
            raise
    if last_error:
        raise last_error
    raise RuntimeError("gemini call failed after retries")


def call_gemini_vision(image_path, api_key, max_retries=3):
    """يفحص صورة: هل فيها نص مكتوب (بأي لغة)؟ إذا نعم يرجع ترجمته/صياغته كتعليق عربي طبيعي.
    يستخدم فقط عند غياب أي تعليق نصي على المنشور، عشان ما ينزل منشور صورة فاضية
    وفيها نص أجنبي محد يفهمه القاري العربي."""
    if not api_key:
        return {"has_text": False, "caption": ""}
    try:
        with open(image_path, "rb") as f:
            import base64
            img_b64 = base64.b64encode(f.read()).decode()
    except Exception:
        return {"has_text": False, "caption": ""}

    ext = image_path.lower().rsplit(".", 1)[-1]
    mime = "image/png" if ext == "png" else "image/jpeg"

    prompt = """افحص هذه الصورة: هل يوجد عليها أي نص مكتوب (عنوان، جملة، شعار كتابي) بأي لغة؟
- إذا يوجد نص، لخّصه وأعد صياغته كتعليق قصير طبيعي بالعربية الفصحى (وليس ترجمة حرفية)، بدون وصف الصورة نفسها.
- إذا لا يوجد أي نص مكتوب على الصورة إطلاقاً، اجعل has_text=false و caption فارغة.

أعد النتيجة بصيغة JSON فقط: {"has_text": true/false, "caption": "النص بالعربية أو فارغ"}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": mime, "data": img_b64}},
        {"text": prompt},
    ]}]}

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            result = json.loads(raw)
            return {"has_text": bool(result.get("has_text", False)),
                    "caption": (result.get("caption") or "").strip()}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            print(f"⚠️ خطأ فحص نص الصورة: {e}")
            return {"has_text": False, "caption": ""}
    return {"has_text": False, "caption": ""}


def check_is_ad(text, api_key):
    prompt = f"""حدد فقط إذا كان النص التالي إعلاناً مدفوعاً أو محتوى ترويجياً تجارياً.
اعتبره إعلاناً (is_ad=true) لو فيه أي من هذي العلامات:
- ترويج مباشر لمنتج، تطبيق، خدمة، قناة/حساب آخر، أو رعاية مدفوعة
- سعر، خصم، أو عرض ("سعر الاشتراك"، "بدل من"، نسبة خصم، إلخ)
- دعوة صريحة للتسجيل أو الاشتراك أو الحجز بدورة/كورس/منتج مقابل مبلغ
- رقم أو معرّف تواصل "للحجز" أو "للاستفسار" أو "للتواصل" بخصوص خدمة أو دورة مدفوعة
- أسماء مدرّسين/مراكز خاصة مع ترويج لدوراتهم (حتى لو المحتوى تعليمي بالمظهر)

أي خبر عادي إخباري — حتى لو ذكر جوائز، مسابقات، إعلانات رسمية من جهة حكومية، أو أحداث،
بدون سعر أو دعوة للشراء — **ليس إعلاناً**، اعتبره is_ad=false.
عند الشك بين خبر عادي وإعلان بدون أي من العلامات فوق، اجعل is_ad=false. لا تعدل النص إطلاقاً.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"is_ad": true/false}}"""
    try:
        result = call_gemini(prompt, api_key)
        return bool(result.get("is_ad", False))
    except Exception as e:
        print(f"❌ خطأ فحص الإعلان: {e}")
        return False

def call_translate(text, api_key):
    prompt = f"""أنت كاتب عربي محترف. ترجم النص التالي (بأي لغة كان مكتوب — إنجليزي، روسي، أو غيرها) إلى العربية بأسلوب طبيعي فصيح، كأن كاتبه الأصلي عربي وليس ترجمة حرفية.
تجاهل أي روابط أو إشارات لقناة المصدر. لا تضيف أي تعليق أو مقدمة من عندك.
إذا كان النص إعلاناً مدفوعاً أو محتوى ترويجياً تجارياً صريحاً (منتج، تطبيق، خدمة، رعاية مدفوعة) اجعل should_post = false.
أي خبر عادي — حتى لو ذكر جوائز أو مسابقات أو أحداث — ليس إعلاناً، انشره (should_post = true). عند الشك انشر.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "الترجمة"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return {"should_post": bool(result.get("should_post", True)),
                "text": (result.get("text") or text).strip()}
    except Exception as e:
        print(f"❌ خطأ الترجمة — لن يُنشر بلا ترجمة: {e}")
        return {"should_post": False, "text": ""}

def call_rephrase(text, api_key):
    prompt = f"""أنت محرر صحفي عراقي. أعد صياغة النص التالي بأسلوب صحفي احترافي واضح ومختصر بالعربية.
تجاهل أي روابط أو إشارات لقناة المصدر. لا تضيف أي تعليق من عندك.
إذا كان النص إعلاناً مدفوعاً أو محتوى ترويجياً تجارياً صريحاً (منتج، تطبيق، خدمة، رعاية مدفوعة) اجعل should_post = false.
أي خبر عادي — حتى لو ذكر جوائز أو مسابقات أو أحداث — ليس إعلاناً، انشره (should_post = true). عند الشك انشر.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "النص المعاد صياغته"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return {"should_post": bool(result.get("should_post", True)),
                "text": (result.get("text") or text).strip()}
    except Exception as e:
        print(f"❌ خطأ إعادة الصياغة: {e}")
        return {"should_post": True, "text": text}

def call_match_links(text, api_key):
    prompt = f"""أنت تنسّق منشورات قناة تبث روابط مشاهدة مباريات كرة القدم. حوّل النص التالي لنفس القالب بالضبط:

- احذف أي "تمديد" أو تكرار حروف بأسماء الفرق (زي "فـ ـرنـ ـسـ ـا") — اكتب الاسم عادي بدون فواصل (زي "فرنسا").
- سطر كل مباراة: "علم الدولة الأولى اسم_الفريق 🆚 اسم_الفريق علم الدولة الثانية" (بدون "✅ |" وبدون رمز ⚽️).
- سطر الوقت: "⏰ | الساعة مساءً بتوقيت 🇸🇦" (بدون كلمة "الـ" قبل العلم).
- سطر المعلّق: "🎤 | الاسم" (بدون تمديد حروف بالاسم).
- افصل بين كل مباراة والثانية بسطر فاضي.
- بعد آخر مباراة، سطر فاضي ثم: "🔗 | رابط المباريات:" ثم رابط الدعوة (https://t.me/+...) بسطر لحاله.
- بعده سطر فاضي ثم: "⬇️ | ملاحظة: اضغط على الرابط ثم «انضمام»، وبعدها اضغط مرة أخرى على الرابط للدخول 💎"
- لا تحذف أي مباراة. لا تضف أي تعليق من عندك.

مثال المدخل:
✅ | 🇫🇷 فـ ـرنـ ـسـ ـا ⚽️ تــركيــا 🇹🇷
⏰ | 9:45 مساء بتوقيت الـ 🇸🇦
🎤 | حـ ـسـ ـن العيدروس

https://t.me/+QmFvryvtAV85YmFk

⬇️| ملاحظه اضغط على الرابط ثم انضمام ثم اضغط مره اخرى على الرابط للدخول 💎

مثال المخرج المطلوب بالضبط:
🇫🇷 فرنسا 🆚 تركيا 🇹🇷
⏰ | 9:45 مساءً بتوقيت 🇸🇦
🎤 | حسن العيدروس

🔗 | رابط المباريات:
https://t.me/+QmFvryvtAV85YmFk

⬇️ | ملاحظة: اضغط على الرابط ثم «انضمام»، وبعدها اضغط مرة أخرى على الرابط للدخول 💎

النص المطلوب تنسيقه الآن:
{text}

أعد النتيجة بصيغة JSON فقط: {{"text": "النص بعد الترتيب بنفس القالب أعلاه بالضبط"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return (result.get("text") or "").strip()
    except Exception as e:
        print(f"❌ خطأ تنسيق منشور المباريات: {e}")
        return ""


def call_fabrizio(text, api_key):
    prompt = f"""أنت محرر لصفحة عربية تنقل أهم منشورات حساب فابريزيو رومانو الرسمي بالعربية.

معايير النشر — انشر (should_post = true) فقط إذا كان النص يندرج تحت واحد من هذي:
- يحتوي على عبارة "Here we go" (يُنشر دائماً بلا استثناء)
- إحصائيات لاعب (أرقام، مساهمات تهديفية، ظهورات، إلخ)
- تغطية مباراة مباشرة: التشكيلة، بداية المباراة، نهاية الشوط الأول، نهاية المباراة، نتيجة نهائية
- انتقال أو صفقة أو تجديد عقد (رسمي أو قريب الإتمام)
- تصريح مهم من لاعب أو مدرب أو مسؤول ناد عن انتقال، صفقة، مستقبله، أو حدث كروي مهم
  (تصريحات عامة سطحية أو مقابلات روتينية بلا خبر فعلي لا تُحسب "مهمة")

أي خبر آخر غير مندرج تحت هذي الفئات (تحليلات عامة، إشاعات هامشية، تعليقات جانبية، أخبار غير مباشرة
بالانتقالات أو المباريات) اجعل should_post = false.
كذلك إذا كان النص إعلاناً أو محتوى ترويجياً صريحاً اجعل should_post = false.

الترجمة (فقط إذا should_post = true):
- **ممنوع الترجمة الحرفية كلمة-بكلمة.** أعد صياغة الخبر بالكامل بأسلوب محرر رياضي عربي محترف
  (زي أسلوب مواقع كووورة أو beIN SPORTS)، كأن الخبر كُتب أصلاً بالعربي وليس مترجماً.
  غيّر ترتيب الجملة، ادمج أو افصل الجمل، واستخدم تعابير رياضية عربية شائعة (زي "أكد مصدر مقرب"،
  "من المنتظر أن"، "بات قاب قوسين من") بدل الترجمة المباشرة للتراكيب الإنجليزية.
- أبقِ عبارة "Here we go" بالإنجليزية كما هي حرفياً بدون ترجمة إذا وردت بالنص.
- احذف أي رابط أو إشارة لقناة المصدر (بما فيها روابط تويتر/X وإشارات "Fabrizio Romano on X").
  لا تضيف تعليقات من عندك.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "النص المُعالج أو فارغ"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return {"should_post": bool(result.get("should_post", False)),
                "text": (result.get("text") or "").strip()}
    except Exception as e:
        print(f"❌ خطأ معالجة فابريزيو — لن يُنشر بلا ترجمة: {e}")
        return {"should_post": False, "text": ""}

async def apply_processing(config, text):
    """يرجع (should_post, final_text)."""
    mode = config["mode"]
    if not text:
        return True, ""

    if not config.get("gemini_key"):
        print(f"❌ سر Gemini مفقود بهذي القناة ({config['name']}) — تأكد من إضافته بـ GitHub Secrets. لن يُنشر.")
        return False, ""

    if mode == "copy":
        is_ad = check_is_ad(text, config["gemini_key"])
        return (not is_ad), text

    if mode == "match_links":
        result_text = call_match_links(text, config["gemini_key"])
        return bool(result_text), result_text

    if mode == "translate_en_ar":
        result = call_translate(text, config["gemini_key"])
        return result["should_post"], result["text"]

    if mode == "rephrase_ar":
        result = call_rephrase(text, config["gemini_key"])
        return result["should_post"], result["text"]

    if mode == "fabrizio_special":
        force_post = bool(re.search(r'here\s*we\s*go', text, re.IGNORECASE))
        result = call_fabrizio(text, config["gemini_key"])
        should_post = bool(result["text"]) and (result["should_post"] or force_post)
        return should_post, result["text"]

    return True, text

# ==================== معالجة ونشر دفعة رسائل (منشور مفرد أو ألبوم) ====================

async def process_batch(source_id, messages):
    config = CHANNELS.get(source_id)
    if not config:
        return

    raw_text = ""
    text_msg = None
    for m in messages:
        if m.message:
            raw_text = m.message
            text_msg = m
            break

    if contains_click_here_phrase(raw_text):
        print(f"⏭️  تم تجاهل منشور — {config['name']} (يحتوي 'اضغط هنا للمشاهدة' — يُستبعد دائماً)")
        return

    hidden_links = extract_hidden_link_urls(text_msg, config.get("source_username"))
    if hidden_links:
        # الرابط الحقيقي كان مخفي خلف نص زي "اضغط هنا" — نضيفه كنص ظاهر حتى ما يضيع
        raw_text = (raw_text.rstrip() + "\n\n" + "\n".join(hidden_links)) if raw_text else "\n".join(hidden_links)

    strip_tg_links = config["mode"] != "match_links"
    cleaned = clean_text(raw_text, config.get("source_username"), strip_telegram_links=strip_tg_links)
    should_post, final_text = await apply_processing(config, cleaned)

    if not should_post:
        print(f"⏭️  تم تجاهل منشور — {config['name']} (إعلان أو غير مهم، أو خطأ تقني بالمعالجة — راجع الأسطر فوق)")
        return

    media_msgs = [m for m in messages if m.photo or m.video or m.document]

    # فحص نص الصورة بالذكاء الاصطناعي (فقط عند غياب أي تعليق، بوضع ترجمة/إعادة صياغة)
    # هذا يحتاج تحميل صورة واحدة صغيرة فقط — الفيديوهات/الملفات ما تُحمَّل إطلاقاً (انظر تحت)
    if (not final_text.strip()
            and config["mode"] in ("translate_en_ar", "rephrase_ar")):
        first_photo_msg = next((m for m in media_msgs if m.photo), None)
        if first_photo_msg:
            tmp_path = None
            try:
                tmp_path = await client.download_media(first_photo_msg, file=f"{DOWNLOAD_DIR}/")
                if tmp_path:
                    vision = call_gemini_vision(tmp_path, config["gemini_key"])
                    if vision["has_text"] and vision["caption"]:
                        final_text = vision["caption"]
            except Exception as e:
                print(f"⚠️ خطأ فحص نص الصورة — {config['name']}: {e}")
            finally:
                if tmp_path:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

    if config.get("add_link") and config.get("link"):
        link_text = config["link"]
        final_text = f"{final_text}\n\n{link_text}" if final_text else link_text

    try:
        if media_msgs:
            # نرسل الوسائط بالإشارة المباشرة لملفها على سيرفرات تلجرام — بدون تحميل
            # أو إعادة رفع محلياً. هذا يشتغل حتى لفيديوهات/ملفات بأحجام كبيرة جداً
            # (جيجابايتات) بدون ما يمر أي بايت عبر GitHub Actions، وتلقائياً ما يظهر
            # اسم/قناة المرسل الأصلي لأنها رسالة جديدة مو Forward.
            to_send = media_msgs[0].media if len(media_msgs) == 1 else [m.media for m in media_msgs]
            try:
                await client.send_file(config["target"], to_send,
                                        caption=final_text or None, parse_mode="html")
                print(f"✅ نُشر (وسائط) — {config['name']}")
            except Exception as e:
                print(f"⚠️ فشل النسخ المباشر، محاولة تحميل احتياطي — {config['name']}: {e}")
                # احتياط نادر: لو فشلت الإشارة المباشرة (مثلاً ملف قديم جداً)، جرّب تحميل حقيقي
                files = []
                for m in media_msgs:
                    try:
                        path = await client.download_media(m, file=f"{DOWNLOAD_DIR}/")
                        if path:
                            files.append(path)
                    except Exception as e2:
                        print(f"⚠️ فشل التحميل الاحتياطي لملف — {config['name']}: {e2}")
                if files:
                    to_send2 = files[0] if len(files) == 1 else files
                    await client.send_file(config["target"], to_send2,
                                            caption=final_text or None, parse_mode="html")
                    for f in files:
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                    print(f"✅ نُشر (وسائط، تحميل احتياطي) — {config['name']}")
                elif final_text:
                    await client.send_message(config["target"], final_text,
                                               parse_mode="html", link_preview=False)
                    print(f"⚠️ نُشر نص فقط (فشل النسخ والتحميل) — {config['name']}")
                else:
                    print(f"❌ تم تجاهل منشور — فشل كل محاولات نشر الوسائط — {config['name']}")
        elif final_text:
            await client.send_message(config["target"], final_text,
                                       parse_mode="html", link_preview=False)
            print(f"✅ نُشر (نص) — {config['name']}")
    except Exception as e:
        print(f"❌ خطأ بالنشر — {config['name']}: {e}")

# ==================== معالجة الرسائل الفائتة (بولينغ) ====================

async def catch_up_channel(source_id):
    config = CHANNELS.get(source_id, {})
    # استخدم اليوزرنيم العام إذا موجود — يتحل حتى لو الحساب مو منضم للقناة.
    # الـ ID الرقمي وحده يفشل أحياناً لو الحساب ما "شاف" القناة من قبل (access_hash غير محفوظ).
    entity_ref = config.get("source_username") or source_id

    key = str(source_id)
    last_id = state.get(key, 0)

    if last_id == 0:
        latest = await client.get_messages(entity_ref, limit=1)
        if latest:
            last_id = max(latest[0].id - 5, 0)
        state[key] = last_id
        save_state(state)

    messages = await client.get_messages(entity_ref, min_id=last_id, limit=200)
    if not messages:
        return

    messages = list(reversed(messages))  # من الأقدم للأحدث
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.grouped_id:
            group = [m for m in messages if m.grouped_id == msg.grouped_id]
            group.sort(key=lambda m: m.id)
            await process_batch(source_id, group)
            new_last = group[-1].id
            i += len(group)
        else:
            await process_batch(source_id, [msg])
            new_last = msg.id
            i += 1
        state[key] = new_last
        save_state(state)

# ==================== التشغيل الرئيسي ====================
# تشغيلة واحدة قصيرة: تتصل، تفحص كل قناة مرة واحدة، تحفظ الحالة، وتطفي.
# لا يوجد أي استماع مباشر أو حلقة انتظار — هذا هو الفرق الجوهري عن النسخة السابقة.

async def main():
    await client.start()
    print("🚀 بدء فحص القنوات الثمانية (بولينغ)...")

    for source_id, cfg in CHANNELS.items():
        print(f"⏳ فحص — {cfg['name']}")
        try:
            await catch_up_channel(source_id)
        except Exception as e:
            print(f"❌ فشل فحص قناة كامل (تخطّي — البقية بتكمل): {cfg['name']} — {e}")

    await client.disconnect()
    commit_state()
    print("✅ انتهت التشغيلة — الاتصال مقفول.")

if __name__ == "__main__":
    asyncio.run(main())
