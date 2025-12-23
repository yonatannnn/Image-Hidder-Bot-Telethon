import os

from dotenv import load_dotenv
from cryptography.fernet import Fernet
from pymongo import MongoClient


def main(output_dir: str = "exported_images") -> None:
    """
    Retrieve all encrypted images from MongoDB and save them locally.

    Each document in the `hidden_photos` collection is expected to have:
      - `photo_data`: encrypted bytes
      - `access_key`: unique string used as part of the filename
    """
    load_dotenv()

    mongo_uri = os.getenv("MONGO_URI")
    encryption_key = os.getenv("ENCRYPTION_KEY")

    if not mongo_uri:
        raise RuntimeError("MONGO_URI is not set in the environment (.env).")
    if not encryption_key:
        raise RuntimeError("ENCRYPTION_KEY is not set in the environment (.env).")

    cipher = Fernet(encryption_key.encode())

    client = MongoClient(mongo_uri)
    db = client["photo_hide_db"]
    collection = db["hidden_photos"]

    os.makedirs(output_dir, exist_ok=True)

    count = 0
    skipped = 0
    for doc in collection.find({}):
        photo_data = doc.get("photo_data")
        access_key = doc.get("access_key", f"no_key_{count}")

        if not photo_data:
            continue

        # Use access_key in filename to make it easier to map back if needed
        filename = f"{access_key}.jpg"
        filepath = os.path.join(output_dir, filename)

        # ---- Filter: skip if already downloaded ----
        if os.path.exists(filepath):
            skipped += 1
            continue

        decrypted = cipher.decrypt(photo_data)

        with open(filepath, "wb") as f:
            f.write(decrypted)

        count += 1

    print(f"Saved {count} new images to '{output_dir}', skipped {skipped} already existing files")


if __name__ == "__main__":
    main()


