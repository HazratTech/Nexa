from datetime import datetime
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from core.database import Database
from core.models.guild_models import AntiSpamSettings
from core.models.antispam_models import AntiSpamLog

class AntiSpamService:
    @classmethod
    def get_settings_collection(cls) -> AsyncIOMotorCollection:
        return Database.antispam_settings()

    @classmethod
    def get_logs_collection(cls) -> AsyncIOMotorCollection:
        return Database.antispam_logs()

    @classmethod
    async def get_settings(cls, guild_id: int) -> AntiSpamSettings:
        collection = cls.get_settings_collection()
        data = await collection.find_one({"guild_id": {"$in": [guild_id, str(guild_id)]}})
        if data:
            data["guild_id"] = int(data["guild_id"])
            return AntiSpamSettings(**data)
        
        # Create and save default settings
        default_settings = AntiSpamSettings(guild_id=guild_id)
        await collection.insert_one(default_settings.model_dump())
        return default_settings

    @classmethod
    async def update_settings(cls, guild_id: int, **fields) -> bool:
        collection = cls.get_settings_collection()
        fields["updated_at"] = datetime.now()
        
        exists = await collection.find_one({"guild_id": {"$in": [guild_id, str(guild_id)]}})
        if exists:
            result = await collection.update_one(
                {"_id": exists["_id"]},
                {"$set": fields}
            )
            return result.modified_count > 0
        else:
            fields["guild_id"] = guild_id
            result = await collection.insert_one(fields)
            return result.inserted_id is not None

    @classmethod
    async def log_action(cls, log_model: AntiSpamLog) -> bool:
        collection = cls.get_logs_collection()
        result = await collection.insert_one(log_model.to_mongo())
        return result.inserted_id is not None

    @classmethod
    async def get_logs(cls, guild_id: int, user_id: Optional[int] = None, limit: int = 20) -> List[AntiSpamLog]:
        collection = cls.get_logs_collection()
        query = {"guild_id": guild_id}
        if user_id is not None:
            query["user_id"] = user_id
            
        cursor = collection.find(query).sort("created_at", -1).limit(limit)
        results = await cursor.to_list(length=limit)
        return [AntiSpamLog(**item) for item in results]

    @classmethod
    async def get_stats(cls, guild_id: int) -> dict:
        """Runs aggregation pipeline to get summary stats for a guild."""
        collection = cls.get_logs_collection()
        pipeline = [
            {"$match": {"guild_id": guild_id}},
            {"$facet": {
                "violations_by_type": [
                    {"$group": {"_id": "$violation_type", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}}
                ],
                "actions_by_type": [
                    {"$group": {"_id": "$action_taken", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}}
                ],
                "top_offenders": [
                    {"$group": {"_id": "$user_id", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 5}
                ],
                "total_count": [
                    {"$count": "count"}
                ]
            }}
        ]
        results = await collection.aggregate(pipeline).to_list(length=1)
        if results:
            data = results[0]
            total = data.get("total_count", [])
            return {
                "total": total[0]["count"] if total else 0,
                "violations": {item["_id"]: item["count"] for item in data.get("violations_by_type", [])},
                "actions": {item["_id"]: item["count"] for item in data.get("actions_by_type", [])},
                "top_offenders": [(item["_id"], item["count"]) for item in data.get("top_offenders", [])]
            }
        return {"total": 0, "violations": {}, "actions": {}, "top_offenders": []}
