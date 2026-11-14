import json, os, secrets
from datetime import datetime, timezone
from typing import Literal
import paho.mqtt.publish as publish
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from pymongo import MongoClient

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"), tz_aware=True)
db = client["test2"]
fans     = db["fans"]
readings = db["readings"]
settings = db["settings"]

MQTT_HOST = "135.232.203.144"
MQTT_PORT = 1883
MQTT_NAME = os.getenv("MQTT_NAME", "yourname")

app = FastAPI()

class FanIn(BaseModel):
    mac: str
    room: str

class ReadingIn(BaseModel):
    mac: str
    humidity: float = Field(ge=0, le=100)

class SettingsIn(BaseModel):
    mode: Literal["auto", "on", "off"]
    max_humidity: float = Field(ge=0, le=100)

def check_key(x_api_key: str | None, mac: str):
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    owner = fans.find_one({"key": x_api_key})
    if owner is None:
        raise HTTPException(status_code=401, detail="Unknown API key")
    if owner["mac"] != mac:
        raise HTTPException(status_code=403, detail="Key belongs to another fan")

@app.post("/fans", status_code=201)
def create_fan(fan: FanIn):
    if fans.find_one({"mac": fan.mac}):
        raise HTTPException(409, "Fan already exists")
    key = secrets.token_urlsafe(16)
    fans.insert_one({"mac": fan.mac, "room": fan.room, "key": key})
    return {"mac": fan.mac, "room": fan.room, "key": key}

@app.get("/fans")
def list_fans():
    return list(fans.find({}, {"_id": 0, "key": 0}))

@app.get("/fans/{mac}")
def get_fan(mac: str):
    fan = fans.find_one({"mac": mac}, {"_id": 0, "key": 0})
    if not fan:
        raise HTTPException(404, "No fan with MAC " + mac)
    return fan

@app.post("/readings", status_code=201)
def create_reading(reading: ReadingIn,
                   x_api_key: str | None = Header(default=None)):
    check_key(x_api_key, reading.mac)
    doc = reading.model_dump()
    doc["time"] = datetime.now(timezone.utc)
    readings.insert_one(doc)
    doc.pop("_id")
    return doc

@app.get("/readings")
def get_readings(mac: str | None = None,
                 limit: int = Query(default=10, ge=1, le=100)):
    query = {"mac": mac} if mac else {}
    return list(readings.find(query, {"_id": 0}).sort("time", -1).limit(limit))

@app.put("/fans/{mac}/settings")
def put_settings(mac: str, new_settings: SettingsIn, response: Response):
    if not fans.find_one({"mac": mac}):
        raise HTTPException(404, "No fan with MAC " + mac)
    result = settings.update_one(
        {"mac": mac},
        {"$set": {"mode": new_settings.mode,
                  "max_humidity": new_settings.max_humidity}},
        upsert=True)
    response.status_code = 201 if result.upserted_id else 200
    payload = json.dumps({"mode": new_settings.mode,
                          "max_humidity": new_settings.max_humidity})
    topic = f"ecse3038/{MQTT_NAME}/fan/settings"
    try:
        publish.single(topic, payload, qos=1, retain=True,
                       hostname=MQTT_HOST, port=MQTT_PORT)
    except Exception as e:
        print("MQTT error:", e)
    return {"mac": mac, "mode": new_settings.mode,
            "max_humidity": new_settings.max_humidity}