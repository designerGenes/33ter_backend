import asyncio
import websockets
import sys
from websockets.exceptions import ConnectionClosedError
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

async def send_data(uri, data):
    try:
        async with websockets.connect(uri) as websocket:
            await websocket.send(data)
            print(f"Successfully sent: {data}")
            response = await websocket.recv()
            print(f"Server response: {response}")
    except ConnectionRefusedError:
        print(f"Error: Could not connect to {uri}")
        print("Make sure the WebSocket server is running and the URI is correct")
        sys.exit(1)
    except ConnectionClosedError:
        print("Connection closed unexpectedly")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 publish_to_websocket.py <WebSocket URI> <message>")
        sys.exit(1)

    uri = sys.argv[1]
    data = sys.argv[2]

    asyncio.run(send_data(uri, data))