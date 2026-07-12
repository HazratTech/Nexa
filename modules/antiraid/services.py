from datetime import datetime
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from core.database import Database
from core.models.guild_models import AntiRaidSettings
from core.models.antispam_models import AntiRaidIncident

class AntiRaidService:
    @classmethod
    def get_settings_collection(cls) -> AsyncIOMotorCollection:
        return Database.antiraid_settings()

    @classmethod
    def get_incidents_collection(cls) -> AsyncIOMotorCollection:
        return Database.antiraid_incidents()

    @classmethod
    async def get_settings(cls, guild_id: int) -> AntiRaidSettings:
        collection = cls.get_settings_collection()
        data = await collection.find_one({"guild_id": guild_id})
        if data:
            return AntiRaidSettings(**data)
        
        # Create and save default settings
        default_settings = AntiRaidSettings(guild_id=guild_id)
        await collection.insert_one(default_settings.model_dump())
        return default_settings

    @classmethod
    async def update_settings(cls, guild_id: int, **fields) -> bool:
        collection = cls.get_settings_collection()
        fields["updated_at"] = datetime.now()
        result = await collection.update_one(
            {"guild_id": guild_id},
            {"$set": fields},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    @classmethod
    async def log_incident(cls, incident: AntiRaidIncident) -> str:
        collection = cls.get_incidents_collection()
        result = await collection.insert_one(incident.to_mongo())
        return str(result.inserted_id)

    @classmethod
    async def get_incidents(cls, guild_id: int, limit: int = 10) -> List[AntiRaidIncident]:
        collection = cls.get_incidents_collection()
        cursor = collection.find({"guild_id": guild_id}).sort("created_at", -1).limit(limit)
        results = await cursor.to_list(length=limit)
        return [AntiRaidIncident(**item) for item in results]

    @classmethod
    async def resolve_incident(cls, incident_id_str: str, auto_resolved: bool = True) -> bool:
        """Mark an incident as resolved/de-escalated."""
        from bson import ObjectId
        try:
            obj_id = ObjectId(incident_id_str)
        except Exception:
            return False
            
        collection = cls.get_incidents_collection()
        result = await collection.update_one(
            {"_id": obj_id},
            {"$set": {
                "auto_resolved": auto_resolved,
                "resolved_at": datetime.now(),
                "updated_at": datetime.now()
            }}
        )
        return result.modified_count > 0
