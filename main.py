# -*- coding: utf-8 -*-
"""
بوت الريلي الموحد — حساب شخصي واحد (Telethon) يفحص 8 قنوات مصدر كل تشغيل
(بولينغ، بدون استماع مباشر مستمر) وينشر الجديد بـ 8 قنوات هدف.

هذه النسخة لا تفتح اتصال طويل الأمد ولا تستخدم events.NewMessage.
كل تشغيلة تفحص الرسائل الفائتة فقط ثم تُغلق الاتصال.
"""

import os
import re
import json
import hashlib
import difflib
import time
import asyncio
import subprocess

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageEntityTextUrl,
    MessageMediaPhoto,
    MessageMediaDocument,
    MessageMediaWebPage,
)
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

# ==================== إعدادات القنوات ====================

CHANNELS = {
    -1001344466508: {
        "name": "فابريزيو رومانو بالعربي",
        "target": -1002015818715,
        "mode": "fabrizio_special",
        "gemini_key": GEMINI_KEY_FABRIZ,
        "source_username": "@FabrizioRomanoTG",
        "skip_if_video": True,
    },
    -1009003922420: {
        "name": "سعر الدولار في العراق",
        "target": "@DollarIraq24",
        "mode": "rephrase_ar",
        "gemini_key": GEMINI_KEY_AFLAM,
        "source_username": "@dollariraqi",
        "add_link": True,
        "link": "@DollarIraq24",
        "extra_rules": "هذا منشور عن أسعار صرف الدولار والعملات. أعد صياغته بصورة مبسطة ومختصرة وواضحة "
                       "(سطر لكل سعر أو مدينة/سوق مثلاً)، لكن لا تحذف أي سعر أو رقم أو مدينة أو معلومة؛ "
                       "فقط بسّط الصياغة واحذف الزخرفة والتكرار. أبقِ الأرقام كما هي بدقة. "
                       "احذف أي ذكر أو يوزر أو رابط لقناة المصدر.",
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
                       "واكتبه بالدولار فقط بدل الروبل، مع الإشارة إلى أنه تقريبي بكلمة «حوالي». "
                       "لا تكتب الروبل إطلاقاً بالنص النهائي.",
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

# ==================== الحالة ومنع التكرار ====================

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
DUP_HISTORY_SIZE = 40
DUP_SIMILARITY_THRESHOLD = 0.90


def _normalise_for_dedupe(text):
    text = (text or "").lower()
    text = re.sub(r"https?://\S+|t\.me/\S+", " ", text)
    text = re.sub(r"[^\w\u0600-\u06FF]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _batch_fingerprint(messages, text):
    media_ids = []
    for msg in messages:
        media = getattr(msg, "media", None)
        photo = getattr(media, "photo", None)
        document = getattr(media, "document", None)
        obj = photo or document
        if obj is not None and getattr(obj, "id", None) is not None:
            media_ids.append(str(obj.id))
    normal = _normalise_for_dedupe(text)
    raw = normal + "|media:" + ",".join(sorted(media_ids))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), normal


def is_duplicate_content(source_id, messages, text):
    fingerprint, normal = _batch_fingerprint(messages, text)
    if not normal and fingerprint.endswith("|media:"):
        return False
    bucket = state.setdefault("dedupe_history", {}).setdefault(str(source_id), [])
    for item in bucket:
        if item.get("hash") == fingerprint:
            return True
        previous = item.get("text", "")
        if len(normal) >= 35 and len(previous) >= 35:
            if difflib.SequenceMatcher(None, normal, previous).ratio() >= DUP_SIMILARITY_THRESHOLD:
                return True
    return False


def record_published_content(source_id, messages, text):
    fingerprint, normal = _batch_fingerprint(messages, text)
    bucket = state.setdefault("dedupe_history", {}).setdefault(str(source_id), [])
    bucket.append({"hash": fingerprint, "text": normal, "time": int(time.time())})
    state["dedupe_history"][str(source_id)] = bucket[-DUP_HISTORY_SIZE:]
    save_state(state)


def commit_state():
    """يحفظ relay_state.json على GitHub بنهاية كل تشغيلة."""
    try:
        subprocess.run(["git", "add", STATE_FILE], check=False)
        subprocess.run(
            ["git", "commit", "-m", "update relay state"],
            check=False,
            capture_output=True,
        )
        subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            check=False,
            capture_output=True,
        )
        subprocess.run(["git", "push"], check=False, capture_output=True)
    except Exception as e:
        print(f"⚠️ git commit error: {e}")


# ==================== تنظيف النص والروابط ====================

def _is_small_thumbnail_photo(photo, threshold=250):
    try:
        dims = [
            (getattr(s, "w", 0), getattr(s, "h", 0))
            for s in photo.sizes if hasattr(s, "w")
        ]
        if not dims:
            return False
        max_w = max(w for w, _ in dims)
        max_h = max(h for _, h in dims)
        return max_w < threshold and max_h < threshold
    except Exception:
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
        return m.photo
    return m.media


def extract_hidden_link_urls(message, source_username=None):
    if not message or not getattr(message, "entities", None):
        return []
    handle = (source_username or "").lstrip("@").lower()
    skip_anchor_re = re.compile(r"read\s*more|اقرأ\s*المزيد", re.IGNORECASE)
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
    cleaned = text.replace("📊", "")
    if source_username:
        cleaned = re.sub(re.escape(source_username), "", cleaned, flags=re.IGNORECASE)
    if strip_telegram_links:
        cleaned = re.sub(r"(https?://)?t\.me/\S+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"https?://t\.co/\S+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?i)forwarded from.*", "", cleaned)
    cleaned = re.sub(r"(?i)read\s*more\.?\s*$", "", cleaned.rstrip())
    cleaned = re.sub(r"اقرأ\s*المزيد\.?\s*$", "", cleaned.rstrip())
    cleaned = re.sub(r"أعيد التوجيه من.*", "", cleaned)
    cleaned = re.sub(
        r"^.*نيمار\s*ابن\s*الانبار.*$",
        "",
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^.*@?IRAQEDU.*$",
        "",
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def contains_click_here_phrase(text):
    if not text:
        return False
    return bool(re.search(r"اضغط\s*هنا.{0,15}(للمشاهدة|لمشاهدة|مشاهدة)", text))


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
- إذا يوجد نص، لخّصه وأعد صياغته كتعليق قصير طبيعي بالعربية، وليس ترجمة حرفية، بدون وصف الصورة نفسها.
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
            return {
                "has_text": bool(result.get("has_text", False)),
                "caption": (result.get("caption") or "").strip(),
            }
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
- سعر، خصم، أو عرض
- دعوة صريحة للتسجيل أو الاشتراك أو الحجز بدورة/كورس/منتج مقابل مبلغ
- رقم أو معرّف تواصل للحجز أو الاستفسار عن خدمة أو دورة مدفوعة
- أسماء مدرّسين/مراكز خاصة مع ترويج لدوراتهم

أي خبر عادي إخباري، حتى لو ذكر جوائز أو مسابقات أو إعلانات رسمية، بدون سعر أو دعوة للشراء، ليس إعلاناً.
عند الشك اجعل is_ad=false. لا تعدل النص إطلاقاً.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"is_ad": true/false}}"""
    try:
        result = call_gemini(prompt, api_key)
        return bool(result.get("is_ad", False))
    except Exception as e:
        print(f"❌ خطأ فحص الإعلان: {e}")
        return False


# ==================== الترجمة وإعادة الصياغة ====================

def call_translate(text, api_key, extra_rules=None):
    extra = f"\nتعليمات إضافية خاصة بالقناة:\n{extra_rules}\n" if extra_rules else ""

    prompt = f"""أنت محرر عربي محترف تكتب منشورات لقناة تلغرام. مهمتك نقل النص إلى العربية بصياغة طبيعية وسلسة، كما لو أن محرراً عربياً كتبه من البداية، لا أن تترجمه حرفياً.

قواعد الصياغة:
- استخدم عربية واضحة وبسيطة وحيوية، مناسبة لطبيعة النص وجمهوره. في أخبار كرة القدم استخدم المصطلحات الكروية العربية المألوفة، وفي التقنية والألعاب استخدم المصطلحات الشائعة لدى الجمهور.
- أعد بناء الجمل وترتيبها بحرية لتحسين سلاسة العربية، مع الالتزام التام بمعنى النص الأصلي.
- ابدأ بالمعلومة الأهم، وتجنب الحشو والتكرار والتراكيب المترجمة حرفياً.
- حافظ على جميع الحقائق والتفاصيل المهمة، والأسماء والفرق والنتائج والأرقام والتواريخ والأسعار والاقتباسات والروابط المطلوبة ودرجة التأكيد والنفي. لا تحوّل احتمالاً إلى تأكيد، أو تفاوضاً إلى اتفاق نهائي.
- لا تخترع معلومات أو استنتاجات أو سياقاً غير موجود، ولا تحذف تفصيلاً مهماً لمجرد الاختصار.
- احتفظ بالإيموجي ذات المعنى وبنبرة الخبر الأصلية، بما فيها صيغة العاجل إن وُجدت، دون الإكثار من الإيموجي من عندك.
- تجاهل روابط وإشارات حسابات المصدر غير اللازمة، ولا تضف مقدمة أو تعليقاً أو خاتمة أو هاشتاغات من عندك.
- لا تعتبر خبراً أو تحديثاً عادياً إعلاناً لمجرد ذكر منتج أو لعبة أو شركة أو خدمة. اجعل should_post = false فقط عند وجود إعلان تجاري مدفوع أو ترويج صريح لمنتج/خدمة. عند الشك، انشره.
- إذا كانت هناك تعليمات خاصة بالقناة أدناه، طبّقها ما دامت لا تغيّر حقائق النص الأصلي.
- أخرج النتيجة بصيغة JSON صحيحة فقط، من دون أي نص خارج JSON.

مثال على الأسلوب: بدلاً من ترجمة الجملة كلمة بكلمة، صغها بالعربية الطبيعية مع الحفاظ على المعنى نفسه.

{extra}
النص الأصلي:
{text}

أعد النتيجة بصيغة JSON فقط:
{{"should_post": true/false, "text": "المنشور العربي النهائي"}}"""

    try:
        result = call_gemini(prompt, api_key)
        return {
            "should_post": bool(result.get("should_post", True)),
            "text": (result.get("text") or "").strip(),
        }
    except Exception as e:
        print(f"❌ خطأ الترجمة — لن يُنشر بلا ترجمة: {e}")
        return {"should_post": False, "text": ""}


def call_rephrase(text, api_key, extra_rules=None):
    extra = f"\nتعليمات إضافية خاصة بالقناة:\n{extra_rules}\n" if extra_rules else ""
    prompt = f"""أنت محرر عربي محترف. أعد صياغة النص التالي ليبدو طبيعياً وسلساً وكأنه كُتب بالعربية من البداية، مع الحفاظ الكامل على المعلومات.

قواعد إعادة الصياغة:
- استخدم عربية واضحة وبسيطة وحيوية، وبأسلوب يناسب نوع المنشور والجمهور المستهدف.
- غيّر بناء الجمل وترتيبها عند الحاجة، ولا تكتفِ باستبدال الكلمات بمرادفات.
- حافظ على جميع الأسماء والأرقام والتواريخ والنتائج والأسعار والاقتباسات والتفاصيل المهمة، وعلى النفي ودرجة التأكيد ونسبة التصريحات إلى أصحابها.
- لا تحوّل الشائعة إلى حقيقة، أو الاهتمام إلى مفاوضات، أو المفاوضات إلى اتفاق؛ ولا تضف استنتاجات أو معلومات من عندك.
- لا تحذف تفاصيل مهمة ولا تختصر بما يغيّر المعنى. تجنّب الحشو والتكرار واللغة المتكلّفة.
- تجاهل روابط وإشارات حسابات المصدر غير الضرورية، ولا تضف مقدمة أو خاتمة أو تعليقاً أو هاشتاغات من عندك.
- لا تعتبر خبراً عادياً إعلاناً. اجعل should_post = false فقط للإعلان التجاري المدفوع أو الترويج الصريح لمنتج/خدمة؛ وعند الشك انشره.
- طبّق تعليمات القناة الإضافية أدناه دون تغيير حقائق النص.
- أخرج JSON صحيحاً فقط، ولا تكتب أي شيء خارجه.

{extra}
النص الأصلي:
{text}

أعد النتيجة بصيغة JSON فقط:
{{"should_post": true/false, "text": "النص المعاد صياغته"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return {
            "should_post": bool(result.get("should_post", True)),
            "text": (result.get("text") or text).strip(),
        }
    except Exception as e:
        print(f"❌ خطأ إعادة الصياغة: {e}")
        return {"should_post": True, "text": text}


def call_match_links(text, api_key):
    prompt = f"""أنت تنسّق منشورات قناة تبث روابط مشاهدة مباريات كرة القدم. حوّل النص التالي لنفس القالب بالضبط:

- احذف تمديد الحروف من أسماء الفرق واكتب الأسماء بصورة عادية.
- سطر كل مباراة: "اسم_الفريق × اسم_الفريق" بدون أي إيموجي إطلاقاً.
- سطر الوقت: "⏰ | الساعة مساءً بتوقيت مكة المكرمة".
- سطر المعلّق: "🎤 | الاسم".
- افصل بين كل مباراة والثانية بسطر فارغ.
- بعد آخر مباراة، سطر فارغ ثم سطر رابط الدعوة: إذا كانت مباراة واحدة اكتب "🔗 | رابط المباراة:"، وإذا كانت أكثر من مباراة اكتب "🔗 | رابط المباريات:" ثم رابط الدعوة بسطر لحاله.
- بعده سطر فارغ ثم: "ملاحظة: اضغط على الرابط ثم «انضمام»، وبعدها اضغط مرة أخرى على الرابط للدخول 💎"
- لا تحذف أي مباراة ولا تضف أي تعليق من عندك.

النص المطلوب تنسيقه:
{text}

أعد النتيجة بصيغة JSON فقط: {{"text": "النص بعد الترتيب بنفس القالب أعلاه بالضبط"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return (result.get("text") or "").strip()
    except Exception as e:
        print(f"❌ خطأ تنسيق منشور المباريات: {e}")
        return ""


def call_fabrizio(text, api_key):
    prompt = f"""أنت محرر أخبار كرة قدم وانتقالات لقناة تلغرام عربية. حوّل النص إلى منشور عربي طبيعي وواضح، كأن محرراً رياضياً عربياً كتبه من البداية، لا كترجمة حرفية.

قرار النشر:
- انشر الأخبار الرياضية الفعلية، بما فيها الانتقالات والمفاوضات وتجديد العقود والتصريحات والإحصائيات والأخبار الصغيرة.
- استبعد الإعلانات التجارية المدفوعة فقط، وكذلك الترويج لبودكاست أو برنامج فابريزيو نفسه إذا لم يتضمن خبراً فعلياً.
- استبعد مقاطع الفيديو القصيرة التي لا تحمل خبراً مفيداً إذا كان محتواها الأساسي غير قابل للنقل من النص.
- إذا وردت عبارة "Here we go"، انشر المنشور دائماً بلا استثناء.

أسلوب التحرير:
- استخدم عربية بسيطة وحيوية ومصطلحات كروية مألوفة، وابدأ بأهم معلومة.
- أعد بناء الجمل لتبدو عربية طبيعية، وتجنب النقل الحرفي والحشو والمبالغة.
- حافظ على أسماء اللاعبين والأندية والأرقام والمبالغ والتواريخ والاقتباسات وكل التفاصيل المهمة.
- حافظ بدقة على حالة الصفقة: اهتمام أولي، أو مفاوضات، أو اتفاق، أو توقيع رسمي. لا تجعل الخبر أكثر تأكيداً مما يقوله المصدر.
- أبقِ عبارة "Here we go" بالإنجليزية كما هي تماماً إذا وردت في النص.
- احتفظ بروابط YouTube التي تبدأ بـ youtube.com أو youtu.be كما هي حرفياً.
- احذف روابط وإشارات حساب فابريزيو رومانو على تويتر/X، باستثناء رابط يوتيوب المذكور.
- لا تضف معلومات أو تحليلات أو تعليقات أو هاشتاغات من عندك.
- أخرج JSON صحيحاً فقط دون أي نص خارجه.

النص الأصلي:
{text}

أعد النتيجة بصيغة JSON فقط:
{{"should_post": true/false, "text": "المنشور العربي النهائي"}}"""

    try:
        result = call_gemini(prompt, api_key)
        return {
            "should_post": bool(result.get("should_post", True)),
            "text": (result.get("text") or text).strip(),
        }
    except Exception as e:
        print(f"❌ خطأ معالجة فابريزيو — لن يُنشر بلا ترجمة: {e}")
        return {"should_post": False, "text": ""}


async def apply_processing(config, text):
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
        result = call_translate(text, config["gemini_key"], config.get("extra_rules"))
        return result["should_post"], result["text"]

    if mode == "rephrase_ar":
        result = call_rephrase(text, config["gemini_key"], config.get("extra_rules"))
        return result["should_post"], result["text"]

    if mode == "fabrizio_special":
        force_post = bool(re.search(r"here\s*we\s*go", text, re.IGNORECASE))
        result = call_fabrizio(text, config["gemini_key"])
        should_post = bool(result["text"]) and (result["should_post"] or force_post)
        return should_post, result["text"]

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

    if is_duplicate_content(source_id, messages, raw_text):
        print(f"⏭️ تم تجاهل منشور مكرر — {config['name']}")
        return

    if contains_click_here_phrase(raw_text):
        print(f"⏭️ تم تجاهل منشور — {config['name']} (يحتوي 'اضغط هنا للمشاهدة')")
        return

    hidden_links = extract_hidden_link_urls(text_msg, config.get("source_username"))
    if hidden_links:
        raw_text = (raw_text.rstrip() + "\n\n" + "\n".join(hidden_links)) if raw_text else "\n".join(hidden_links)

    strip_tg_links = config["mode"] != "match_links"
    cleaned = clean_text(
        raw_text,
        config.get("source_username"),
        strip_telegram_links=strip_tg_links,
    )
    should_post, final_text = await apply_processing(config, cleaned)

    if not should_post:
        print(f"⏭️ تم تجاهل منشور — {config['name']} (إعلان أو غير مهم أو خطأ تقني)")
        return

    media_msgs = [m for m in messages if _is_usable_media_msg(m)]

    if config.get("skip_if_video") and any(m.video for m in media_msgs):
        force_post = bool(re.search(r"here\s*we\s*go", raw_text, re.IGNORECASE))
        if not force_post:
            print(f"⏭️ تم تجاهل منشور — {config['name']} (يحتوي فيديو مرفق)")
            return

    if not final_text.strip() and config["mode"] in ("translate_en_ar", "rephrase_ar"):
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

    published = False
    try:
        if media_msgs:
            to_send = (
                _media_payload(media_msgs[0])
                if len(media_msgs) == 1
                else [_media_payload(m) for m in media_msgs]
            )
            try:
                await client.send_file(
                    config["target"], to_send,
                    caption=final_text or None, parse_mode="html",
                )
                published = True
                print(f"✅ نُشر (وسائط) — {config['name']}")
            except Exception as e:
                print(f"⚠️ فشل النسخ المباشر، محاولة تحميل احتياطي — {config['name']}: {e}")
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
                    await client.send_file(
                        config["target"], to_send2,
                        caption=final_text or None, parse_mode="html",
                    )
                    for f in files:
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                    published = True
                    print(f"✅ نُشر (وسائط، تحميل احتياطي) — {config['name']}")
                elif final_text:
                    await client.send_message(
                        config["target"], final_text,
                        parse_mode="html", link_preview=False,
                    )
                    published = True
                    print(f"⚠️ نُشر نص فقط (فشل النسخ والتحميل) — {config['name']}")
                else:
                    print(f"❌ تم تجاهل منشور — فشل كل محاولات نشر الوسائط — {config['name']}")
        elif final_text:
            await client.send_message(
                config["target"], final_text,
                parse_mode="html", link_preview=False,
            )
            published = True
            print(f"✅ نُشر (نص) — {config['name']}")
    except Exception as e:
        print(f"❌ خطأ بالنشر — {config['name']}: {e}")

    if published:
        record_published_content(source_id, messages, raw_text)


# ==================== معالجة الرسائل الفائتة (Polling) ====================

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

async def main():
    await client.start()
    print("🚀 بدء فحص القنوات (Polling)...")

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
