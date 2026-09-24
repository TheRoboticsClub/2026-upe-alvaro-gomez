# Audio completo por WebSocket

Primera fase del proyecto: un servidor Python lee un archivo MP3 local, lo envía
completo al navegador mediante WebSocket y el navegador lo reproduce usando el
reproductor de audio HTML.

Esta versión **no es streaming continuo**. El navegador espera a recibir el
archivo completo antes de comenzar la reproducción.

## Requisitos

- Python 3.
- Un navegador moderno con soporte para WebSocket y MP3.
- El archivo `file_example_MP3_700KB.mp3` que se provee en la raíz de este proyecto.

## Archivos

- `server.py`: inicia el servidor HTTP y el servidor WebSocket.
- `index.html`: interfaz web y lógica del cliente WebSocket.
- `file_example_MP3_700KB.mp3`: archivo de audio que lee el servidor.
- `requirements.txt`: lista la librería Python externa necesaria.

## ¿Es necesario `requirements.txt`?

Sí. `server.py` utiliza la librería `websockets` mediante esta importación:

```python
import websockets
```

`websockets` no forma parte de la biblioteca estándar de Python. Por eso
`requirements.txt` permite instalar la dependencia de forma reproducible. Su
contenido actual es:

```text
websockets>=12,<16
```

No es necesario instalar una librería para el cliente web: `WebSocket`, `Blob`,
`URL.createObjectURL` y el elemento `<audio>` son APIs incorporadas al navegador.

## Instalación

Abre un terminal en la carpeta del proyecto:

```bash
cd /home/rh/Documentos/audio_out
```

Crea un entorno virtual. Esto mantiene las dependencias de este proyecto
separadas de las instalaciones globales de Python:

```bash
python3 -m venv .venv
```

Activa el entorno virtual:

```bash
source .venv/bin/activate
```

Instala la dependencia del servidor:

```bash
python -m pip install -r requirements.txt
```

El entorno virtual solo tiene que crearse una vez. En las siguientes sesiones
basta con volver a activar `.venv`.

## Ejecución

Con el entorno virtual activado, ejecuta:

```bash
python server.py
```

El servidor mostrará dos direcciones:

- `http://127.0.0.1:8000`: página web.
- `ws://127.0.0.1:8765`: conexión WebSocket.

Abre `http://127.0.0.1:8000` en el navegador y pulsa **Conectar y recibir
audio**. El botón inicia la conexión y constituye una interacción del usuario,
lo que permite al navegador reproducir el sonido sin bloquearlo por sus
políticas de reproducción automática.

Para detener el servidor, vuelve al terminal donde está ejecutándose y pulsa
`Ctrl+C`.

## Qué ocurre en el servidor

`server.py` ejecuta dos servicios al mismo tiempo:

1. Un servidor HTTP sirve `index.html` desde la carpeta del proyecto.
2. Un servidor WebSocket escucha conexiones en el puerto `8765`.

Cuando un navegador se conecta por WebSocket, el servidor:

1. Comprueba que existe `file_example_MP3_700KB.mp3`.
2. Lee todo el archivo en memoria con `read_bytes()`.
3. Envía un mensaje JSON con el nombre, el tipo MIME y el tamaño.
4. Envía el contenido completo del MP3 como un mensaje binario.
5. Envía un último mensaje JSON indicando que ha terminado.

El protocolo actual es, por tanto:

```text
JSON audio_start
datos binarios del MP3 completo
JSON audio_end
```

Si el archivo no existe, se envía en su lugar un mensaje JSON de tipo `error`.

## Qué ocurre en el navegador

El cliente crea una conexión con:

```javascript
const socket = new WebSocket('ws://127.0.0.1:8765');
```

Como el servidor envía el audio en binario, el cliente configura:

```javascript
socket.binaryType = 'arraybuffer';
```

Los mensajes de texto se interpretan como JSON. Cuando llega el mensaje
binario:

1. Se crea un `Blob` con tipo `audio/mpeg`.
2. `URL.createObjectURL()` crea una URL temporal para ese `Blob`.
3. La URL se asigna al atributo `src` del elemento HTML `<audio>`.
4. El navegador decodifica el MP3 y lo envía a la salida de audio configurada
	en el sistema.

La cadena completa es:

```text
WebSocket -> ArrayBuffer -> Blob -> URL temporal -> <audio> -> altavoces
```

No se utilizan WebRTC, `AudioContext`, `AudioWorklet` ni `MediaSource` en esta
primera fase.


## Próxima ampliación

Para convertir esta versión en envío continuo no bastará con enviar muchos
mensajes MP3 arbitrarios: el cliente necesitará una estrategia de buffer y
reproducción progresiva. La conexión WebSocket y los mensajes de control pueden
mantenerse, sustituyendo el único mensaje binario completo por varios bloques.
