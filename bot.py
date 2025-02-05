from telethon import TelegramClient, events, Button
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


# ---- START COMMAND ----
@bot.on(events.NewMessage(pattern="/start"))
async def start_command(event):
    """Sends a welcome message when a user starts the bot."""
    if event.out:
        return  # Ignore messages sent by the bot

    welcome_text = (
        "**👋 Welcome to Photo Hider Bot!**\n\n"
        "🔹 Send a **photo**, and it will be **securely stored**.\n"
        "🔹 Retrieve it anytime using your unique **access key**.\n"
        "🔹 Your photos are **encrypted and private**.\n\n"
        "📌 Type `/help` for more commands."
    )

    buttons = [
        [Button.inline("📖 Help", data="help")],
        [Button.inline("🔍 Retrieve Photo", data="retrieve")]
    ]

    await event.respond(welcome_text, buttons=buttons)

# ---- HELP COMMAND ----
@bot.on(events.NewMessage(pattern="/help"))
async def help_command(event):
    """Shows how to use the bot with button options."""
    help_text = (
        "**🛠 Photo Hider Bot - Help Guide**\n\n"
        "🔹 **Hide a Photo**: Send any photo to the bot, and it will be stored securely.\n"
        "🔹 **Retrieve a Photo**: Use `/get <your_access_key>` to get your hidden photo.\n"
        "🔹 **Security**: Photos are encrypted and only retrievable using your key.\n"
        "🔹 **Privacy**: Photos are deleted from the bot's storage after saving.\n"
    )

    buttons = [
        [Button.inline("🔍 Retrieve Photo", data="retrieve")],
        [Button.inline("🏠 Home", data="home")]
    ]

    await event.respond(help_text, buttons=buttons)


# ---- PHOTO HANDLER ----
@bot.on(events.NewMessage(func=lambda e: e.photo and not e.out))
async def receive_photo(event):
    """Handles photo uploads and stores them securely."""
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

    # Send confirmation message with buttons
    buttons = [
        [Button.text("📖 Help", resize=True)],
        [Button.text("🔍 Retrieve Photo", resize=True)]
    ]

    await event.respond(
        f"✅ Your photo is securely stored!\nUse this key to retrieve it: `{access_key}`\n\n📌 Type `/help` for more commands.",
        buttons=buttons
    )

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

        # Send menu buttons after retrieving the image
        buttons = [
            [Button.text("🔍 Retrieve Another Photo", resize=True)],
            [Button.text("📖 Help", resize=True)]
        ]
        await event.respond("ℹ️ Need more help? Click below:", buttons=buttons)

    else:
        await event.reply("❌ Invalid key! No photo found.")

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Handles button clicks."""
    data = event.data.decode("utf-8")
    if data == "help":
        await help_command(event)
    elif data == "retrieve":
        await event.respond("📌 To retrieve a photo, use `/get <your_access_key>`.")
    elif data == "home":
        await start_command(event)


# ---- START THE BOT ----
print("Bot is running...")
bot.run_until_disconnected()
