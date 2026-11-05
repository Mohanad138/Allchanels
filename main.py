# -*- coding: utf-8 -*-
"""
بوت الريلي الموحد — حساب شخصي واحد (Telethon) يفحص القنوات المصدر كل تشغيل
(بولينغ، بدون استماع مباشر مستمر) وينشر الجديد بـ قنوات الهدف.
(نسخة مستودع allchanels - بدون فابريزيو)
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

# ==================== إعدادات القنوات (بدون فابريزيو) ====================
CHANNELS = {
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

DUP_HISTORY_SIZE = 30
DUP_SIMILARITY_THRESHOLD = 0.80   
DUP_OVERLAP_THRESHOLD = 0.85      
DUP_MIN_TOKENS = 6                

def _norm_for_dup(text):
    t = text.lower()
    t = re.sub(r'https?://\S+', ' ', t)
    t = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', t)
    t = t.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ى', 'ي').replace('ة', 'ه')
    t = re.sub(r'[^\w\u0600-\u06FF\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def _dup_tokens(norm):
    return set(re.findall(r'[\w\u0600-\u06FF]{3,}', norm))

def is_duplicate_content(source_id, text):
    if not text or not text.strip(): return False
    norm = _norm_for_dup(text)
    if not norm: return False
    new_tokens = _dup_tokens(norm)
    recent = state.setdefault("recent_texts", {}).get(str(source_id), [])
    for prev in recent:
        prev_norm = _norm_for_dup(prev)
        if difflib.SequenceMatcher(None, norm, prev_norm).ratio() >= DUP_SIMILARITY_THRESHOLD:
            return True
        prev_tokens = _dup_tokens(prev_norm)
        smaller = min(len(new_tokens), len(prev_tokens))
        if smaller >= DUP_MIN_TOKENS and len(new_tokens) <= len(prev_tokens) * 1.25:
            if len(new_tokens & prev_tokens) / smaller >= DUP_OVERLAP_THRESHOLD:
                return True
    return False

def record_published_text(source_id, text):
    if not text or not text.strip(): return
    key = str(source_id)
    norm = _norm_for_dup(text)
    if not norm: return
    bucket = state.setdefault("recent_texts", {}).setdefault(key, [])
    bucket.append(norm)
    state["recent_texts"][key] = bucket[-DUP_HISTORY_SIZE:]
    save_state(state)

def commit_state():
    try:
        subprocess.run(["git", "add", STATE_FILE], check=False)
        c = subprocess.run(["git", "commit", "-m", "update relay state"], capture_output=True, text=True)
        if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr).lower():
            return
        for attempt in range(1, 4):
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True, text=True)
            p = subprocess.run(["git", "push"], capture_output=True, text=True)
            if p.returncode == 0: return
            print(f"⚠️ فشل رفع الحالة لـ GitHub (محاولة {attempt}/3): {(p.stderr or p.stdout).strip()[:300]}")
            time.sleep(2 * attempt)
        print("❌ تعذّر رفع الحالة لـ GitHub بعد 3 محاولات — احتمال تكرار منشورات بالتشغيلة الجاية")
    except Exception as e:
        print(f"⚠️ git commit error: {e}")

# ==================== تنظيف النص ====================

def _is_small_thumbnail_photo(photo, abs_threshold=250, square_size_cap=800):
    try:
        dims = [(getattr(s, "w", 0), getattr(s, "h", 0)) for s in photo.sizes if hasattr(s, "w")]
        if not dims: return False
        max_w = max(w for w, _ in dims)
        max_h = max(h for _, h in dims)
        if max_w < abs_threshold and max_h < abs_threshold: return True
        if max_w > 0 and max_h > 0:
            ratio = max_w / max_h
            if 0.85 <= ratio <= 1.18 and max(max_w, max_h) <= square_size_cap: return True
        return False
    except Exception: return False

def _message_has_any_video(m):
    media = m.media
    if isinstance(media, MessageMediaDocument):
        return bool(m.video) or bool(getattr(m, "gif", None))
    if isinstance(media, MessageMediaWebPage):
        wp = getattr(media, "webpage", None)
        if wp is None: return False
        if getattr(wp, "duration", None): return True
        wtype = str(getattr(wp, "type", "") or "").lower()
        if "video" in wtype or "gif" in wtype: return True
        doc = getattr(wp, "document", None)
        if doc is not None and str(getattr(doc, "mime_type", "")).startswith(("video/", "image/gif")): return True
    return False

def _is_usable_media_msg(m):
    media = m.media
    if isinstance(media, (MessageMediaPhoto, MessageMediaDocument)): return True
    if isinstance(media, MessageMediaWebPage):
        wp = getattr(media, "webpage", None)
        photo = getattr(wp, "photo", None)
        if photo and not _is_small_thumbnail_photo(photo): return True
    return False

def _media_payload(m):
    if isinstance(m.media, MessageMediaWebPage): return m.photo
    return m.media

def extract_hidden_link_urls(message, source_username=None):
    if not message or not getattr(message, "entities", None): return []
    handle = (source_username or "").lstrip("@").lower()
    skip_anchor_re = re.compile(r'read\s*more|اقرأ\s*المزيد', re.IGNORECASE)
    urls = []
    try:
        for entity, anchor_text in message.get_entities_text(MessageEntityTextUrl):
            url = entity.url
            if handle and f"t.me/{handle}".lower() in url.lower(): continue
            if skip_anchor_re.search(anchor_text or ""): continue
            urls.append(url)
    except Exception: pass
    return urls

def clean_text(text, source_username=None, strip_telegram_links=True):
    if not text: return ""
    cleaned = text.replace('📊', '')
    if source_username: cleaned = re.sub(re.escape(source_username), '', cleaned, flags=re.IGNORECASE)
    if strip_telegram_links: cleaned = re.sub(r'(https?://)?t\.me/\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'https?://t\.co/\S+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?i)forwarded from.*', '', cleaned)
    cleaned = re.sub(r'(?i)read\s*more\.?\s*$', '', cleaned.rstrip())
    cleaned = re.sub(r'اقرأ\s*المزيد\.?\s*$', '', cleaned.rstrip())
    cleaned = re.sub(r'أعيد التوجيه من.*', '', cleaned)
    cleaned = re.sub(r'^.*نيمار\s*ابن\s*الانبار.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'^.*@?IRAQEDU.*$', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    lines = cleaned.split('\n')
    while lines and not re.search(r'[A-Za-z\u0600-\u06FF0-9]', lines[-1]): lines.pop()
    return '\n'.join(lines).rstrip()

SHARE_PHRASE_RE = re.compile(r'شارك\s+(القناة|المنشور)\s+مع\s+اصدقائ?ك', re.IGNORECASE)

def insert_link_after_share_phrase(text, link_text):
    match = SHARE_PHRASE_RE.search(text)
    if not match: return None
    newline_idx = text.find('\n', match.end())
    if newline_idx == -1: return text.rstrip() + f"\n{link_text}"
    return text[:newline_idx] + f"\n{link_text}" + text[newline_idx:]

def contains_click_here_phrase(text):
    if not text: return False
    return bool(re.search(r'اضغط\s*هنا.{0,15}(للمشاهدة|لمشاهدة|مشاهدة)', text))

def contains_youtube_link(text):
    if not text: return False
    return bool(re.search(r'(youtube\.com|youtu\.be)', text, re.IGNORECASE))

# ==================== Gemini ====================

def call_gemini(prompt, api_key, max_retries=3):
    if not api_key: raise RuntimeError("no gemini key")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(2 ** attempt); continue
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"): raw = raw[4:].strip()
            return json.loads(raw)
        except Exception as e:
            if attempt == max_retries: raise e
            time.sleep(2 ** attempt)

def call_gemini_vision(image_path, api_key, max_retries=3):
    if not api_key: return {"has_text": False, "caption": ""}
    try:
        import base64
        with open(image_path, "rb") as f: img_b64 = base64.b64encode(f.read()).decode()
    except Exception: return {"has_text": False, "caption": ""}
    mime = "image/png" if image_path.lower().endswith("png") else "image/jpeg"
    prompt = 'افحص هذه الصورة: هل يوجد عليها نص؟ لخصه بالعربية. JSON: {"has_text": true/false, "caption": "النص"}'
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": img_b64}}, {"text": prompt}]}]}
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(2 ** attempt); continue
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"): raw = raw[4:].strip()
            result = json.loads(raw)
            return {"has_text": bool(result.get("has_text", False)), "caption": (result.get("caption") or "").strip()}
        except Exception:
            if attempt == max_retries: return {"has_text": False, "caption": ""}
            time.sleep(2 ** attempt)

def check_image_has_play_button(image_path, api_key, max_retries=3):
    if not api_key: return False
    try:
        import base64
        with open(image_path, "rb") as f: img_b64 = base64.b64encode(f.read()).decode()
    except Exception: return False
    mime = "image/png" if image_path.lower().endswith("png") else "image/jpeg"
    prompt = 'هل يوجد زر تشغيل فيديو (▶) بالصورة؟ JSON: {"has_play_button": true/false}'
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": img_b64}}, {"text": prompt}]}]}
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                time.sleep(2 ** attempt); continue
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"): raw = raw[4:].strip()
            return bool(json.loads(raw).get("has_play_button", False))
        except Exception:
            if attempt == max_retries: return False
            time.sleep(2 ** attempt)

def check_is_ad(text, api_key):
    prompt = f'حدد إذا كان النص إعلاناً (is_ad=true) أو خبراً (false).\nالنص: {text}\nJSON: {{"is_ad": true/false}}'
    try: return bool(call_gemini(prompt, api_key).get("is_ad", False))
    except Exception: return False

def check_is_relevant_topic(text, api_key, topic_description):
    prompt = f'حدد إذا كان يتعلق بالموضوع (is_relevant=true) أو لا (false).\nالموضوع: {topic_description}\nالنص: {text}\nJSON: {{"is_relevant": true/false}}'
    try: return bool(call_gemini(prompt, api_key).get("is_relevant", False))
    except Exception: return True

def call_translate(text, api_key, extra_rules=None):
    extra = f"\n{extra_rules}\n" if extra_rules else ""
    prompt = f'أعد صياغة النص بالعربية. تجاهل الروابط. إعلان؟ should_post=false.\n{extra}\nالنص: {text}\nJSON: {{"should_post": true/false, "text": "الترجمة"}}'
    try:
        res = call_gemini(prompt, api_key)
        return {"should_post": bool(res.get("should_post", True)), "text": (res.get("text") or text).strip()}
    except Exception: return {"should_post": False, "text": ""}

def call_rephrase(text, api_key, extra_rules=None):
    extra = f"\n{extra_rules}\n" if extra_rules else ""
    prompt = f'أعد صياغة النص بأسلوب صحفي.\n{extra}\nالنص: {text}\nJSON: {{"should_post": true/false, "text": "النص"}}'
    try:
        res = call_gemini(prompt, api_key)
        return {"should_post": bool(res.get("should_post", True)), "text": (res.get("text") or text).strip()}
    except Exception: return {"should_post": True, "text": text}

def call_match_links(text, api_key):
    prompt = f'نسق النص لروابط مباريات: اسم_الفريق × اسم_الفريق ⏰ | الساعة 🎤 | الاسم 🔗 | الرابط.\nالنص: {text}\nJSON: {{"text": "النص"}}'
    try: return (call_gemini(prompt, api_key).get("text") or "").strip()
    except Exception: return ""

async def apply_processing(config, text):
    mode = config["mode"]
    if not text: return True, ""
    if not config.get("gemini_key"): return False, ""

    if mode == "copy":
        if check_is_ad(text, config["gemini_key"]): return False, text
        if config.get("topic_filter") and not check_is_relevant_topic(text, config["gemini_key"], config["topic_filter"]): return False, text
        return True, text
    elif mode == "match_links":
        res = call_match_links(text, config["gemini_key"])
        return bool(res), res
    elif mode == "translate_en_ar":
        res = call_translate(text, config["gemini_key"], config.get("extra_rules"))
        return res["should_post"], res["text"]
    elif mode == "rephrase_ar":
        res = call_rephrase(text, config["gemini_key"], config.get("extra_rules"))
        return res["should_post"], res["text"]
    return True, text

# ==================== معالجة ونشر دفعة رسائل ====================

DUP_TARGET_HISTORY = 15
DUP_TARGET_HARD = 0.78      
DUP_SOFT_CONTAINMENT = 0.5  
DUP_SOFT_MIN_SHARED = 3

def _norm_for_dup_target(text, strip_strings=()):
    t = text or ""
    for st in strip_strings:
        if st: t = t.replace(st, " ")
    t = re.sub(r'https?://\S+', ' ', t)
    t = re.sub(r'@\w+', ' ', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'[_\s]+', ' ', t).strip().lower()
    return t

def check_same_news_ai(new_text, similar_texts, api_key):
    if not api_key or not similar_texts: return False
    joined = "\n---\n".join(similar_texts)
    prompt = f'السابق:\n{joined}\n\nالجديد:\n{new_text}\n\nهل هو نفس الخبر؟ JSON: {{"is_duplicate": true/false}}'
    try: return bool(call_gemini(prompt, api_key).get("is_duplicate", False))
    except Exception: return False

async def is_duplicate_in_target(config, final_text):
    target = config.get("target")
    if not target or not final_text or not final_text.strip(): return False
    try: recent = await client.get_messages(target, limit=DUP_TARGET_HISTORY)
    except Exception: return False

    strip_strings = [config.get("link", "")]
    new_norm = _norm_for_dup_target(final_text, strip_strings)
    if len(new_norm) < 8: return False
    new_tokens = {w for w in new_norm.split() if len(w) >= 3}

    soft_candidates = []
    for m in recent:
        body = (m.message or "").strip()
        if not body: continue
        old_norm = _norm_for_dup_target(body, strip_strings)
        if not old_norm: continue
        if difflib.SequenceMatcher(None, new_norm, old_norm).ratio() >= DUP_TARGET_HARD: return True
        old_tokens = {w for w in old_norm.split() if len(w) >= 3}
        shared = new_tokens & old_tokens
        if new_tokens and old_tokens and len(shared) >= DUP_SOFT_MIN_SHARED:
            containment = len(shared) / min(len(new_tokens), len(old_tokens))
            if containment >= DUP_SOFT_CONTAINMENT: soft_candidates.append((containment, body))

    if soft_candidates:
        soft_candidates.sort(key=lambda x: x[0], reverse=True)
        return check_same_news_ai(final_text, [b for _, b in soft_candidates[:3]], config.get("gemini_key"))
    return False

async def process_batch(source_id, messages):
    config = CHANNELS.get(source_id)
    if not config: return

    raw_text = ""
    text_msg = None
    for m in messages:
        if m.message:
            raw_text = m.message
            text_msg = m
            break

    if contains_click_here_phrase(raw_text):
        print(f"⏭️  تم تجاهل منشور — {config['name']} (اضغط هنا)")
        return

    hidden_links = extract_hidden_link_urls(text_msg, config.get("source_username"))
    if hidden_links:
        raw_text = (raw_text.rstrip() + "\n\n" + "\n".join(hidden_links)) if raw_text else "\n".join(hidden_links)

    strip_tg_links = config["mode"] != "match_links"
    cleaned = clean_text(raw_text, config.get("source_username"), strip_telegram_links=strip_tg_links)

    if is_duplicate_content(source_id, cleaned):
        print(f"⏭️  تم تجاهل منشور — {config['name']} (تكرار)")
        return

    should_post, final_text = await apply_processing(config, cleaned)
    if not should_post:
        print(f"⏭️  تم تجاهل منشور — {config['name']} (إعلان أو غير مهم)")
        return

    record_published_text(source_id, cleaned)

    if final_text and is_duplicate_content(f"{source_id}#final", final_text):
        print(f"⏭️  تم تجاهل منشور — {config['name']} (النص النهائي تكرار)")
        return
    record_published_text(f"{source_id}#final", final_text)

    media_msgs = [m for m in messages if _is_usable_media_msg(m)]
    force_post_here_we_go = bool(re.search(r'here\s*we\s*go', raw_text, re.IGNORECASE))

    if config.get("skip_if_video") and any(_message_has_any_video(m) for m in messages) and not force_post_here_we_go:
        print(f"⏭️  تم تجاهل منشور — {config['name']} (فيديو)")
        return

    if config.get("skip_if_youtube") and contains_youtube_link(raw_text) and not force_post_here_we_go:
        print(f"⏭️  تم تجاهل منشور — {config['name']} (يوتيوب)")
        return

    if config.get("skip_if_play_button") and not force_post_here_we_go:
        first_photo_msg = next((m for m in media_msgs if m.photo), None)
        if first_photo_msg:
            tmp_path = None
            has_play = False
            try:
                tmp_path = await client.download_media(first_photo_msg, file=f"{DOWNLOAD_DIR}/")
                if tmp_path: has_play = check_image_has_play_button(tmp_path, config["gemini_key"])
            except Exception: pass
            finally:
                if tmp_path:
                    try: os.remove(tmp_path)
                    except OSError: pass
            if has_play:
                print(f"⏭️  تم تجاهل منشور — {config['name']} (غلاف فيديو)")
                return

    if (not final_text.strip() and config["mode"] in ("translate_en_ar", "rephrase_ar")):
        first_photo_msg = next((m for m in media_msgs if m.photo), None)
        if first_photo_msg:
            tmp_path = None
            try:
                tmp_path = await client.download_media(first_photo_msg, file=f"{DOWNLOAD_DIR}/")
                if tmp_path:
                    vision = call_gemini_vision(tmp_path, config["gemini_key"])
                    if vision["has_text"] and vision["caption"]: final_text = vision["caption"]
            except Exception: pass
            finally:
                if tmp_path:
                    try: os.remove(tmp_path)
                    except OSError: pass

    if await is_duplicate_in_target(config, final_text):
        print(f"⏭️  تم تجاهل منشور — {config['name']} (تكرار بقناة الهدف)")
        return

    if config.get("add_link") and config.get("link"):
        link_text = config["link"]
        inserted = None
        if config.get("link_after_share_phrase") and final_text:
            inserted = insert_link_after_share_phrase(final_text, link_text)
        if inserted is not None: final_text = inserted
        else: final_text = f"{final_text}\n\n{link_text}" if final_text else link_text

    try:
        if media_msgs:
            to_send = _media_payload(media_msgs[0]) if len(media_msgs) == 1 else [_media_payload(m) for m in media_msgs]
            try:
                await client.send_file(config["target"], to_send, caption=final_text or None, parse_mode="html")
                print(f"✅ نُشر (وسائط) — {config['name']}")
            except Exception as e:
                print(f"⚠️ فشل النسخ، تحميل احتياطي — {config['name']}: {e}")
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
                    print(f"✅ نُشر (وسائط، احتياطي) — {config['name']}")
                elif final_text:
                    await client.send_message(config["target"], final_text, parse_mode="html", link_preview=False)
                    print(f"⚠️ نُشر نص فقط — {config['name']}")
                else:
                    print(f"❌ فشل نشر — {config['name']}")
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
        if latest: last_id = max(latest[0].id - 5, 0)
        state[key] = last_id
        save_state(state)

    messages = await client.get_messages(entity_ref, min_id=last_id, limit=200)
    if not messages: return

    messages = list(reversed(messages))
    
    # 🚀 إصلاح التكرار: نستخدم processed_ids بدلاً من i += len(group) لتجنب تكرار أو تخطي الألبومات
    processed_ids = set()
    for msg in messages:
        if msg.id in processed_ids: continue
        
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
    print("🚀 بدء فحص القنوات السبع (بولينغ)...")

    for source_id, cfg in CHANNELS.items():
        print(f"⏳ فحص — {cfg['name']}")
        try:
            await catch_up_channel(source_id)
        except Exception as e:
            print(f"❌ فشل فحص قناة كامل: {cfg['name']} — {e}")
        # 🚀 السرعة القصوى: الحفظ والرفع بعد كل قناة لضمان عدم التأخير
        commit_state()

    await client.disconnect()
    commit_state()
    print("✅ انتهت التشغيلة — الاتصال مقفول.")

if __name__ == "__main__":
    asyncio.run(main())
