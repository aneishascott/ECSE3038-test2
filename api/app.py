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