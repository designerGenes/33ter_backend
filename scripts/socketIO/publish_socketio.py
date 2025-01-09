import asyncio
import socketio
import json
import sys 

# Load server details from the config file
def load_server_details():
    try:
        with open("server_config.json", "r") as f:
            config = json.load(f)
            return config["ip"], config["port"], config["room"]
    except Exception as e:
        print(f"Error loading server details: {e}")
        exit(1)

async def send_data(ip, port, room, message):
    try:
        # Create a Socket.IO client
        sio = socketio.AsyncClient()

        # Connect to the server
        await sio.connect(f"http://{ip}:{port}")
        print(f"Connected to server at http://{ip}:{port}")

        # Join the room
        await sio.emit("join_room", {"room": room})
        print(f"Joined room: {room}")

        # Prepare the message in the correct format
        message_data = {
            "room": room,
            "message": {
                "plainText": message,
                "codeBlock": """
Write a function that takes an array of integers and returns a new array where:
    •    Numbers divisible by 3 are replaced with "Fizz".
    •    Numbers divisible by 5 are replaced with "Buzz".
    •    Numbers divisible by both 3 and 5 are replaced with "FizzBuzz".
    •    Other numbers remain unchanged.

import Foundation

func fizzBuzzTransform(_ numbers: [Int]) -> [Any] {
    return numbers.map { number in
        if number % 3 == 0 && number % 5 == 0 {
            return "FizzBuzz"
        } else if number % 3 == 0 {
            return "Fizz"
        } else if number % 5 == 0 {
            return "Buzz"
        } else {
            return number
        }
    }
}
"""
            }
        }

        # Send the message to the room
        await sio.emit("room_message", message_data)
        print(f"Sent message to room {room}: {json.dumps(message_data, indent=2)}")

        # Wait for a response (optional)
        @sio.event
        async def message(data):
            print(f"Received response from server: {data}")
            await sio.disconnect()

        # Keep the connection alive for a while
        await asyncio.sleep(2)

    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)
    finally:
        await sio.disconnect()

if __name__ == "__main__":
    # Load server details from the config file
    ip, port, room = load_server_details()

    # Get the message from the command line
    if len(sys.argv) < 2:
        print("Usage: python3 publish_socketio.py <message>")
        exit(1)
    message = sys.argv[1]

    # Send the message
    asyncio.run(send_data(ip, port, room, message))