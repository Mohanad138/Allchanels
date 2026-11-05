# -*- coding: utf-8 -*-
"""
بوت الريلي الموحد — حساب شخصي واحد (Telethon) يفحص 8 قنوات مصدر كل تشغيل
(بولينغ، بدون استماع مباشر مستمر) وينشر الجديد بـ 8 قنوات هدف.
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

CHANNELS = {
    -1001344466508: {
        "name": "فابريزيو رومانو بالعربي",
        "target": -1002015818715,
        "mode": "fabrizio_special",
        "gemini_key": GEMINI_KEY_FABRIZ,
        "source_username": "@FabrizioRomanoTG",
        "skip_if_video": True,
        "skip_if_youtube": True,
        "skip_if_play_button": True,
    },
    -1009003922421: {
        "name": "كأس آسيا",
        "target": "@AsiaCup24",
        "mode": "copy",
        "gemini_key": GEMINI_KEY_AFLAM,
        "source_username": "@sportts_iq",
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
    -1009001498076: {
        "name": "الانترنت المجاني في العراق",
        "target": "@FreeNet24IQ",
        "mode": "rephrase_ar",
        "gemini_key": GEMINI_KEY_TECH,
        "source_username": "@Free_Neet10",
        "add_link": True,
        "link": "@FreeNet24IQ",
        "extra_rules": "أعد صياغة النص بشكل متناسق وبسيط وواضح، بدون حذف أي معلومة فعلية "
                       "(أسماء باقات، أسعار، خطوات، إلخ).",
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
        "topic_filter": "أخبار ومعلومات تخص الطلبة والدراسة والتعليم فقط، وتفيد الطالب فعلاً — "
                        "نتائج، تعليمات، مواعيد، قبول، منح، إلخ. إذا كان المنشور رسالة محوّلة "
                        "(Forwarded) من قناة ثانية ومحتواها لا يحمل خبر أو معلومة حقيقية تفيد "
                        "الطالب (مجرد ترويج، دردشة، محتوى عام بلا فائدة تعليمية مباشرة)، اعتبرها "
                        "غير متعلقة (is_relevant=false) حتى لو ذُكرت كلمة متعلقة بالدراسة عرضياً.",
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
# تم تعديل التعليق ليتطابق مع القيمة الفعلية
DUP_SIMILARITY_THRESHOLD = 0.82 

def is_duplicate_content(source_id, text):
    """يقارن النص الجديد بآخر 15 منشور بنفس القناة — لو فيه تشابه 82%+ يُعتبر تكرار"""
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
        subprocess.run(["git", "commit", "-m", "update relay state"], check=False, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False, capture_output=True)
        push_res = subprocess.run(["git", "push"], check=False, capture_output=True, text=True)
        if push_res.returncode != 0:
            print(f"⚠️ فشل رفع الحالة لـ GitHub: {push_res.stderr}")
    except Exception as e:
        print(f"⚠️ git commit error: {e}")

# ==================== تنظيف النص ====================

def _is_small_thumbnail_photo(photo, abs_threshold=250, square_size_cap=800):
    try:
        dims = [(getattr(s, "w", 0), getattr(s, "h", 0)) for s in photo.sizes if hasattr(s, "w")]
        if not dims:
            return False
        max_w = max(w for w, _ in dims)
        max_h = max(h for _, h in dims)
        if max_w < abs_threshold and max_h < abs_threshold:
            return True
        if max_w > 0 and max_h > 0:
            ratio = max_w / max_h
            if 0.85 <= ratio <= 1.18 and max(max_w, max_h) <= square_size_cap:
                return True
        return False
    except Exception:
        return False

def _message_has_any_video(m):
    media = m.media
    if isinstance(media, MessageMediaDocument):
        return bool(m.video) or bool(getattr(m, "gif", None))
    if isinstance(media, MessageMediaWebPage):
        wp = getattr(media, "webpage", None)
        if wp is None:
            return False
        if getattr(wp, "duration", None):
            return True
        wtype = str(getattr(wp, "type", "") or "").lower()
        if "video" in wtype or "gif" in wtype:
            return True
        doc = getattr(wp, "document", None)
        if doc is not None and str(getattr(doc, "mime_type", "")).startswith(("video/", "image/gif")):
            return True
    return False

def _is_usable_media_msg(m):
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
    if isinstance(m.media, MessageMediaWebPage):
        return m.photo if m.photo else None
    return m.media

def extract_hidden_link_urls(message, source_username=None):
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
            # أمان: تجاهل روابط الدعوات المخفية (t.me/+)
            if re.search(r't\.me/\+', url, re.IGNORECASE):
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
        cleaned = re.sub(r'(https?://)?t\.me/\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'https?://t\.co/\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?i)forwarded from.*', '', cleaned)
    cleaned = re.sub(r'(?i)read\s*more\.?\s*$', '', cleaned.rstrip())
    cleaned = re.sub(r'اقرأ\s*المزيد\.?\s*$', '', cleaned.rstrip())
    cleaned = re.sub(r'أعيد التوجيه من.*', '', cleaned)
    
    # إزالة التوقيعات المزعجة
    cleaned = re.sub(r'^.*نيمار\s*ابن\s*الانبار.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'^.*@?IRAQEDU.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()
    lines = cleaned.split('\n')
    while lines and not re.search(r'[A-Za-z\u0600-\u06FF0-9]', lines[-1]):
        lines.pop()
    cleaned = '\n'.join(lines).rstrip()
    return cleaned

# تم إصلاح الهمزة هنا
SHARE_PHRASE_RE = re.compile(r'شارك\s+(القناة|المنشور)\s+مع\s+[اأ]?صدقائ?ك?', re.IGNORECASE)

def insert_link_after_share_phrase(text, link_text):
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
    if not text:
        return False
    return bool(re.search(r'اضغط\s*هنا.{0,15}(للمشاهدة|لمشاهدة|مشاهدة)', text))

def contains_youtube_link(text):
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
                time.sleep(2 ** attempt)
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
                time.sleep(2 ** attempt)
                continue
            raise
        except Exception:
            raise
    if last_error:
        raise last_error
    raise RuntimeError("gemini call failed after retries")

def call_gemini_vision(image_path, api_key, max_retries=3):
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
- إذا يوجد نص، لخّصه وأعد صياغته كتعليق قصير طبيعي بالعربية الفصحى.
- إذا لا يوجد أي نص، اجعل has_text=false و caption فارغة.
أعد النتيجة بصيغة JSON فقط: {"has_text": true/false, "caption": "النص"}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": img_b64}}, {"text": prompt}]}]}

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
            return {"has_text": bool(result.get("has_text", False)), "caption": (result.get("caption") or "").strip()}
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return {"has_text": False, "caption": ""}
    return {"has_text": False, "caption": ""}

def check_image_has_play_button(image_path, api_key, max_retries=3):
    if not api_key:
        return False
    try:
        import base64
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
    except Exception:
        return False

    ext = image_path.lower().rsplit(".", 1)[-1]
    mime = "image/png" if ext == "png" else "image/jpeg"
    prompt = """هل يوجد في هذه الصورة زر تشغيل فيديو (رمز مثلث ▶ غالباً داخل دائرة أو مربع)؟
- إذا نعم has_play_button=true، وإذا لا false.
- أعد النتيجة بصيغة JSON فقط: {"has_play_button": true/false}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": img_b64}}, {"text": prompt}]}]}

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
            return bool(json.loads(raw).get("has_play_button", False))
        except Exception:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False
    return False

def check_is_ad(text, api_key):
    prompt = f"""حدد فقط إذا كان النص التالي إعلاناً مدفوعاً أو محتوى ترويجياً تجارياً.
اعتبره إعلاناً (is_ad=true) لو فيه أي من هذي العلامات:
- ترويج مباشر لمنتج، تطبيق، خدمة، قناة/حساب آخر، أو رعاية مدفوعة
- سعر، خصم، أو عرض
- دعوة صريحة للتسجيل أو الحجز مقابل مبلغ
- رقم تواصل "للحجز" بخصوص خدمة مدفوعة
أي خبر عادي — حتى لو ذكر جوائز أو مسابقات — ليس إعلاناً، اعتبره is_ad=false.
النص:
{text}
أعد النتيجة بصيغة JSON فقط: {{"is_ad": true/false}}"""
    try:
        return bool(call_gemini(prompt, api_key).get("is_ad", False))
    except Exception:
        return False

def check_is_relevant_topic(text, api_key, topic_description):
    prompt = f"""حدد فقط إذا كان النص التالي يتعلق بهذا الموضوع: {topic_description}
- إذا كان يتعلق is_relevant=true، وإذا لا false.
النص:
{text}
أعد النتيجة بصيغة JSON فقط: {{"is_relevant": true/false}}"""
    try:
        return bool(call_gemini(prompt, api_key).get("is_relevant", False))
    except Exception:
        # في حال فشل الاتصال، نعتمد النشر كإجراء احتياطي
        return True 

def call_translate(text, api_key, extra_rules=None):
    extra = f"\n{extra_rules}\n" if extra_rules else ""
    prompt = f"""أنت كاتب عربي محترف. أعد صياغة النص التالي (بأي لغة) بالعربية بالكامل.
**ممنوع الترجمة الحرفية.** اكتبه بأسلوبك كأنك عربي شاهدت الخبر.
تجاهل أي روابط. إذا كان إعلاناً تجارياً صريحاً اجعل should_post = false، عدا ذلك انشره.
{extra}
النص:
{text}
أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "الترجمة"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return {"should_post": bool(result.get("should_post", True)), "text": (result.get("text") or text).strip()}
    except Exception:
        return {"should_post": False, "text": ""}

def call_rephrase(text, api_key, extra_rules=None):
    extra = f"\n{extra_rules}\n" if extra_rules else ""
    prompt = f"""أنت محرر صحفي عراقي. أعد صياغة النص بأسلوب صحفي احترافي واضح ومختصر.
تجاهل أي روابط. إذا كان إعلاناً تجارياً اجعل should_post = false، عدا ذلك انشره.
{extra}
النص:
{text}
أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "النص المعاد صياغته"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return {"should_post": bool(result.get("should_post", True)), "text": (result.get("text") or text).strip()}
    except Exception:
        return {"should_post": True, "text": text}

def call_match_links(text, api_key):
    prompt = f"""أنت تنسّق منشورات قناة تبث روابط مشاهدة مباريات كرة القدم. حوّل النص التالي للقالب:
- اسم_الفريق × اسم_الفريق (بدون إيموجي)
- ⏰ | الساعة مساءً بتوقيت مكة المكرمة
- 🎤 | الاسم
- 🔗 | رابط المباراة: (أو رابط المباريات:)
- الملاحظة المعتادة.
النص:
{text}
أعد النتيجة بصيغة JSON فقط: {{"text": "النص المنسق"}}"""
    try:
        return (call_gemini(prompt, api_key).get("text") or "").strip()
    except Exception:
        return ""

def call_fabrizio(text, api_key):
    # تم تعديل البرومبت هنا ليكون بصيغة فابريزيو المتكلم وبأسلوب احترافي
    prompt = f"""أنت محرر لصفحة عربية تنقل كل منشورات حساب فابريزيو رومانو الرسمي بالعربية.
معايير النشر: انشر أي خبر كروي ملموس (صفقات، إصابات، تصريحات مهمة، جوائز، Here we go).
اجعل should_post = false فقط للإعلانات المدفوعة، أو التشويق بلا معلومة، أو الترويج لبرنامجه.
الترجمة (إذا should_post = true):
- **صيغة المتكلم:** هذي القناة تنطق بلسان فابريزيو رومانو نفسه (أنا أؤكد، أنا أفهم). ممنوع تحويلها لصيغة الغائب (قال فابريزيو).
- أعد صياغة الخبر بأسلوب محرر رياضي عربي محترف، بأسلوب طبيعي جداً كأنه مكتوب بالعربية من الأصل، وليس ترجمة حرفية.
- أبقِ عبارة "Here we go" بالإنجليزية.
- لا تضع أي روابط نهائياً.
النص:
{text}
أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "النص المُعالج"}}"""
    try:
        result = call_gemini(prompt, api_key)
        out_text = (result.get("text") or text).strip()
        out_text = re.sub(r'https?://\S+', '', out_text)
        out_text = re.sub(r'\n{3,}', '\n\n', out_text).strip()
        return {"should_post": bool(result.get("should_post", True)), "text": out_text}
    except Exception as e:
        print(f"❌ خطأ معالجة فابريزيو: {e}")
        return {"should_post": False, "text": ""}

async def apply_processing(config, text):
    mode = config["mode"]
    if not text:
        return True, ""
    if not config.get("gemini_key"):
        return False, ""

    if mode == "copy":
        if check_is_ad(text, config["gemini_key"]):
            return False, text
        if config.get("topic_filter") and not check_is_relevant_topic(text, config["gemini_key"], config["topic_filter"]):
            return False, text
        return True, text
    if mode == "match_links":
        res = call_match_links(text, config["gemini_key"])
        return bool(res), res
    if mode == "translate_en_ar":
        res = call_translate(text, config["gemini_key"], config.get("extra_rules"))
        return res["should_post"], res["text"]
    if mode == "rephrase_ar":
        res = call_rephrase(text, config["gemini_key"], config.get("extra_rules"))
        return res["should_post"], res["text"]
    if mode == "fabrizio_special":
        force_post = bool(re.search(r'here\s*we\s*go', text, re.IGNORECASE))
        res = call_fabrizio(text, config["gemini_key"])
        should_post = bool(res["text"]) and (res["should_post"] or force_post)
        return should_post, res["text"]
    return True, text

# ==================== معالجة ونشر دفعة رسائل ====================

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
        print(f"⏭️  تم تجاهل — {config['name']} (اضغط هنا للمشاهدة)")
        return

    hidden_links = extract_hidden_link_urls(text_msg, config.get("source_username"))
    if hidden_links:
        raw_text = (raw_text.rstrip() + "\n\n" + "\n".join(hidden_links)) if raw_text else "\n".join(hidden_links)

    strip_tg_links = config["mode"] != "match_links"
    cleaned = clean_text(raw_text, config.get("source_username"), strip_telegram_links=strip_tg_links)

    if is_duplicate_content(source_id, cleaned):
        print(f"⏭️  تم تجاهل — {config['name']} (مشابه لمنشور سابق)")
        return

    should_post, final_text = await apply_processing(config, cleaned)

    if not should_post:
        print(f"⏭️  تم تجاهل — {config['name']} (إعلان أو غير مهم)")
        return

    record_published_text(source_id, cleaned)
    media_msgs = [m for m in messages if _is_usable_media_msg(m)]
    force_post_here_we_go = bool(re.search(r'here\s*we\s*go', raw_text, re.IGNORECASE))

    if config.get("skip_if_video") and any(_message_has_any_video(m) for m in messages) and not force_post_here_we_go:
        print(f"⏭️  تم تجاهل — {config['name']} (فيديو مرفق)")
        return
    if config.get("skip_if_youtube") and contains_youtube_link(raw_text) and not force_post_here_we_go:
        print(f"⏭️  تم تجاهل — {config['name']} (رابط يوتيوب)")
        return

    if config.get("skip_if_play_button") and not force_post_here_we_go:
        first_photo_msg = next((m for m in media_msgs if m.photo), None)
        if first_photo_msg:
            tmp_path = None
            has_play = False
            try:
                tmp_path = await client.download_media(first_photo_msg, file=f"{DOWNLOAD_DIR}/")
                if tmp_path:
                    has_play = check_image_has_play_button(tmp_path, config["gemini_key"])
            except Exception:
                pass
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            if has_play:
                print(f"⏭️  تم تجاهل — {config['name']} (غلاف فيديو)")
                return

    if (not final_text.strip() and config["mode"] in ("translate_en_ar", "rephrase_ar")):
        first_photo_msg = next((m for m in media_msgs if m.photo), None)
        if first_photo_msg:
            tmp_path = None
            try:
                tmp_path = await client.download_media(first_photo_msg, file=f"{DOWNLOAD_DIR}/")
                if tmp_path:
                    vision = call_gemini_vision(tmp_path, config["gemini_key"])
                    if vision["has_text"] and vision["caption"]:
                        final_text = vision["caption"]
            except Exception:
                pass
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

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
            # تجهيز الوسائط، مع استبعاد أي None قد ينتج من معاينة رابط بدون صورة
            valid_payloads = [_media_payload(m) for m in media_msgs if _media_payload(m) is not None]
            if not valid_payloads:
                if final_text:
                    await client.send_message(config["target"], final_text, parse_mode="html", link_preview=False)
                    print(f"✅ نُشر نص فقط (وسائط غير صالحة) — {config['name']}")
                return
                
            to_send = valid_payloads[0] if len(valid_payloads) == 1 else valid_payloads
            try:
                await client.send_file(config["target"], to_send, caption=final_text or None, parse_mode="html")
                print(f"✅ نُشر (وسائط) — {config['name']}")
            except Exception as e:
                print(f"⚠️ فشل النسخ المباشر — {config['name']}: {e}")
                files = []
                for m in media_msgs:
                    try:
                        path = await client.download_media(m, file=f"{DOWNLOAD_DIR}/")
                        if path: files.append(path)
                    except Exception: pass
                if files:
                    to_send2 = files[0] if len(files) == 1 else files
                    await client.send_file(config["target"], to_send2, caption=final_text or None, parse_mode="html")
                    for f in files:
                        try: os.remove(f)
                        except OSError: pass
                    print(f"✅ نُشر (وسائط، تحميل احتياطي) — {config['name']}")
                elif final_text:
                    await client.send_message(config["target"], final_text, parse_mode="html", link_preview=False)
                    print(f"⚠️ نُشر نص فقط — {config['name']}")
        elif final_text:
            await client.send_message(config["target"], final_text, parse_mode="html", link_preview=False)
            print(f"✅ نُشر (نص) — {config['name']}")
    except Exception as e:
        print(f"❌ خطأ بالنشر — {config['name']}: {e}")

# ==================== معالجة الرسائل الفائتة (بولينغ) ====================

async def catch_up_channel(source_id):
    config = CHANNELS.get(source_id, {})
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

    messages = list(reversed(messages))
    
    # إصلاح خلل التكرار هنا:
    processed_ids = set()
    for msg in messages:
        if msg.id in processed_ids:
            continue

        if msg.grouped_id:
            group = [m for m in messages if m.grouped_id == msg.grouped_id and m.id not in processed_ids]
            group.sort(key=lambda m: m.id)
            await process_batch(source_id, group)
            processed_ids.update(m.id for m in group)
            new_last = group[-1].id
        else:
            await process_batch(source_id, [msg])
            processed_ids.add(msg.id)
            new_last = msg.id
            
        state[key] = new_last
        save_state(state)

# ==================== التشغيل الرئيسي ====================

async def main():
    await client.start()
    print("🚀 بدء فحص القنوات (بولينغ)...")

    for source_id, cfg in CHANNELS.items():
        print(f"⏳ فحص — {cfg['name']}")
        try:
            await catch_up_channel(source_id)
        except Exception as e:
            print(f"❌ فشل فحص قناة كامل: {cfg['name']} — {e}")

    await client.disconnect()
    
    # تم نقل الحفظ ليكون مرة واحدة في النهاية لتحسين الأداء
    commit_state()
    print("✅ انتهت التشغيلة — الاتصال مقفول.")

if __name__ == "__main__":
    asyncio.run(main())
