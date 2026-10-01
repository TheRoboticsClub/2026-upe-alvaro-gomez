"""Servidor de audio por WebSocket.

Un único servidor aiohttp (sin hilos) hace tres cosas:
  - GET /                          sirve la página (index.html)
  - GET /pcm-player-worklet.js     sirve el AudioWorklet del cliente
  - GET /ws                        conexión persistente: manda el audio
                                    en fragmentos PCM cada 20 ms

Ya no hay señalización ni WebRTC: el audio viaja directamente por el
WebSocket, en bruto (PCM), en trozos pequeños y a intervalos cortos.
"""

import asyncio
import time
from pathlib import Path

from aiohttp import web, WSMsgType

from audio_source import FRAME_MS, SAMPLE_RATE, SAMPLES_PER_FRAME, file_frames

PROJECT_DIR = Path(__file__).parent
AUDIO_PATH = PROJECT_DIR / "file_example_MP3_700KB.mp3"


async def index(request: web.Request) -> web.Response:
    """Sirve la página HTML tal cual."""
    html = (PROJECT_DIR / "index.html").read_text()
    return web.Response(content_type="text/html", text=html)


async def worklet(request: web.Request) -> web.Response:
    """Sirve el AudioWorklet como JavaScript."""
    js = (PROJECT_DIR / "pcm-player-worklet.js").read_text()
    return web.Response(content_type="application/javascript", text=js)


async def send_paced(ws: web.WebSocketResponse, path: Path) -> None:
    """Manda los frames de un archivo por el WebSocket, uno cada 20 ms reales."""
    start_time = None  # instante real en que empezó el envío
    samples_sent = 0  # muestras mandadas hasta ahora, para calcular el pacing

    async for frame in file_frames(path):
        if ws.closed:
            return

        await ws.send_bytes(frame)
        samples_sent += SAMPLES_PER_FRAME

        if start_time is None:
            start_time = time.time()
            continue

        # Sin esto, como decodificar es más rápido que tiempo real, se
        # mandaría todo el audio de golpe en vez de a ritmo de reproducción.
        target = start_time + samples_sent / SAMPLE_RATE
        delay = target - time.time()
        if delay > 0:
            await asyncio.sleep(delay)


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Cada conexión WebSocket recibe el audio del archivo en streaming."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    if not AUDIO_PATH.is_file():
        await ws.close(message=f"No se encuentra: {AUDIO_PATH}".encode())
        return ws

    send_task = asyncio.create_task(send_paced(ws, AUDIO_PATH))

    async def watch_client():
        """Si el cliente manda algo o cierra, no hay más que hacer aquí."""
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break

    watch_task = asyncio.create_task(watch_client())

    # Terminamos en cuanto pase lo primero: se acaba el archivo, o el
    # cliente se desconecta. Antes solo mirábamos lo segundo, así que el
    # socket se quedaba abierto sin mandar nada más al llegar al final
    # del archivo.
    done, pending = await asyncio.wait(
        {send_task, watch_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()

    if not ws.closed:
        await ws.close()

    return ws


def build_app() -> web.Application:
    """Crea la aplicación aiohttp con sus tres rutas."""
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/pcm-player-worklet.js", worklet)
    app.router.add_get("/ws", websocket_handler)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=8000)