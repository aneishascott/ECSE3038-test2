# ECSE3038 Test 2: the bathroom fan

An ESP32 in Wokwi reads a DHT22 humidity every 10 s and POSTs it,
with its own API key, to a FastAPI server backed by MongoDB Atlas.
PUT /fans/{mac}/settings sets the mode (auto, on, off) and
max_humidity; the API publishes them as JSON retained on the class
MQTT broker, and the board drives the fan LED from them.

## Run the API
    cd api
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    # create .env: MONGODB_URI=... and MQTT_NAME=<name>
    uvicorn app:app --reload

## Run the board
1. Open board/ in VS Code with PlatformIO.
2. Create include/secrets.h: #define DEVICE_KEY ""
3. Set API_URL and MQTT_NAME in src/main.cpp.
4. Build, start Wokwi. Copy MAC from Serial Monitor.
5. POST /fans with that MAC; paste the key into secrets.h; rebuild.