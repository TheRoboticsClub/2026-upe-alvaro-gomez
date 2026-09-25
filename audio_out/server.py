"""Servidor de audio por WebRTC.

Un único servidor aiohttp (sin hilos, todo en el mismo bucle async) hace dos cosas:
  - GET /     sirve la página (index.html)
  - GET /ws   WebSocket de señalización: recibe la oferta SDP del navegador
              y responde con la respuesta SDP

El audio en sí NO pasa por el WebSocket: una vez negociada la conexión,
viaja directamente por WebRTC (RTP/Opus) entre aiortc y el navegador.
"""

import json
from pathlib import Path

from aiohttp import web, WSMsgType
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer

PROJECT_DIR = Path(__file__).parent
AUDIO_PATH = PROJECT_DIR / "file_example_MP3_700KB.mp3"

pcs = set()  # conexiones activas, para poder cerrarlas todas al apagar el servidor


async def index(request: web.Request) -> web.Response:
    """Sirve la página HTML tal cual."""
    html = (PROJECT_DIR / "index.html").read_text()
    return web.Response(content_type="text/html", text=html)


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Señalización: recibe UNA oferta SDP por el socket y responde con la respuesta SDP."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for msg in ws:
        if msg.type != WSMsgType.TEXT:
            continue

        message = json.loads(msg.data)
        if message.get("type") != "offer":
            await ws.send_json({"error": "Se esperaba una oferta SDP"})
            continue

        if not AUDIO_PATH.is_file():
            await ws.send_json({"error": f"No se encuentra: {AUDIO_PATH}"})
            continue

        answer_sdp = await negotiate(message)
        await ws.send_json(answer_sdp)
        break  # una sesión = una negociación; el audio ya no pasa por aquí

    return ws


async def negotiate(offer_message: dict) -> dict:
    """Crea la RTCPeerConnection, le añade el audio y hace el intercambio SDP."""
    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_state_change():
        """Quita la conexión del registro cuando el cliente se desconecta."""
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            pcs.discard(pc)

    # MediaPlayer decodifica el archivo, lo trocea en frames y lo ritma a
    # tiempo real: es funcionalidad de aiortc, no código propio.
    player = MediaPlayer(str(AUDIO_PATH))
    pc.addTrack(player.audio)

    offer = RTCSessionDescription(sdp=offer_message["sdp"], type=offer_message["type"])
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


async def on_shutdown(app: web.Application) -> None:
    """Cierra todas las conexiones WebRTC abiertas al parar el servidor."""
    for pc in list(pcs):
        await pc.close()
    pcs.clear()


def build_app() -> web.Application:
    """Crea la aplicación aiohttp con sus dos rutas."""
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket_handler)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=8000)