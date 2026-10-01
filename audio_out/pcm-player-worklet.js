// AudioWorkletProcessor: reproduce, sin cortes, los trozos de audio que van
// llegando por WebSocket. Corre en su propio hilo de audio en tiempo real,
// separado del hilo principal del navegador.

class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = []; // cola de trozos (Float32Array) pendientes de reproducir
    this.offset = 0; // por dónde vamos dentro del primer trozo de la cola

    // El hilo principal nos manda trozos de audio por este puerto.
    this.port.onmessage = (event) => {
      this.queue.push(event.data);
    };
  }

  // El navegador llama a esto muy a menudo (cada ~128 muestras) para pedir
  // el siguiente bloque de audio a reproducir.
  process(_inputs, outputs) {
    const output = outputs[0][0];
    let written = 0;

    while (written < output.length) {
      if (this.queue.length === 0) {
        // No ha llegado audio a tiempo: rellenamos con silencio en vez de cortar.
        output[written++] = 0;
        continue;
      }

      const chunk = this.queue[0];
      const available = chunk.length - this.offset;
      const toCopy = Math.min(available, output.length - written);

      output.set(chunk.subarray(this.offset, this.offset + toCopy), written);
      this.offset += toCopy;
      written += toCopy;

      if (this.offset >= chunk.length) {
        this.queue.shift();
        this.offset = 0;
      }
    }

    return true; // seguir vivo para el siguiente bloque
  }
}

registerProcessor('pcm-player', PCMPlayerProcessor);