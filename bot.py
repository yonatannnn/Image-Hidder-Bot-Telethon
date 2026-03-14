import os
import json
import requests
from flask import Flask, request, jsonify
from pymongo import MongoClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ---- CONFIG ----
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is required")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY is required")

cipher = Fernet(ENCRYPTION_KEY.encode())

# Database Connection
client = MongoClient(MONGO_URI)
db = client["photo_hide_db"]
collection = db["hidden_photos"]

# Flask App
app = Flask(__name__)

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_BASE = f"https://api.telegram.org/file/bot{BOT_TOKEN}"


def tg_post(method, data=None, files=None):
    url = f"{API_BASE}/{method}"
    resp = requests.post(url, data=data, files=files, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_keyboard(rows):
    return {"inline_keyboard": rows}


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return tg_post("sendMessage", data=data)


def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return tg_post("editMessageText", data=data)


def answer_callback(callback_id):
    return tg_post("answerCallbackQuery", data={"callback_query_id": callback_id})


def delete_message(chat_id, message_id):
    return tg_post("deleteMessage", data={"chat_id": chat_id, "message_id": message_id})


def get_file_bytes(file_id):
    info = tg_post("getFile", data={"file_id": file_id})
    file_path = info.get("result", {}).get("file_path")
    if not file_path:
        raise RuntimeError("Failed to get file_path from Telegram")
    file_url = f"{FILE_BASE}/{file_path}"
    resp = requests.get(file_url, timeout=30)
    resp.raise_for_status()
    return resp.content


def handle_start(chat_id):
    welcome_text = (
        "<b>👋 Welcome to Photo Hider Bot!</b>\n\n"
        "🔹 Send a <b>photo</b>, and it will be <b>securely stored</b>.\n"
        "🔹 Retrieve it anytime using your unique <b>access key</b>.\n"
        "🔹 Your photos are <b>encrypted and private</b>.\n\n"
        "📌 Type /help for more commands."
    )
    buttons = build_keyboard([
        [{"text": "📖 Help", "callback_data": "help"}],
        [{"text": "🔍 Retrieve Photo", "callback_data": "retrieve"}],
    ])
    send_message(chat_id, welcome_text, reply_markup=buttons)


def handle_help(chat_id):
    help_text = (
        "<b>🛠 Photo Hider Bot - Help Guide</b>\n\n"
        "🔹 <b>Hide a Photo</b>: Send any photo to the bot, and it will be stored securely.\n"
        "🔹 <b>Retrieve a Photo</b>: Use /get <code>&lt;your_access_key&gt;</code> to get your hidden photo.\n"
        "🔹 <b>Security</b>: Photos are encrypted and only retrievable using your key.\n"
        "🔹 <b>Privacy</b>: Photos are deleted from the bot's storage after saving.\n"
    )
    buttons = build_keyboard([
        [{"text": "🔍 Retrieve Photo", "callback_data": "retrieve"}],
        [{"text": "🏠 Home", "callback_data": "home"}],
    ])
    send_message(chat_id, help_text, reply_markup=buttons)


def handle_photo(message):
    chat_id = message["chat"]["id"]
    message_id = message["message_id"]
    user_id = message["from"]["id"]

    photos = message.get("photo", [])
    if not photos:
        return

    status_resp = send_message(chat_id, "hidding image ...")
    status_message_id = status_resp.get("result", {}).get("message_id")

    file_id = photos[-1]["file_id"]
    photo_bytes = get_file_bytes(file_id)
    encrypted_photo = cipher.encrypt(photo_bytes)
    access_key = os.urandom(4).hex()

    collection.insert_one({
        "user_id": user_id,
        "photo_data": encrypted_photo,
        "access_key": access_key,
    })

    delete_message(chat_id, message_id)

    buttons = build_keyboard([
        [{"text": "🔍 Retrieve Photo", "callback_data": "retrieve"}],
        [{"text": "📖 Help", "callback_data": "help"}],
    ])

    send_message(
        chat_id,
        f"✅ Your photo is securely stored!\nUse this key to retrieve it: <code>{access_key}</code>\n\n📌 Type /help for more commands.",
        reply_markup=buttons,
    )
    if status_message_id:
        delete_message(chat_id, status_message_id)


def handle_get(chat_id, access_key):
    record = collection.find_one({"access_key": access_key})
    if not record:
        send_message(chat_id, "❌ Invalid key! No photo found.")
        return

    status_resp = send_message(chat_id, "retreiving image ...")
    status_message_id = status_resp.get("result", {}).get("message_id")

    decrypted_photo = cipher.decrypt(record["photo_data"])

    files = {"photo": ("retrieved.jpg", decrypted_photo)}
    data = {"chat_id": chat_id, "caption": "📸 Here is your hidden photo:"}
    tg_post("sendPhoto", data=data, files=files)
    if status_message_id:
        delete_message(chat_id, status_message_id)

    buttons = build_keyboard([
        [{"text": "🔍 Retrieve Another Photo", "callback_data": "retrieve"}],
        [{"text": "📖 Help", "callback_data": "help"}],
    ])
    send_message(chat_id, "ℹ️ Need more help? Click below:", reply_markup=buttons)


def handle_callback(callback):
    data = callback.get("data", "")
    msg = callback.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")
    callback_id = callback.get("id")

    if callback_id:
        answer_callback(callback_id)

    if not chat_id or not message_id:
        return

    if data == "help":
        edit_message(
            chat_id,
            message_id,
            "<b>🛠 Photo Hider Bot - Help Guide</b>\n\n"
            "🔹 <b>Hide a Photo</b>: Send any photo to the bot, and it will be stored securely.\n"
            "🔹 <b>Retrieve a Photo</b>: Use /get <code>&lt;your_access_key&gt;</code> to get your hidden photo.\n"
            "🔹 <b>Security</b>: Photos are encrypted and only retrievable using your key.\n"
            "🔹 <b>Privacy</b>: Photos are deleted from the bot's storage after saving.\n",
            reply_markup=build_keyboard([
                [{"text": "🔍 Retrieve Photo", "callback_data": "retrieve"}],
                [{"text": "🏠 Home", "callback_data": "home"}],
            ]),
        )
    elif data == "retrieve":
        edit_message(chat_id, message_id, "📌 To retrieve a photo, use /get <code>&lt;your_access_key&gt;</code>." )
    elif data == "home":
        edit_message(
            chat_id,
            message_id,
            "<b>👋 Welcome to Photo Hider Bot!</b>\n\n"
            "🔹 Send a <b>photo</b>, and it will be <b>securely stored</b>.\n"
            "🔹 Retrieve it anytime using your unique <b>access key</b>.\n"
            "🔹 Your photos are <b>encrypted and private</b>.\n\n"
            "📌 Type /help for more commands.",
            reply_markup=build_keyboard([
                [{"text": "📖 Help", "callback_data": "help"}],
                [{"text": "🔍 Retrieve Photo", "callback_data": "retrieve"}],
            ]),
        )


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}

    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return jsonify({"ok": True})

    message = update.get("message")
    if not message:
        return jsonify({"ok": True})

    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return jsonify({"ok": True})

    text = message.get("text", "")
    if text.startswith("/start"):
        handle_start(chat_id)
    elif text.startswith("/help"):
        handle_help(chat_id)
    elif text.startswith("/get "):
        access_key = text.split(" ", 1)[1].strip()
        if access_key:
            handle_get(chat_id, access_key)
        else:
            send_message(chat_id, "❌ Invalid key! No photo found.")
    elif "photo" in message:
        handle_photo(message)

    return jsonify({"ok": True})


@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
