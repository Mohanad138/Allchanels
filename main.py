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
import difflib

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (MessageEntityTextUrl, MessageMediaPhoto,
                                MessageMediaDocument, MessageMediaWebPage)
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
        "skip_if_video": True,
        "skip_if_youtube": True,
    },
    -1009003922421: {
        "name": "كأس آسيا",
        "target": "@AsiaCup24",
        "mode": "copy",
        "gemini_key": GEMINI_KEY_AFLAM,
        "source_username": "@sportts_iq",  # امبراطورية الاخبار العراقية
        "topic_filter": "منشورات تخص كأس آسيا لكرة القدم (AFC Asian Cup) فقط — مباريات، نتائج، "
                         "تشكيلات، تأهل، منتخبات مشاركة. أي خبر رياضي أو غير رياضي آخر غير متعلق "
                         "بكأس آسيا تحديداً يُعتبر غير متعلق ويُتجاهل.",
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
    -1009001498075: {
        "name": "الذكاء الاصطناعي",
        "target": "@AInewsAR1",
        "mode": "translate_en_ar",
        "gemini_key": GEMINI_KEY_TECH,
        "source_username": "@aipost",
        "add_link": True,
        "link": "@AInewsAR1",
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
        "topic_filter": "أخبار ومعلومات تخص الطلبة والدراسة والتعليم فقط",
        "link_after_share_phrase": True,
    },
    -1009003946451: {
        "name": "تسريبات GTA 6",
        "target": -1002218686576,
        "mode": "translate_en_ar",
        "gemini_key": GEMINI_KEY_GTA,
        "source_username": "@GTA6NewsEN",
        "add_link": True,
        "link": "@GTA6AR",
        "extra_rules": "إذا ورد أي سعر بالروبل الروسي بالنص، حوّله لمكافئه التقريبي بالدولار الأمريكي "
                       "واكتبه بالدولار فقط بدل الروبل (استخدم تقريب تقريبي لسعر الصرف الحالي، وأشر أنه تقريبي "
                       "بكلمة \"حوالي\"). لا تكتب الروبل إطلاقاً بالنص النهائي.",
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

DUP_HISTORY_SIZE = 15
DUP_SIMILARITY_THRESHOLD = 0.80

def is_duplicate_content(source_id, text):
    """يقارن النص الجديد بآخر 15 منشور بنفس القناة — لو فيه تشابه 85%+ يُعتبر تكرار
    (يغطي حالات إعادة النشر بصياغة شبه مطابقة، مو بس تطابق حرفي)."""
    if not text or not text.strip():
        return False
    key = str(source_id)
    recent = state.setdefault("recent_texts", {}).get(key, [])
    norm = re.sub(r'\s+', ' ', text).strip().lower()
    for prev in recent:
        if difflib.SequenceMatcher(None, norm, prev).ratio() >= DUP_SIMILARITY_THRESHOLD:
            return True
    return False

def record_published_text(source_id, text):
    if not text or not text.strip():
        return
    key = str(source_id)
    norm = re.sub(r'\s+', ' ', text).strip().lower()
    bucket = state.setdefault("recent_texts", {}).setdefault(key, [])
    bucket.append(norm)
    state["recent_texts"][key] = bucket[-DUP_HISTORY_SIZE:]
    save_state(state)

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

def _is_small_thumbnail_photo(photo, threshold=250):
    """يحدد إذا كانت الصورة 'مصغّرة' (زي أفاتار حساب بمعاينة تغريدة مقتبسة) بدل صورة محتوى
    حقيقية — بفحص أبعادها الفعلية. أي بُعد أكبر من threshold بكسل يُعتبر صورة محتوى حقيقية."""
    try:
        dims = [(getattr(s, "w", 0), getattr(s, "h", 0)) for s in photo.sizes if hasattr(s, "w")]
        if not dims:
            return False  # ما نقدر نتأكد من الحجم — الأسلم نعتبرها صورة حقيقية
        max_w = max(w for w, _ in dims)
        max_h = max(h for _, h in dims)
        return max_w < threshold and max_h < threshold
    except Exception:
        return False


def _message_has_any_video(m):
    """يفحص وجود فيديو بالرسالة بأي شكل — فيديو مرفق حقيقي (MessageMediaDocument) أو فيديو
    مضمّن داخل معاينة رابط تغريدة (MessageMediaWebPage). يُستخدم فقط لقرار 'استبعد المنشور
    لأنه فيديو'، بغض النظر هل الفيديو هذا أصلاً داخل قائمة الوسائط القابلة للنشر أو لا —
    لأن فيديو معاينة الرابط ما نقدر ننشره، لكن لازم نعرف بوجوده عشان نستبعد المنشور."""
    media = m.media
    if isinstance(media, MessageMediaDocument):
        return bool(m.video)
    if isinstance(media, MessageMediaWebPage):
        wp = getattr(media, "webpage", None)
        if wp is None:
            return False
        if getattr(wp, "type", None) == "video":
            return True
        doc = getattr(wp, "document", None)
        if doc is not None and str(getattr(doc, "mime_type", "")).startswith("video/"):
            return True
    return False


def _is_usable_media_msg(m):
    """هل هذي الرسالة فيها وسائط حقيقية تستاهل تُنشر؟ يستثني صور معاينة الرابط الصغيرة
    (أفاتار حساب بمعاينة تغريدة مقتبسة) بس يبقي الصور الحقيقية حتى لو جايه من نفس آلية
    المعاينة (زي صورة لاعب مرفقة بتغريدة أصلية)."""
    media = m.media
    if isinstance(media, (MessageMediaPhoto, MessageMediaDocument)):
        return True
    if isinstance(media, MessageMediaWebPage):
        wp = getattr(media, "webpage", None)
        photo = getattr(wp, "photo", None)
        if photo and not _is_small_thumbnail_photo(photo):
            return True
    return False


def _media_payload(m):
    """الكائن المناسب لتمريره لـ send_file — Photo الحقيقي المستخرج لو كانت الوسائط من
    نوع معاينة رابط (MessageMediaWebPage)، أو m.media مباشرة لباقي الحالات."""
    if isinstance(m.media, MessageMediaWebPage):
        return m.photo
    return m.media


def extract_hidden_link_urls(message, source_username=None):
    """يرجع روابط 'مخفية' خلف نص مقنّع زي 'اضغط هنا للمشاهدة' — نص الرسالة العادي ما يحتوي
    الرابط الحقيقي أصلاً، فبدون هذا الاستخراج يضيع الرابط بالكامل عند النشر.
    يتجاهل رابط قناة المصدر نفسها، وأي رابط خلف نص "Read more" أو "اقرأ المزيد"
    (رابط لمقال بموقع المصدر — مو محتوى نحتاج ننقله)."""
    if not message or not getattr(message, "entities", None):
        return []
    handle = (source_username or "").lstrip("@").lower()
    skip_anchor_re = re.compile(r'read\s*more|اقرأ\s*المزيد', re.IGNORECASE)
    urls = []
    try:
        for entity, anchor_text in message.get_entities_text(MessageEntityTextUrl):
            url = entity.url
            if handle and f"t.me/{handle}".lower() in url.lower():
                continue
            if skip_anchor_re.search(anchor_text or ""):
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
    # روابط t.co (اختصار تويتر/X لمعاينة الصورة أو التغريدة الأصلية) — ما تحمل أي محتوى
    # مفيد للقارئ العربي، تُحذف دايماً من كل القنوات
    cleaned = re.sub(r'https?://t\.co/\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?i)forwarded from.*', '', cleaned)
    cleaned = re.sub(r'(?i)read\s*more\.?\s*$', '', cleaned.rstrip())
    cleaned = re.sub(r'اقرأ\s*المزيد\.?\s*$', '', cleaned.rstrip())
    cleaned = re.sub(r'أعيد التوجيه من.*', '', cleaned)
    # حذف سطر التوقيع/الشكر اللي تضيفه قنوات ثانية بمنشورها (زي "نيمار ابن الانبار || @IRAQEDU")
    # — يشتغل بكل القنوات، على أي سطر يحتوي هذا التوقيع بغض النظر عن الصيغة بالضبط
    cleaned = re.sub(r'^.*نيمار\s*ابن\s*الانبار.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'^.*@?IRAQEDU.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    # احذف أي سطر "زخرفي" فاضي من المحتوى الحقيقي (رموز/إيموجي بس، بلا حرف أو رقم) من نهاية
    # النص — عشان لمّا نضيف رابطنا بالنهاية يطلع مباشرة تحت آخر جملة حقيقية (زي "شارك المنشور
    # مع اصدقاءك:")، مو تحت سطر زخرفي فاضي كان المصدر حاطه
    lines = cleaned.split('\n')
    while lines and not re.search(r'[A-Za-z\u0600-\u06FF0-9]', lines[-1]):
        lines.pop()
    cleaned = '\n'.join(lines).rstrip()
    return cleaned


SHARE_PHRASE_RE = re.compile(r'شارك\s+(القناة|المنشور)\s+مع\s+اصدقائ?ك', re.IGNORECASE)

def insert_link_after_share_phrase(text, link_text):
    """لو النص فيه جملة 'شارك القناة/المنشور مع اصدقائك'، يرجع النص بعد ما يحط الرابط
    مباشرة تحت هذي الجملة (مو بآخر النص). لو الجملة مو موجودة يرجع None عشان المتصل
    يستخدم الأسلوب الافتراضي (إضافة الرابط بالنهاية)."""
    match = SHARE_PHRASE_RE.search(text)
    if not match:
        return None
    newline_idx = text.find('\n', match.end())
    if newline_idx == -1:
        return text.rstrip() + f"\n{link_text}"
    before = text[:newline_idx]
    after = text[newline_idx:]
    return before + f"\n{link_text}" + after


def contains_click_here_phrase(text):
    """يفحص وجود عبارة 'اضغط هنا للمشاهدة' (وتنويعاتها) — منشورات بهذي الصيغة تُستبعد
    بالكامل بناءً على طلب المستخدم (كثير منها طلع منشورات احتيال/تصيّد)."""
    if not text:
        return False
    return bool(re.search(r'اضغط\s*هنا.{0,15}(للمشاهدة|لمشاهدة|مشاهدة)', text))


def contains_youtube_link(text):
    """يفحص وجود رابط يوتيوب (youtube.com أو youtu.be) — منشورات فيها رابط فيديو يوتيوب
    تُستبعد بقنوات معيّنة (زي فابريزيو) لأنها عملياً إعلان لفيديو، مو خبر بحد ذاته."""
    if not text:
        return False
    return bool(re.search(r'(youtube\.com|youtu\.be)', text, re.IGNORECASE))

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

def check_is_relevant_topic(text, api_key, topic_description):
    prompt = f"""حدد فقط إذا كان النص التالي يتعلق بهذا الموضوع: {topic_description}

اعتبره متعلق (is_relevant=true) لو كان عن: نتائج دراسية، تعليمات وزارية/جامعية، مواعيد امتحانات أو
تسجيل أو قبول، مناهج، منح دراسية، أو أي خبر رسمي يخص الطلبة والمؤسسات التعليمية مباشرة.
اعتبره غير متعلق (is_relevant=false) لو كان عن أي موضوع آخر (سياسة عامة، حوادث، رياضة، ترفيه،
اقتصاد عام غير تعليمي، إلخ) حتى لو مثير أو مهم، طالما مالها علاقة مباشرة بالدراسة/التعليم.
عند الشك اجعل is_relevant=false. لا تعدل النص إطلاقاً.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"is_relevant": true/false}}"""
    try:
        result = call_gemini(prompt, api_key)
        return bool(result.get("is_relevant", False))
    except Exception as e:
        print(f"⚠️ خطأ فحص الموضوع: {e}")
        return True  # عند فشل الفحص التقني، ننشر بدل ما نفقد منشور صحيح بسبب خطأ تقني


def call_translate(text, api_key, extra_rules=None):
    extra = f"\n{extra_rules}\n" if extra_rules else ""
    prompt = f"""أنت كاتب عربي محترف. أعد صياغة النص التالي (بأي لغة كان مكتوب — إنجليزي، روسي، أو غيرها) بالعربية بالكامل.
**ممنوع الترجمة الحرفية كلمة-بكلمة.** اكتبه وكأنك عربي شاهدت نفس الخبر وتكتبه لأول مرة بأسلوبك — غيّر ترتيب الجملة،
ادمج أو افصل الجمل، واستخدم تعابير عربية طبيعية شائعة بدل نقل التراكيب الأجنبية حرفياً.
تجاهل أي روابط أو إشارات لقناة المصدر. لا تضيف أي تعليق أو مقدمة من عندك.
إذا كان النص إعلاناً مدفوعاً أو محتوى ترويجياً تجارياً صريحاً (منتج، تطبيق، خدمة، رعاية مدفوعة) اجعل should_post = false.
أي خبر عادي — حتى لو ذكر جوائز أو مسابقات أو أحداث — ليس إعلاناً، انشره (should_post = true). عند الشك انشر.
{extra}
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

def call_rephrase(text, api_key, extra_rules=None):
    extra = f"\n{extra_rules}\n" if extra_rules else ""
    prompt = f"""أنت محرر صحفي عراقي. أعد صياغة النص التالي بأسلوب صحفي احترافي واضح ومختصر بالعربية.
تجاهل أي روابط أو إشارات لقناة المصدر. لا تضيف أي تعليق من عندك.
إذا كان النص إعلاناً مدفوعاً أو محتوى ترويجياً تجارياً صريحاً (منتج، تطبيق، خدمة، رعاية مدفوعة) اجعل should_post = false.
أي خبر عادي — حتى لو ذكر جوائز أو مسابقات أو أحداث — ليس إعلاناً، انشره (should_post = true). عند الشك انشر.
{extra}
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
- سطر كل مباراة: "اسم_الفريق × اسم_الفريق" بدون أي إيموجي إطلاقاً (بدون أعلام دول، بدون ⚽️، بدون 🆚 — استخدم علامة × فقط).
- سطر الوقت: "⏰ | الساعة مساءً بتوقيت مكة المكرمة" (اكتب "مكة المكرمة" نص صريح، بدون علم وبدون كلمة "الـ").
- سطر المعلّق: "🎤 | الاسم" (بدون تمديد حروف بالاسم).
- افصل بين كل مباراة والثانية بسطر فاضي.
- بعد آخر مباراة، سطر فاضي ثم سطر رابط الدعوة: إذا كانت مباراة واحدة بس بكل المنشور اكتب "🔗 | رابط المباراة:"،
  وإذا كانت أكثر من مباراة اكتب "🔗 | رابط المباريات:" — ثم رابط الدعوة (https://t.me/+...) بسطر لحاله.
- بعده سطر فاضي ثم (بدون أي إيموجي بالبداية): "ملاحظة: اضغط على الرابط ثم «انضمام»، وبعدها اضغط مرة أخرى على الرابط للدخول 💎"
  (إيموجي 💎 بالنهاية يبقى، بس احذف أي إيموجي كان بأول السطر زي ⬇️).
- لا تحذف أي مباراة. لا تضف أي تعليق من عندك.

مثال المدخل (مباراة واحدة):
🇬🇧 تشيلسي 🆚 بورنموث 🏴󠁧󠁢󠁥󠁮󠁧󠁿
⏰ | 5:00 مساءً بتوقيت 🇸🇦
🎤 | علي محمد علي

🔗 | رابط المباريات:
https://t.me/+5hBOma9vTGo4MWRk

⬇️ | ملاحظة: اضغط على الرابط ثم «انضمام»، وبعدها اضغط مرة أخرى على الرابط للدخول 💎

مثال المخرج المطلوب بالضبط:
تشيلسي × بورنموث
⏰ | 5:00 مساءً بتوقيت مكة المكرمة
🎤 | علي محمد علي

🔗 | رابط المباراة:
https://t.me/+5hBOma9vTGo4MWRk

ملاحظة: اضغط على الرابط ثم «انضمام»، وبعدها اضغط مرة أخرى على الرابط للدخول 💎

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
    prompt = f"""أنت محرر لصفحة عربية تنقل كل منشورات حساب فابريزيو رومانو الرسمي بالعربية.

معايير النشر:
- انشر كل منشور يصلك (should_post = true) بلا استثناء — انتقالات، صفقات، تجديد عقود، تغطية مباراة،
  إحصائيات، تصريحات، فيديوهات، أو أي خبر آخر مهما كان صغيراً أو هامشياً.
- الاستثناء الوحيد: إذا كان النص إعلاناً مدفوعاً أو محتوى ترويجياً تجارياً صريحاً (منتج، تطبيق، خدمة،
  رعاية مدفوعة) — عندها فقط اجعل should_post = false. أي خبر رياضي حقيقي ليس إعلاناً.
- استثناء ثاني: منشورات الترويج لبودكاست/برنامج فابريزيو نفسه (زي "New pod on"، ترويج لحلقة
  يوتيوب/بودكاست، دعوة للاستماع) تُعتبر ترويج ذاتي لمحتواه مو خبر مباشر — اجعلها should_post = false،
  حتى لو ذكرت أسماء لاعبين بشكل عابر ("talks"، "more to follow" بدون تفاصيل فعلية).
- استثناء ثالث: منشورات اللي جوهرها مقطع فيديو قصير مرفق من تويتر/X (لقطة، تكريم، هايلايت، "Watch:")
  وما فيها خبر مكتوب فعلي غير جملة قصيرة وصفية — اجعلها should_post = false. السبب: الفيديو المرفق
  عبارة عن معاينة رابط من X مو ملف تيليجرام حقيقي، والبوت ما يقدر ينشره، فينزل منشور فاضي بلا فائدة.
- أي منشور يحتوي على عبارة "Here we go" يُنشر دائماً بلا استثناء (حتى لو جاء ضمن منشور بودكاست أو فيديو).

الترجمة (فقط إذا should_post = true):
- **ممنوع الترجمة الحرفية كلمة-بكلمة.** أعد صياغة الخبر بالكامل بأسلوب محرر رياضي عربي محترف
  (زي أسلوب مواقع كووورة أو beIN SPORTS)، كأن الخبر كُتب أصلاً بالعربي وليس مترجماً.
  غيّر ترتيب الجملة، ادمج أو افصل الجمل، واستخدم تعابير رياضية عربية شائعة (زي "أكد مصدر مقرب"،
  "من المنتظر أن"، "بات قاب قوسين من") بدل الترجمة المباشرة للتراكيب الإنجليزية.
- **صيغة المتكلم:** هذي القناة تنطق بلسان فابريزيو رومانو نفسه (يعني "أنا فابريزيو" مو "فابريزيو قال").
  إذا كان النص الأصلي تصريح أو تغريدة لفابريزيو نفسه (بصيغة متكلم بالإنجليزي)، ترجمه بصيغة متكلم
  بالعربي أيضاً، **ممنوع** تحويله لصيغة الغائب (زي "يؤكد فابريزيو"، "ينفي فابريزيو"، "قال فابريزيو").
  مثال: "I can confirm..." تترجم "أؤكد لكم..." مو "يؤكد فابريزيو...". إذا كان النص أصلاً نقل كلام
  شخص ثالث (لاعب/مدرب) فابريزيو ينقله، خلي النقل بصيغة الغائب عادي ("قال اللاعب...") لأنه فعلاً نقل.
- أبقِ عبارة "Here we go" بالإنجليزية كما هي حرفياً بدون ترجمة إذا وردت بالنص.
- احذف أي رابط أو إشارة لقناة المصدر نفسها (بما فيها روابط تويتر/X وإشارات "Fabrizio Romano on X").
  **لا تُبقِ أي رابط إطلاقاً بالنص النهائي** — لا روابط يوتيوب، لا روابط تويتر/X، لا أي رابط آخر.
  لا تضيف تعليقات من عندك.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "النص المُعالج"}}"""
    try:
        result = call_gemini(prompt, api_key)
        out_text = (result.get("text") or text).strip()
        # ضمان كودي قطعي — بغض النظر عن التزام الذكاء الاصطناعي، نحذف أي رابط متبقي
        # (t.co، x.com/status، youtube، أي رابط آخر) من النص النهائي بهذي القناة تحديداً
        out_text = re.sub(r'https?://\S+', '', out_text)
        out_text = re.sub(r'\n{3,}', '\n\n', out_text).strip()
        return {"should_post": bool(result.get("should_post", True)),
                "text": out_text}
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
        if is_ad:
            return False, text
        topic_filter = config.get("topic_filter")
        if topic_filter:
            is_relevant = check_is_relevant_topic(text, config["gemini_key"], topic_filter)
            if not is_relevant:
                return False, text
        return True, text

    if mode == "match_links":
        result_text = call_match_links(text, config["gemini_key"])
        return bool(result_text), result_text

    if mode == "translate_en_ar":
        result = call_translate(text, config["gemini_key"], config.get("extra_rules"))
        return result["should_post"], result["text"]

    if mode == "rephrase_ar":
        result = call_rephrase(text, config["gemini_key"], config.get("extra_rules"))
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

    if is_duplicate_content(source_id, cleaned):
        print(f"⏭️  تم تجاهل منشور — {config['name']} (مشابه لمنشور سابق — تكرار)")
        return

    should_post, final_text = await apply_processing(config, cleaned)

    if not should_post:
        print(f"⏭️  تم تجاهل منشور — {config['name']} (إعلان أو غير مهم، أو خطأ تقني بالمعالجة — راجع الأسطر فوق)")
        return

    record_published_text(source_id, cleaned)

    # نتحقق من نوع الوسائط الفعلي (MessageMediaPhoto/Document حقيقي) بدل الخاصية العامة
    # m.photo/m.video، لأن تيليثون أحياناً يرجّع صورة "معاينة الرابط" (thumbnail لمعاينة
    # تغريدة مقتبسة) على إنها صورة حقيقية بالمنشور — وهذا يخلي البوت ينشرها غلط وكأنها محتوى.
    media_msgs = [m for m in messages if _is_usable_media_msg(m)]

    force_post_here_we_go = bool(re.search(r'here\s*we\s*go', raw_text, re.IGNORECASE))

    if config.get("skip_if_video") and any(_message_has_any_video(m) for m in messages) and not force_post_here_we_go:
        print(f"⏭️  تم تجاهل منشور — {config['name']} (يحتوي فيديو حقيقي مرفق — يُستبعد دائماً بهذي القناة)")
        return

    if config.get("skip_if_youtube") and contains_youtube_link(raw_text) and not force_post_here_we_go:
        print(f"⏭️  تم تجاهل منشور — {config['name']} (يحتوي رابط يوتيوب — منشور إعلان فيديو، يُستبعد دائماً)")
        return

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
        inserted = None
        if config.get("link_after_share_phrase") and final_text:
            inserted = insert_link_after_share_phrase(final_text, link_text)
        if inserted is not None:
            final_text = inserted
        else:
            final_text = f"{final_text}\n\n{link_text}" if final_text else link_text

    try:
        if media_msgs:
            # نرسل الوسائط بالإشارة المباشرة لملفها على سيرفرات تلجرام — بدون تحميل
            # أو إعادة رفع محلياً. هذا يشتغل حتى لفيديوهات/ملفات بأحجام كبيرة جداً
            # (جيجابايتات) بدون ما يمر أي بايت عبر GitHub Actions، وتلقائياً ما يظهر
            # اسم/قناة المرسل الأصلي لأنها رسالة جديدة مو Forward.
            to_send = _media_payload(media_msgs[0]) if len(media_msgs) == 1 else [_media_payload(m) for m in media_msgs]
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
        # حفظ ورفع الحالة لـ GitHub بعد كل قناة (مو بس بنهاية التشغيلة) — لو صارت مشكلة
        # أو انقطاع بمنتصف التشغيلة، القنوات اللي خلصت فعلاً تبقى حالتها محفوظة ومرفوعة،
        # وما تنعاد نفس المنشورات بالتشغيلة الجاية (هذا كان سبب محتمل لتكرار بعض المنشورات)
        commit_state()

    await client.disconnect()
    commit_state()
    print("✅ انتهت التشغيلة — الاتصال مقفول.")

if __name__ == "__main__":
    asyncio.run(main())
