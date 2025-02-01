
import asyncio
import socketio
import json
import os

class AutomaticSocketClient:
    def __init__(self):
        self.sio = socketio.AsyncClient()
        self.room = "cheddarbox_room"
        self.ip, self.port = self.load_server_details()
        self.setup_events()

    def load_server_details(self):
        run_mode = os.getenv("RUN_MODE", "local").lower()
        config_path = "/app/server_config.json" if run_mode == "docker" else os.path.join(os.getcwd(), "server_config.json")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found at {config_path}")
        with open(config_path, "r") as f:
            config = json.load(f)
        return config["ip"], config["port"]

    def setup_events(self):
        @self.sio.event
        async def connect():
            print(f"Connected to server at {self.ip}:{self.port}")
            await self.sio.emit("join_room", {"room": self.room})
            print(f"Joined room: {self.room}")

        @self.sio.event
        async def disconnect():
            print("Disconnected from server")

        @self.sio.event
        async def room_message(data):
            print("Received room message:")
            print(json.dumps(data, indent=2))

    async def run(self):
        try:
            await self.sio.connect(f"http://{self.ip}:{self.port}")
            await self.sio.wait()
        except Exception as e:
            print(f"Connection error: {e}")

if __name__ == "__main__":
    client = AutomaticSocketClient()
    asyncio.run(client.run())