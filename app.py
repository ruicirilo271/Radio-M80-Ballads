import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template
from imageio_ffmpeg import get_ffmpeg_exe
from shazamio import Shazam

app = Flask(__name__)

RADIO_NAME = "M80 Ballads"
STREAM_URL = os.getenv(
    "M80_STREAM_URL",
    "https://stream-icy.bauermedia.pt/m80ballads.aac",
)
DEFAULT_COVER = "/static/default_cover.svg"
CAPTURE_SECONDS = 18


def ffmpeg_path():
    """Usa o binário incluído pelo imageio-ffmpeg na Function da Vercel."""
    return get_ffmpeg_exe()


def itunes_cover(artist, title):
    try:
        response = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": f"{artist} {title}",
                "entity": "song",
                "limit": 5,
                "country": "PT",
            },
            timeout=6,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        artwork = results[0].get("artworkUrl100") if results else None
        return artwork.replace("100x100bb", "600x600bb") if artwork else DEFAULT_COVER
    except Exception:
        return DEFAULT_COVER


def normalize_track(track):
    title = str(track.get("title") or "").strip()
    artist = str(track.get("subtitle") or track.get("artist") or "").strip()
    if not title:
        return None
    if not artist:
        artist = "Artista desconhecido"

    images = track.get("images") or {}
    cover = (
        images.get("coverarthq")
        or images.get("coverart")
        or images.get("background")
        or itunes_cover(artist, title)
    )

    return {
        "title": title,
        "artist": artist,
        "cover": cover or DEFAULT_COVER,
        "identified_at": int(time.time()),
        "played_at": int(time.time()),
    }


def capture_stream(output_file):
    """Captura uma amostra curta. Duas tentativas cabem no limite Hobby."""
    errors = []
    command_base = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36",
        "-headers", "Accept: audio/aac,audio/*;q=0.9,*/*;q=0.8\r\nIcy-MetaData: 0\r\nAccept-Encoding: identity\r\n",
        "-rw_timeout", "9000000",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_on_network_error", "1",
        "-reconnect_on_http_error", "4xx,5xx",
        "-reconnect_delay_max", "3",
        "-i", STREAM_URL,
        "-t", str(CAPTURE_SECONDS),
        "-vn",
        "-af", "highpass=f=80,lowpass=f=15000,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ac", "1",
        "-ar", "44100",
        "-c:a", "pcm_s16le",
        str(output_file),
    ]

    for attempt in range(1, 3):
        try:
            output_file.unlink(missing_ok=True)
            result = subprocess.run(
                command_base,
                capture_output=True,
                text=True,
                timeout=27,
            )
            if output_file.exists() and output_file.stat().st_size >= 180000:
                return
            detail = (result.stderr or "O stream não enviou áudio suficiente.").strip()
            errors.append(f"tentativa {attempt}: {detail[-500:]}")
        except subprocess.TimeoutExpired:
            errors.append(f"tentativa {attempt}: tempo limite da captura")

        if attempt == 1:
            time.sleep(2)

    raise RuntimeError(
        "O servidor da M80 não forneceu uma amostra válida. " + " | ".join(errors)
    )


async def recognize_file(audio_file):
    shazam = Shazam()
    result = await shazam.recognize(str(audio_file))
    track = result.get("track") if isinstance(result, dict) else None
    return normalize_track(track) if track else None


@app.route("/")
def index():
    return render_template(
        "index.html",
        radio_name=RADIO_NAME,
        stream_url=STREAM_URL,
    )


@app.route("/api/identify", methods=["POST"])
def identify():
    stamp = f"{os.getpid()}_{int(time.time() * 1000)}"
    audio_file = Path(tempfile.gettempdir()) / f"m80_{stamp}.wav"

    try:
        capture_stream(audio_file)
        track = asyncio.run(recognize_file(audio_file))
        if not track:
            return jsonify({
                "ok": False,
                "track": None,
                "error": "O Shazam não reconheceu esta parte da emissão. Tenta novamente dentro de alguns segundos.",
            }), 422

        return jsonify({"ok": True, "track": track})

    except Exception as exc:
        return jsonify({
            "ok": False,
            "track": None,
            "error": str(exc) or "Erro desconhecido durante a identificação.",
        }), 503
    finally:
        try:
            audio_file.unlink(missing_ok=True)
        except Exception:
            pass


@app.route("/api/stream-check")
def stream_check():
    try:
        response = requests.get(
            STREAM_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Icy-MetaData": "0",
                "Accept-Encoding": "identity",
            },
            stream=True,
            timeout=(7, 7),
        )
        response.raise_for_status()
        chunk = next(response.iter_content(chunk_size=128), b"")
        status = response.status_code
        content_type = response.headers.get("Content-Type", "")
        response.close()
        return jsonify({
            "ok": bool(chunk),
            "status": status,
            "content_type": content_type,
            "bytes_received": len(chunk),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@app.route("/health")
def health():
    try:
        binary = ffmpeg_path()
        ffmpeg_available = bool(binary and Path(binary).exists())
    except Exception:
        binary = None
        ffmpeg_available = False

    return jsonify({
        "ok": True,
        "platform": "vercel",
        "radio": RADIO_NAME,
        "stream": STREAM_URL,
        "ffmpeg_available": ffmpeg_available,
        "ffmpeg_path": binary,
        "capture_seconds": CAPTURE_SECONDS,
        "storage": "browser-localStorage",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
