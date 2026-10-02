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
import wave
from pathlib import Path

from aiohttp import web, WSMsgType
from piper import PiperVoice

from audio_source import FRAME_MS, SAMPLE_RATE, SAMPLES_PER_FRAME, file_frames
from piper_source import text_frames

PROJECT_DIR = Path(__file__).parent
# Archivos que no vienen incluidos en los requerimientos del proyecto
#AUDIO_PATH = PROJECT_DIR / "file_example_MP3_700KB.mp3"
PIPER_MODEL_PATH = PROJECT_DIR / "es_ES-carlfm-x_low.onnx"
PIPER_CONFIG_PATH = PROJECT_DIR / "es_ES-carlfm-x_low.onnx.json"
PIPER_TEXT_PATH = PROJECT_DIR / "input.txt"

voice: PiperVoice | None = None

#voice = PiperVoice.load(PIPER_MODEL_PATH)
#with wave.open("test.wav", "wb") as wav_file:
#    voice.synthesize_wav("Prueba para Piper. Esto no es un simulacro.", wav_file)


async def index(request: web.Request) -> web.Response:
    """Sirve la página HTML tal cual."""
    html = (PROJECT_DIR / "index.html").read_text()
    return web.Response(content_type="text/html", text=html)


async def worklet(request: web.Request) -> web.Response:
    """Sirve el AudioWorklet como JavaScript."""
    js = (PROJECT_DIR / "pcm-player-worklet.js").read_text()
    return web.Response(content_type="application/javascript", text=js)


async def send_paced(ws: web.WebSocketResponse, frames) -> None:
    """Manda los frames por el WebSocket, uno cada 20 ms reales."""
    start_time = None  # instante real en que empezó el envío
    samples_sent = 0  # muestras mandadas hasta ahora, para calcular el pacing

    async for frame in frames:
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

    if not PIPER_TEXT_PATH.is_file():
        await ws.send_json({"error": f"No se encuentra: {PIPER_TEXT_PATH}"})
        await ws.close()
        return ws

    text = PIPER_TEXT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        await ws.send_json({"error": f"{PIPER_TEXT_PATH} está vacío"})
        await ws.close()
        return ws

    await ws.send_json({"status": "synthesizing"})
    await send_paced(ws, text_frames(text, voice))
    await ws.send_json({"status": "done"})
    await ws.close()

    return ws



def build_app() -> web.Application:
    """Crea la aplicación aiohttp con sus tres rutas, y carga la voz de Piper."""
    global voice
    voice = PiperVoice.load(str(PIPER_MODEL_PATH), config_path=str(PIPER_CONFIG_PATH))

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/pcm-player-worklet.js", worklet)
    app.router.add_get("/ws", websocket_handler)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=8000)



# python -m pip install piper-tts
#
# import wave
# from piper import PiperVoice
#
# voice = PiperVoice.load("/path/to/en_US-lessac-medium.onnx")
# with wave.open("test.wav", "wb") as wav_file:
#     voice.synthesize_wav("Welcome to the world of speech synthesis!", wav_file)
#
# Adjust synthesis:
# syn_config = SynthesisConfig(
#     volume=0.5,  # half as loud
#     length_scale=2.0,  # twice as slow
#     noise_scale=1.0,  # more audio variation
#     noise_w_scale=1.0,  # more speaking variation
#     normalize_audio=False, # use raw audio from voice
# )
#
# voice.synthesize_wav(..., syn_config=syn_config)