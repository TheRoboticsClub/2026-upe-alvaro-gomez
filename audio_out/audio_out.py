"""Fuentes de audio para el servidor.

Contrato común: toda fuente entrega PCM de 16 bits, mono, 48 kHz, troceado en
frames de exactamente 20 ms (960 muestras = 1920 bytes). Es el formato que
espera la pista de WebRTC (Opus trabaja a 48 kHz con frames de 20 ms), así que
la pista no tiene que convertir nada.

Las fuentes NO controlan el ritmo: entregan frames tan rápido como se les
piden. Quien consume (la pista WebRTC, en el paso 2) decide cuándo pedir el
siguiente frame, cada 20 ms.
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator

import av

SAMPLE_RATE = 48_000
CHANNELS = 1
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000  # 960
BYTES_PER_SAMPLE = 2  # s16
FRAME_BYTES = SAMPLES_PER_FRAME * CHANNELS * BYTES_PER_SAMPLE  # 1920


class FrameChunker:
    """Convierte PCM en trozos de tamaño arbitrario a frames de 20 ms.

    Será reutilizable por la fuente de Piper, que produce audio en bloques
    de tamaño irregular.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def push(self, pcm: bytes) -> list[bytes]:
        self._buffer.extend(pcm)
        frames = []
        while len(self._buffer) >= FRAME_BYTES:
            frames.append(bytes(self._buffer[:FRAME_BYTES]))
            del self._buffer[:FRAME_BYTES]
        return frames

    def flush(self) -> bytes | None:
        """Devuelve el resto pendiente, rellenado con silencio hasta 20 ms."""
        if not self._buffer:
            return None
        frame = bytes(self._buffer).ljust(FRAME_BYTES, b"\x00")
        self._buffer.clear()
        return frame


class AudioSource(ABC):
    """Interfaz común de todas las fuentes de audio."""

    @abstractmethod
    def frames(self) -> AsyncIterator[bytes]:
        """Itera frames PCM (s16, mono, 48 kHz, 20 ms) hasta que la fuente acaba."""

    async def close(self) -> None:
        """Libera recursos. Por defecto no hay nada que liberar."""


class FileAudioSource(AudioSource):
    """Lee un archivo de audio (WAV, MP3, Opus... cualquier cosa que decodifique PyAV)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def frames(self) -> AsyncIterator[bytes]:
        if not self.path.is_file():
            raise FileNotFoundError(f"No se encuentra el archivo: {self.path}")

        chunker = FrameChunker()
        resampler = av.AudioResampler(
            format="s16", layout="mono", rate=SAMPLE_RATE
        )

        with av.open(str(self.path)) as container:
            stream = container.streams.audio[0]
            for decoded in container.decode(stream):
                for resampled in resampler.resample(decoded):
                    for frame in chunker.push(resampled.to_ndarray().tobytes()):
                        yield frame
                # Cede el control al bucle de eventos entre frames decodificados.
                await asyncio.sleep(0)

            # Vacía el remuestreador y el último trozo incompleto.
            for resampled in resampler.resample(None):
                for frame in chunker.push(resampled.to_ndarray().tobytes()):
                    yield frame

        last = chunker.flush()
        if last is not None:
            yield last


if __name__ == "__main__":
    # Comprobación rápida: python audio_source.py archivo.wav
    import sys

    async def check(path: str) -> None:
        count = 0
        async for frame in FileAudioSource(path).frames():
            assert len(frame) == FRAME_BYTES, len(frame)
            count += 1
        print(f"{count} frames de {FRAME_MS} ms = {count * FRAME_MS / 1000:.2f} s")

    asyncio.run(check(sys.argv[1]))