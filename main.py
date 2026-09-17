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
    -1003922419894: {
        "name": "أفلام ومسلسلات",
        "target": -1002651737980,
        "mode": "copy",
        "gemini_key": GEMINI_KEY_AFLAM,
        "source_username": "@CCDBotc",
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
    -1001498073945: {
        "name": "أخبار التقنية",
        "target": -1003867842495,
        "mode": "translate_en_ar",
        "gemini_key": GEMINI_KEY_TECH,
        "source_username": "@tech",
    },
    -1001073231505: {
        "name": "أثر",
        "target": -1001555638090,
        "mode": "copy",
        "gemini_key": GEMINI_KEY_GENERAL,
        "source_username": "@YYAEE",
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

def clean_text(text, source_username=None):
    if not text:
        return ""
    cleaned = text
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = re.sub(r't\.me/\S+', '', cleaned)
    if source_username:
        cleaned = re.sub(re.escape(source_username), '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?i)forwarded from.*', '', cleaned)
    cleaned = re.sub(r'أعيد التوجيه من.*', '', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

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
    prompt = f"""حدد فقط إذا كان النص التالي إعلاناً أو محتوى ترويجياً (دعاية/عرض تجاري/رعاية مدفوعة). لا تعدل النص إطلاقاً.
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
    prompt = f"""أنت كاتب عربي محترف. ترجم النص التالي من الإنجليزية إلى العربية بأسلوب طبيعي فصيح، كأن كاتبه الأصلي عربي وليس ترجمة حرفية.
تجاهل أي روابط أو إشارات لقناة المصدر. لا تضيف أي تعليق أو مقدمة من عندك.
إذا كان النص إعلاناً أو محتوى ترويجياً اجعل should_post قيمتها false.

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
إذا كان النص إعلاناً أو محتوى ترويجياً اجعل should_post قيمتها false.

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

def call_fabrizio(text, api_key):
    prompt = f"""أنت محرر لصفحة عربية تنقل كل منشورات حساب فابريزيو رومانو الرسمي بالعربية.

معايير النشر:
- انشر كل منشور يصلك بلا استثناء (should_post = true دائماً)، سواء كان انتقالات، صفقات، تجديد
  عقود، تغطية مباراة، نتيجة، إحصائية أو رقم للاعب، تصريح، أو أي خبر آخر مهما كان صغيراً أو هامشياً.
- الاستثناء الوحيد: إذا كان النص إعلاناً أو محتوى ترويجياً صريحاً (دعاية لمنتج/تطبيق/رعاية مدفوعة/
  عرض تجاري) — عندها فقط اجعل should_post = false. أي خبر رياضي حقيقي، مهما كانت أهميته، ليس إعلاناً.
- أي منشور يحتوي على عبارة "Here we go" يُنشر دائماً (هذا مضمون بالكود أيضاً بغض النظر عن رأيك).

الترجمة:
- ترجم النص إلى عربية طبيعية فصيحة كأن كاتبه عربي أصلاً.
- أبقِ عبارة "Here we go" بالإنجليزية كما هي حرفياً بدون ترجمة إذا وردت بالنص.
- احذف أي رابط أو إشارة لقناة المصدر (بما فيها روابط تويتر/X وإشارات "Fabrizio Romano on X").
  لا تضيف تعليقات من عندك.

النص:
{text}

أعد النتيجة بصيغة JSON فقط: {{"should_post": true/false, "text": "النص المُعالج"}}"""
    try:
        result = call_gemini(prompt, api_key)
        return {"should_post": bool(result.get("should_post", True)),
                "text": (result.get("text") or text).strip()}
    except Exception as e:
        print(f"❌ خطأ معالجة فابريزيو — لن يُنشر بلا ترجمة: {e}")
        return {"should_post": False, "text": ""}

async def apply_processing(config, text):
    """يرجع (should_post, final_text)."""
    mode = config["mode"]
    if not text:
        return True, ""

    if mode == "copy":
        is_ad = check_is_ad(text, config["gemini_key"])
        return (not is_ad), text

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
    for m in messages:
        if m.message:
            raw_text = m.message
            break

    cleaned = clean_text(raw_text, config.get("source_username"))
    should_post, final_text = await apply_processing(config, cleaned)

    if not should_post:
        print(f"⏭️  تم تجاهل منشور (إعلان) — {config['name']}")
        return

    media_msgs = [m for m in messages if m.photo or m.video or m.document]

    # تحميل كل ملف لحاله — فشل ملف وحد (فيديو ثقيل مثلاً) ما يسقط بقية الألبوم
    files = []
    for m in media_msgs:
        try:
            path = await client.download_media(m, file=f"{DOWNLOAD_DIR}/")
            if path:
                files.append(path)
            else:
                print(f"⚠️ تحميل فاشل (بدون خطأ) — {config['name']}")
        except Exception as e:
            print(f"⚠️ خطأ تحميل ملف وسائط — {config['name']}: {e}")

    # لو المنشور صورة بلا أي تعليق نصي، وبالوضع ترجمة/إعادة صياغة —
    # افحص إذا الصورة نفسها فيها نص أجنبي مكتوب، وترجمه بدل ما ينزل منشور فاضي
    if (not final_text.strip() and files
            and config["mode"] in ("translate_en_ar", "rephrase_ar")):
        first_image = next((f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))), None)
        if first_image:
            vision = call_gemini_vision(first_image, config["gemini_key"])
            if vision["has_text"] and vision["caption"]:
                final_text = vision["caption"]

    if config.get("add_link") and config.get("link"):
        link_text = config["link"]
        final_text = f"{final_text}\n\n{link_text}" if final_text else link_text

    try:
        if files:
            to_send = files[0] if len(files) == 1 else files
            await client.send_file(config["target"], to_send,
                                    caption=final_text or None, parse_mode="html")
            for f in files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            print(f"✅ نُشر (وسائط) — {config['name']}")
        elif media_msgs and not files:
            # كل ملفات الوسائط فشل تحميلها — لا تنشر منشور فاضي بلا وسائط ولا نص أصلي
            if final_text:
                await client.send_message(config["target"], final_text,
                                           parse_mode="html", link_preview=False)
                print(f"⚠️ نُشر نص فقط (فشل تحميل الوسائط) — {config['name']}")
            else:
                print(f"❌ تم تجاهل منشور — فشل تحميل كل الوسائط وما فيه نص — {config['name']}")
        elif final_text:
            await client.send_message(config["target"], final_text,
                                       parse_mode="html", link_preview=False)
            print(f"✅ نُشر (نص) — {config['name']}")
    except Exception as e:
        print(f"❌ خطأ بالنشر — {config['name']}: {e}")

# ==================== معالجة الرسائل الفائتة (بولينغ) ====================

async def catch_up_channel(source_id):
    key = str(source_id)
    last_id = state.get(key, 0)

    if last_id == 0:
        latest = await client.get_messages(source_id, limit=1)
        if latest:
            last_id = max(latest[0].id - 5, 0)
        state[key] = last_id
        save_state(state)

    messages = await client.get_messages(source_id, min_id=last_id, limit=200)
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
        await catch_up_channel(source_id)

    await client.disconnect()
    commit_state()
    print("✅ انتهت التشغيلة — الاتصال مقفول.")

if __name__ == "__main__":
    asyncio.run(main())
