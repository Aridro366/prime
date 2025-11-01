# utils/db.py
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = AsyncIOMotorClient(MONGO_URI)
db = client["PrimeBot"]

# Example collections
warnings = db["warnings"]
configs = db["configs"]

async def add_warning(user_id: int, guild_id: int, reason: str):
    await warnings.insert_one({"user_id": user_id, "guild_id": guild_id, "reason": reason})

async def get_warnings(user_id: int, guild_id: int):
    return await warnings.find({"user_id": user_id, "guild_id": guild_id}).to_list(None)
