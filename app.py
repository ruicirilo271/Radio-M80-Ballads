import asyncio
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, stream_with_context
from imageio_ffmpeg import get_ffmpeg_exe
from shazamio import Shazam

app = Flask(__name__)

RADIO_NAME = "M80 Ballads"
STREAM_URL = os.getenv(
    "M80_STREAM_URL",
    "https://stream-icy.bauermedia.pt/m80ballads.aac",
)
DEFAULT_COVER = "/static/default_cover.svg"
CAPTURE_SECONDS = 11
MIN_AUDIO_BYTES = 120_000

STREAM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "audio/aac,audio/*;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "identity",
    "Icy-MetaData": "0",
    "Cache-Control": "no-cache",
}


def ffmpeg_path() -> str:
    return get_ffmpeg_exe()


def itunes_cover(artist: str, title: str) -> str:
    try:
        response = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": f"{artist} {title}",
                "entity": "song",
                "limit": 5,
                "country": "PT",
            },
            timeout=5,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        artwork = results[0].get("artworkUrl100") if results else None
        return artwork.replace("100x100bb", "600x600bb") if artwork else DEFAULT_COVER
    except Exception:
        return DEFAULT_COVER


def normalize_track(track):
    if not isinstance(track, dict):
        return None

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

    now = int(time.time())
    return {
        "title": title,
        "artist": artist,
        "cover": cover or DEFAULT_COVER,
        "identified_at": now,
        "played_at": now,
    }


def capture_stream(output_file: Path) -> None:
    """Grava uma amostra curta com uma repetição rápida em falhas temporárias."""
    errors = []

    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-user_agent", STREAM_HEADERS["User-Agent"],
        "-headers",
        "Accept: audio/aac,audio/*;q=0.9,*/*;q=0.8\r\n"
        "Icy-MetaData: 0\r\n"
        "Accept-Encoding: identity\r\n",
        "-rw_timeout", "7000000",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_on_network_error", "1",
        "-reconnect_on_http_error", "4xx,5xx",
        "-reconnect_delay_max", "2",
        "-i", STREAM_URL,
        "-t", str(CAPTURE_SECONDS),
        "-vn",
        "-af", "highpass=f=70,lowpass=f=15500,volume=1.4",
        "-ac", "1",
        "-ar", "44100",
        "-c:a", "pcm_s16le",
        str(output_file),
    ]

    for attempt in range(1, 3):
        try:
            output_file.unlink(missing_ok=True)
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=18,
            )

            if output_file.exists() and output_file.stat().st_size >= MIN_AUDIO_BYTES:
                return

            detail = (result.stderr or "O stream não enviou áudio suficiente.").strip()
            errors.append(f"tentativa {attempt}: {detail[-350:]}")
        except subprocess.TimeoutExpired:
            if output_file.exists() and output_file.stat().st_size >= MIN_AUDIO_BYTES:
                return
            errors.append(f"tentativa {attempt}: tempo limite da captura")
        except Exception as exc:
            errors.append(f"tentativa {attempt}: {exc}")

        if attempt == 1:
            time.sleep(1)

    raise RuntimeError(
        "O servidor da M80 não forneceu uma amostra válida. " + " | ".join(errors)
    )


async def recognize_file(audio_file: Path):
    shazam = Shazam()
    result = await asyncio.wait_for(shazam.recognize(str(audio_file)), timeout=16)
    track = result.get("track") if isinstance(result, dict) else None
    return normalize_track(track)


@app.route("/")
def index():
    return render_template(
        "index.html",
        radio_name=RADIO_NAME,
        stream_url="/radio-stream",
    )


@app.route("/radio-stream")
def radio_stream():
    """Proxy de áudio do mesmo domínio para permitir Web Audio/AnalyserNode."""
    try:
        upstream = requests.get(
            STREAM_URL,
            headers=STREAM_HEADERS,
            stream=True,
            timeout=(10, 45),
            allow_redirects=True,
        )
        upstream.raise_for_status()

        content_type = upstream.headers.get("Content-Type", "audio/aac")
        if "audio" not in content_type.lower():
            content_type = "audio/aac"

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=32768):
                    if chunk:
                        yield chunk
            except (requests.RequestException, GeneratorExit):
                return
            finally:
                upstream.close()

        return Response(
            stream_with_context(generate()),
            content_type=content_type,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                "Access-Control-Allow-Origin": "*",
                "Accept-Ranges": "none",
                "X-Accel-Buffering": "no",
            },
            direct_passthrough=True,
        )
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"Não foi possível abrir o stream da M80: {exc}",
        }), 502


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

    except asyncio.TimeoutError:
        return jsonify({
            "ok": False,
            "track": None,
            "error": "O Shazam demorou demasiado tempo a responder.",
        }), 504
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
    response = None
    try:
        response = requests.get(
            STREAM_URL,
            headers=STREAM_HEADERS,
            stream=True,
            timeout=(7, 8),
            allow_redirects=True,
        )
        response.raise_for_status()
        chunk = next(response.iter_content(chunk_size=256), b"")
        return jsonify({
            "ok": bool(chunk),
            "status": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "bytes_received": len(chunk),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    finally:
        if response is not None:
            response.close()


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
        "platform": "vercel" if os.getenv("VERCEL") else "local",
        "radio": RADIO_NAME,
        "stream": STREAM_URL,
        "player_source": "/radio-stream",
        "real_spectrum": True,
        "ffmpeg_available": ffmpeg_available,
        "ffmpeg_path": binary,
        "capture_seconds": CAPTURE_SECONDS,
        "storage": "browser-localStorage",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
