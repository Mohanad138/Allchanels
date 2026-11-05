# -*- coding: utf-8 -*-
"""
بوت الريلي الموحد — نسخة فائقة السرعة (بدون قناة فابريزيو)
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
GEMINI_KEY_HADAF = os.getenv("GEMINI_KEY_HADAF")

GEMINI_MODEL = "gemini-flash-lite-latest"

STATE_FILE = "relay_state.json"
DOWNLOAD_DIR = "downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ==================== إعدادات القنوات (تم حذف فابريزيو) ====================
CHANNELS = {
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
        "extra_rules": "أعد صياغة النص بشكل متناسق وبسيط وواضح، بدون حذف أي معلومة فعلية.",
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
        "topic_filter": "أخبار ومعلومات تخص الطلبة والدراسة والتعليم فقط.",
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
        "extra_rules": "إذا ورد أي سعر بالروبل، حوّله للدولار الأمريكي التقريبي.",
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

# ==================== الحالة ====================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

state = load_state()
DUP_HISTORY_SIZE = 15
DUP_SIMILARITY_THRESHOLD = 0.82 

def is_duplicate_content(source_id, text):
    if not text or not text.strip(): return False
    key = str(source_id)
    recent = state.setdefault("recent_texts", {}).get(key, [])
    norm = re.sub(r'\s+', ' ', text).strip().lower()
    for prev in recent:
        if difflib.SequenceMatcher(None, norm, prev).ratio() >= DUP_SIMILARITY_THRESHOLD: return True
    return False

def record_published_text(source_id, text):
    if not text or not text.strip(): return
    key = str(source_id)
    norm = re.sub(r'\s+', ' ', text).strip().lower()
    bucket = state.setdefault("recent_texts", {}).setdefault(key, [])
    bucket.append(norm)
    state["recent_texts"][key] = bucket[-DUP_HISTORY_SIZE:]
    save_state(state)

def commit_state():
    try:
        subprocess.run(["git", "add", STATE_FILE], check=False)
        subprocess.run(["git", "commit", "-m", "update relay state"], check=False, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False, capture_output=True)
        subprocess.run(["git", "push"], check=False, capture_output=True)
    except Exception as e:
        print(f"⚠️ git error: {e}")

# ==================== معالجة الوسائط ====================
def _message_has_any_video(m):
    media = m.media
    if isinstance(media, MessageMediaDocument): return bool(m.video) or bool(getattr(m, "gif", None))
    if isinstance(media, MessageMediaWebPage):
        wp = getattr(media, "webpage", None)
        if not wp: return False
        if getattr(wp, "duration", None): return True
        wtype = str(getattr(wp, "type", "") or "").lower()
        if "video" in wtype or "gif" in wtype: return True
        doc = getattr(wp, "document", None)
        if doc and str(getattr(doc, "mime_type", "")).startswith(("video/", "image/gif")): return True
    return False

def _is_usable_media_msg(m):
    media = m.media
    if isinstance(media, (MessageMediaPhoto, MessageMediaDocument)): return True
    if isinstance(media, MessageMediaWebPage):
        wp = getattr(media, "webpage", None)
        if getattr(wp, "photo", None): return True
    return False

def _media_payload(m):
    if isinstance(m.media, MessageMediaWebPage): return m.photo if m.photo else None
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
            if re.search(r't\.me/\+', url, re.IGNORECASE): continue
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

SHARE_PHRASE_RE = re.compile(r'شارك\s+(القناة|المنشور)\s+مع\s+[اأ]?صدقائ?ك?', re.IGNORECASE)
def insert_link_after_share_phrase(text, link_text):
    match = SHARE_PHRASE_RE.search(text)
    if not match: return None
    newline_idx = text.find('\n', match.end())
    if newline_idx == -1: return text.rstrip() + f"\n{link_text}"
    return text[:newline_idx] + f"\n{link_text}" + text[newline_idx:]

def contains_click_here_phrase(text): return bool(re.search(r'اضغط\s*هنا.{0,15}(للمشاهدة|لمشاهدة|مشاهدة)', text)) if text else False
def contains_youtube_link(text): return bool(re.search(r'(youtube\.com|youtu\.be)', text, re.IGNORECASE)) if text else False

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
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"): raw = raw[4:].strip()
            return json.loads(raw)
        except Exception as e:
            if attempt == max_retries: raise e
            time.sleep(2 ** attempt)

def check_is_ad(text, api_key):
    prompt = f'حدد إذا كان إعلاناً (is_ad=true) أو خبراً (false).\nالنص: {text}\nJSON: {{"is_ad": true/false}}'
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

# ==================== النشر ====================
async def process_batch(source_id, messages):
    config = CHANNELS.get(source_id)
    if not config: return

    raw_text = next((m.message for m in messages if m.message), "")
    text_msg = next((m for m in messages if m.message), None)

    if contains_click_here_phrase(raw_text): return

    hidden_links = extract_hidden_link_urls(text_msg, config.get("source_username"))
    if hidden_links:
        raw_text = (raw_text.rstrip() + "\n\n" + "\n".join(hidden_links)) if raw_text else "\n".join(hidden_links)

    cleaned = clean_text(raw_text, config.get("source_username"), strip_telegram_links=(config["mode"] != "match_links"))

    if is_duplicate_content(source_id, cleaned):
        print(f"⏭️ تجاهل — {config['name']} (تكرار)")
        return

    should_post, final_text = await apply_processing(config, cleaned)
    if not should_post: return

    record_published_text(source_id, cleaned)
    media_msgs = [m for m in messages if _is_usable_media_msg(m)]

    if config.get("add_link") and config.get("link"):
        if config.get("link_after_share_phrase") and final_text and insert_link_after_share_phrase(final_text, config["link"]) is not None:
            final_text = insert_link_after_share_phrase(final_text, config["link"])
        else:
            final_text = f"{final_text}\n\n{config['link']}" if final_text else config["link"]

    try:
        if media_msgs:
            valid_payloads = [_media_payload(m) for m in media_msgs if _media_payload(m) is not None]
            if not valid_payloads:
                if final_text:
                    await client.send_message(config["target"], final_text, parse_mode="html", link_preview=False)
                return
            to_send = valid_payloads[0] if len(valid_payloads) == 1 else valid_payloads
            try:
                await client.send_file(config["target"], to_send, caption=final_text or None, parse_mode="html")
                print(f"✅ نُشر وسائط — {config['name']}")
            except Exception as e:
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
                elif final_text:
                    await client.send_message(config["target"], final_text, parse_mode="html", link_preview=False)
        elif final_text:
            await client.send_message(config["target"], final_text, parse_mode="html", link_preview=False)
            print(f"✅ نُشر نص — {config['name']}")
    except Exception as e:
        print(f"❌ خطأ نشر — {config['name']}: {e}")

# ==================== التشغيل الرئيسي ====================
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

async def main():
    await client.start()
    print("🚀 بدء الفحص للقنوات الستة...")
    for source_id, cfg in CHANNELS.items():
        print(f"⏳ فحص — {cfg['name']}")
        try:
            await catch_up_channel(source_id)
            commit_state()  # حفظ فوري بعد كل قناة لضمان السرعة
        except Exception as e:
            print(f"❌ فشل قناة {cfg['name']}: {e}")
            
    await client.disconnect()
    commit_state()
    print("✅ انتهت التشغيلة.")

if __name__ == "__main__":
    asyncio.run(main())
