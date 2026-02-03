import telebot
import random
import string
import json
import os
from flask import Flask, request, send_file, jsonify
import threading

# ===== AYARLAR =====
API_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
MAX_FILES = 49
DATA_DIR = "data"
ALT_MAP_FILE = "alt_map.json"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# Klasör oluştur
os.makedirs(DATA_DIR, exist_ok=True)

# Alt alan ↔ API ↔ dosya eşleşmesi
if os.path.exists(ALT_MAP_FILE):
    with open(ALT_MAP_FILE, "r") as f:
        alt_map = json.load(f)
else:
    alt_map = {}

def save_alt_map():
    with open(ALT_MAP_FILE, "w") as f:
        json.dump(alt_map, f)

def gen_api():
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(20))

# ===== Admin Dosya Yükleme =====
@bot.message_handler(content_types=['document'])
def admin_upload(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ Sadece admin dosya yükleyebilir.")
        return

    if len(alt_map) >= MAX_FILES:
        bot.reply_to(message, f"❌ Maksimum dosya sayısı ({MAX_FILES}) doldu.")
        return

    doc = message.document
    if not doc.file_name.endswith(".txt"):
        bot.reply_to(message, "❌ Sadece TXT dosya kabul edilir.")
        return

    alt_name = os.path.splitext(doc.file_name)[0]

    if alt_name in alt_map:
        bot.reply_to(message, "❌ Bu alt alan zaten kayıtlı.")
        return

    api_key = gen_api()
    file_path = os.path.join(DATA_DIR, doc.file_name)

    file_info = bot.get_file(doc.file_id)
    downloaded = bot.download_file(file_info.file_path)
    with open(file_path, "wb") as f:
        f.write(downloaded)

    alt_map[alt_name] = {"api": api_key, "file": file_path}
    save_alt_map()

    bot.reply_to(message, f"✅ Dosya kaydedildi: {alt_name}\n🔑 API Key: `{api_key}`", parse_mode="Markdown")

# ===== Telegram API Sorgusu =====
@bot.message_handler(commands=['api'])
def api_query(message):
    try:
        _, api_key, query = message.text.split(" ", 2)
    except:
        bot.reply_to(message, "Kullanım:\n/api APIKEY sorgu")
        return

    results = query_file_by_api(api_key, query)
    if results is None:
        bot.reply_to(message, "❌ Geçersiz API Key")
        return

    send_results(bot, message.chat.id, results, api_key)

# ===== Ortak Fonksiyonlar =====
def query_file_by_api(api_key, query_text):
    file_path = None
    for alt, info in alt_map.items():
        if info["api"] == api_key:
            file_path = info["file"]
            break
    if not file_path:
        return None

    results = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if query_text.lower() in line.lower():
                    results.append(line.strip())
    except:
        return None
    return results

def send_results(bot_instance, chat_id, results, api_key):
    if not results:
        bot_instance.send_message(chat_id, "Sonuç yok.")
    elif len(results) <= 4:
        bot_instance.send_message(chat_id, "\n".join(results))
    else:
        out = f"/tmp/{api_key}_result.txt"
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(results))
        bot_instance.send_document(chat_id, open(out, "rb"))

# ===== HTTP Endpoint =====
@app.route('/query', methods=['GET'])
def query_endpoint():
    api_key = request.args.get('api')
    q = request.args.get('q')
    if not api_key or not q:
        return jsonify({"error": "api ve q parametreleri gerekli"}), 400

    results = query_file_by_api(api_key, q)
    if results is None:
        return jsonify({"error": "Geçersiz API key"}), 403

    if len(results) > 4:
        out_file = f"/tmp/{api_key}_result.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(results))
        return send_file(out_file, as_attachment=True)
    else:
        return jsonify({"results": results})

# ===== /start =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Merhaba! /api APIKEY sorgu komutunu kullanabilirsiniz veya HTTP GET ile /query?api=APIKEY&q=sorgu kullanabilirsiniz. Dosya yükleyemezsiniz.")

# ===== Bot thread ile başlat =====
threading.Thread(target=lambda: bot.infinity_polling()).start()

# ===== Render uyumlu start =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
