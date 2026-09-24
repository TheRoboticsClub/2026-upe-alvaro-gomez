import asyncio
import json
import mimetypes
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets

PROJECT_DIR = Path(__file__).parent
AUDIO_PATH = PROJECT_DIR / "file_example_MP3_700KB.mp3"
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8000
WEBSOCKET_HOST = "127.0.0.1"
WEBSOCKET_PORT = 8765


class WebHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)

    def log_message(self, format, *args):
        pass


async def send_audio(websocket):
    if not AUDIO_PATH.is_file():
        await websocket.send(json.dumps({
            "type": "error",
            "message": f"No se encuentra el archivo: {AUDIO_PATH}",
        }))
        return

    audio_data = AUDIO_PATH.read_bytes()
    mime_type = mimetypes.guess_type(AUDIO_PATH.name)[0] or "application/octet-stream"

    await websocket.send(json.dumps({
        "type": "audio_start",
        "filename": AUDIO_PATH.name,
        "mime": mime_type,
        "size": len(audio_data),
    }))
    await websocket.send(audio_data)
    await websocket.send(json.dumps({"type": "audio_end"}))


async def websocket_handler(websocket):
    await send_audio(websocket)
    await websocket.wait_closed()


def run_http_server():
    server = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), WebHandler)
    print(f"Página web: http://{HTTP_HOST}:{HTTP_PORT}")
    server.serve_forever()


async def main():
    if not AUDIO_PATH.is_file():
        print(f"Aviso: coloca el audio en {AUDIO_PATH}")

    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    async with websockets.serve(
        websocket_handler,
        WEBSOCKET_HOST,
        WEBSOCKET_PORT,
    ):
        print(f"WebSocket: ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Servidor detenido")
