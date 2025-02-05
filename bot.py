from telethon import TelegramClient, events
from pymongo import MongoClient
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ---- CONFIG ----
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY").encode()

cipher = Fernet(ENCRYPTION_KEY)

# Database Connection
client = MongoClient(MONGO_URI)
db = client["photo_hide_db"]
collection = db["hidden_photos"]

# Initialize Bot
bot = TelegramClient("photo_hide_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)


# ---- HELP COMMAND ----
@bot.on(events.NewMessage(pattern="/help"))
async def help_command(event):
    """Shows how to use the bot."""
    help_text = (
        "**🛠 Photo Hider Bot - Help Guide**\n\n"
        "🔹 **Hide a Photo**: Send any photo to the bot, and it will be stored securely.\n"
        "🔹 **Retrieve a Photo**: Use `/get <your_access_key>` to get your hidden photo.\n"
        "🔹 **Security**: Photos are encrypted and only retrievable using your key.\n"
        "🔹 **Privacy**: Photos are deleted from the bot's storage after saving.\n"
    )
    await event.reply(help_text)


# ---- PHOTO HANDLER ----
@bot.on(events.NewMessage(func=lambda e: e.photo))
async def receive_photo(event):
    """Handles photo uploads and stores them securely, then deletes local copy & message."""
    user_id = event.sender_id
    photo = await event.download_media()  # Save photo locally

    with open(photo, "rb") as file:
        encrypted_photo = cipher.encrypt(file.read())  # Encrypt photo

    access_key = os.urandom(16).hex()  # Generate a unique access key

    # Save to MongoDB
    collection.insert_one({
        "user_id": user_id,
        "photo_data": encrypted_photo,
        "access_key": access_key
    })

    # Delete local copy after storing
    os.remove(photo)

    # ✅ Auto-delete message from Telegram
    await event.delete()

    # Send confirmation message
    await bot.send_message(user_id,
                           f"✅ Your photo is securely stored!\nUse this key to retrieve it: `{access_key}`\n\n📌 Type `/help` for more commands.")


# ---- RETRIEVE PHOTO ----
@bot.on(events.NewMessage(pattern="/get (.+)"))
async def retrieve_photo(event):
    """Retrieves and decrypts a stored photo."""
    access_key = event.pattern_match.group(1)

    record = collection.find_one({"access_key": access_key})

    if record:
        decrypted_photo = cipher.decrypt(record["photo_data"])  # Decrypt photo
        file_path = "retrieved.jpg"

        with open(file_path, "wb") as file:
            file.write(decrypted_photo)

        await event.reply("📸 Here is your hidden photo:", file=file_path)

        # Delete the locally saved retrieved photo
        os.remove(file_path)
    else:
        await event.reply("❌ Invalid key! No photo found.")


# ---- START THE BOT ----
print("Bot is running...")
bot.run_until_disconnected()
