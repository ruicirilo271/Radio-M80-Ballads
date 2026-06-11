import asyncio
import os
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from aiohttp_retry import ExponentialRetry
from flask import Flask, Response, jsonify, render_template, stream_with_context
from imageio_ffmpeg import get_ffmpeg_exe
from shazamio import Shazam
from shazamio.client import HTTPClient

app = Flask(__name__)

RADIO_NAME = "M80 Ballads"
STREAM_URL = os.getenv(
    "M80_STREAM_URL",
    "https://stream-icy.bauermedia.pt/m80ballads.aac",
)
DEFAULT_COVER = "/static/default_cover.svg"

# Uma amostra MP3 pequena reduz escrita no /tmp e o trabalho enviado ao Shazam.
CAPTURE_SECONDS = 12
SHAZAM_SEGMENT_SECONDS = 10
MP3_BITRATE = "128k"
MIN_MP3_BYTES = 80_000

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
    """Binário FFmpeg incluído no pacote imageio-ffmpeg."""
    return get_ffmpeg_exe()


@lru_cache(maxsize=1)
def ffmpeg_supports_mp3() -> bool:
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = f"{result.stdout}\n{result.stderr}".lower()
        return "libmp3lame" in output
    except Exception:
        return False


def itunes_cover(artist: str, title: str) -> str:
    try:
        response = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": f"{artist} {title}",
                "entity": "song",
                "limit": 3,
                "country": "PT",
            },
            timeout=2.5,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        artwork = results[0].get("artworkUrl100") if results else None
        return (
            artwork.replace("100x100bb", "600x600bb")
            if artwork
            else DEFAULT_COVER
        )
    except Exception:
        return DEFAULT_COVER


def normalize_track(track: Any) -> dict[str, Any] | None:
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
    )

    # A resposta do Shazam não fica bloqueada por uma segunda API.
    # Quando não existe capa no resultado, o frontend usa a capa padrão.
    if not cover:
        cover = DEFAULT_COVER

    now = int(time.time())
    return {
        "title": title,
        "artist": artist,
        "cover": cover or DEFAULT_COVER,
        "identified_at": now,
        "played_at": now,
    }


def build_capture_command(output_file: Path, seconds: int) -> list[str]:
    return [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",

        # Cabeçalhos usados pelo servidor ICY da Bauer.
        "-user_agent", STREAM_HEADERS["User-Agent"],
        "-headers",
        "Accept: audio/aac,audio/*;q=0.9,*/*;q=0.8\r\n"
        "Icy-MetaData: 0\r\n"
        "Accept-Encoding: identity\r\n"
        "Connection: close\r\n",

        # Reconexão em falhas temporárias 4XX/5XX.
        "-rw_timeout", "6500000",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_on_network_error", "1",
        "-reconnect_on_http_error", "4xx,5xx",
        "-reconnect_delay_max", "2",

        "-i", STREAM_URL,
        "-t", str(seconds),
        "-vn",

        # Limpeza leve; evita o filtro loudnorm, que é mais pesado em serverless.
        "-af", "highpass=f=70,lowpass=f=15000,volume=1.35",
        "-ac", "1",
        "-ar", "44100",

        # MP3 pequeno e compatível com o recognizer do ShazamIO.
        "-c:a", "libmp3lame",
        "-b:a", MP3_BITRATE,
        "-map_metadata", "-1",
        "-id3v2_version", "0",
        "-write_xing", "0",
        "-f", "mp3",
        str(output_file),
    ]


def capture_stream_mp3(output_file: Path) -> dict[str, Any]:
    """
    Grava uma única amostra MP3 de alta qualidade em /tmp.

    Não faz uma segunda gravação automática. Assim, o utilizador não fica
    à espera de duas amostras consecutivas quando o Shazam não encontra
    correspondência ou quando existe uma falha momentânea do stream.
    """
    output_file.unlink(missing_ok=True)
    command = build_capture_command(output_file, CAPTURE_SECONDS)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        size = output_file.stat().st_size if output_file.exists() else 0

        if size >= MIN_MP3_BYTES:
            return {
                "format": "mp3",
                "bitrate": MP3_BITRATE,
                "sample_rate": 44100,
                "bytes": size,
                "attempt": 1,
                "seconds": CAPTURE_SECONDS,
                "ffmpeg_returncode": "timeout-com-amostra-valida",
            }

        raise RuntimeError(
            "A captura MP3 excedeu o tempo disponível e não produziu "
            f"áudio suficiente ({size} bytes)."
        )

    size = output_file.stat().st_size if output_file.exists() else 0

    # O servidor pode fechar a ligação no fim da amostra e o FFmpeg devolver
    # código diferente de zero, embora o MP3 já esteja completo.
    if size >= MIN_MP3_BYTES:
        return {
            "format": "mp3",
            "bitrate": MP3_BITRATE,
            "sample_rate": 44100,
            "bytes": size,
            "attempt": 1,
            "seconds": CAPTURE_SECONDS,
            "ffmpeg_returncode": result.returncode,
        }

    detail = (
        result.stderr
        or result.stdout
        or "O stream não enviou áudio MP3 suficiente."
    ).strip()

    raise RuntimeError(
        "Não foi possível criar uma amostra MP3 válida da M80. "
        f"Tamanho: {size} bytes. Detalhe: {detail[-600:]}"
    )

async def recognize_mp3(audio_file: Path) -> dict[str, Any] | None:
    """
    Lê o MP3 para memória e entrega bytes ao ShazamIO.

    O cliente do ShazamIO é limitado a poucas tentativas para não ficar preso
    durante demasiado tempo numa Function serverless.
    """
    audio_bytes = audio_file.read_bytes()
    if len(audio_bytes) < MIN_MP3_BYTES:
        raise RuntimeError("A amostra MP3 ficou demasiado pequena para identificar.")

    retry_options = ExponentialRetry(
        attempts=2,
        max_timeout=2,
        statuses={429, 500, 502, 503, 504},
    )
    http_client = HTTPClient(retry_options=retry_options)
    shazam = Shazam(
        http_client=http_client,
        segment_duration_seconds=SHAZAM_SEGMENT_SECONDS,
    )

    result = await asyncio.wait_for(
        shazam.recognize(audio_bytes),
        timeout=14,
    )

    track = result.get("track") if isinstance(result, dict) else None
    return normalize_track(track)


@app.after_request
def no_cache_api(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


@app.route("/")
def index():
    return render_template(
        "index.html",
        radio_name=RADIO_NAME,
        stream_url=STREAM_URL,
        spectrum_stream_url="/radio-spectrum-stream",
    )


@app.route("/radio-stream")
@app.route("/radio-spectrum-stream")
def radio_stream():
    """
    Proxy apenas para o spectrum real.

    O áudio audível continua a usar diretamente o stream oficial no JavaScript,
    evitando que a rádio pare quando a Function de streaming terminar.
    """
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
    started = time.perf_counter()
    timings: dict[str, float] = {}
    stage = "preparar"
    stamp = f"{os.getpid()}_{int(time.time() * 1000)}"
    audio_file = Path(tempfile.gettempdir()) / f"m80_{stamp}.mp3"

    try:
        stage = "capturar_mp3"
        phase = time.perf_counter()
        sample = capture_stream_mp3(audio_file)
        timings["capture"] = round(time.perf_counter() - phase, 3)

        stage = "shazam"
        phase = time.perf_counter()
        track = asyncio.run(recognize_mp3(audio_file))
        timings["shazam"] = round(time.perf_counter() - phase, 3)
        timings["total"] = round(time.perf_counter() - started, 3)

        if not track:
            return jsonify({
                "ok": False,
                "track": None,
                "stage": "shazam_sem_correspondencia",
                "sample": sample,
                "timings": timings,
                "error": (
                    "O Shazam recebeu a amostra MP3, mas não reconheceu esta "
                    "parte da emissão. Tenta novamente dentro de alguns segundos."
                ),
            }), 422

        return jsonify({
            "ok": True,
            "track": track,
            "sample": sample,
            "timings": timings,
        })

    except asyncio.TimeoutError:
        timings["total"] = round(time.perf_counter() - started, 3)
        return jsonify({
            "ok": False,
            "track": None,
            "stage": stage,
            "timings": timings,
            "error": "O pedido ao Shazam excedeu o tempo disponível.",
        }), 504

    except Exception as exc:
        timings["total"] = round(time.perf_counter() - started, 3)
        return jsonify({
            "ok": False,
            "track": None,
            "stage": stage,
            "timings": timings,
            "error": f"{type(exc).__name__}: {exc}",
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


@app.route("/api/identify-diagnostics")
def identify_diagnostics():
    temp_test = Path(tempfile.gettempdir()) / f"m80_tmp_test_{os.getpid()}.txt"
    tmp_writable = False
    tmp_error = None

    try:
        temp_test.write_text("ok", encoding="utf-8")
        tmp_writable = temp_test.read_text(encoding="utf-8") == "ok"
    except Exception as exc:
        tmp_error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            temp_test.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        binary = ffmpeg_path()
        ffmpeg_available = bool(binary and Path(binary).exists())
    except Exception as exc:
        binary = None
        ffmpeg_available = False
        tmp_error = tmp_error or f"FFmpeg: {type(exc).__name__}: {exc}"

    return jsonify({
        "ok": ffmpeg_available and tmp_writable and ffmpeg_supports_mp3(),
        "platform": "vercel" if os.getenv("VERCEL") else "local",
        "tmp_directory": tempfile.gettempdir(),
        "tmp_writable": tmp_writable,
        "tmp_error": tmp_error,
        "ffmpeg_available": ffmpeg_available,
        "ffmpeg_path": binary,
        "mp3_encoder": ffmpeg_supports_mp3(),
        "sample_format": "mp3",
        "capture_seconds": CAPTURE_SECONDS,
        "shazam_segment_seconds": SHAZAM_SEGMENT_SECONDS,
        "mp3_bitrate": MP3_BITRATE,
        "sample_rate": 44100,
        "minimum_sample_bytes": MIN_MP3_BYTES,
    })


@app.route("/api/warmup")
def warmup():
    """Inicializa o caminho do FFmpeg sem gravar áudio."""
    started = time.perf_counter()

    try:
        binary = ffmpeg_path()
        available = bool(binary and Path(binary).exists())
        return jsonify({
            "ok": available,
            "ffmpeg_available": available,
            "elapsed": round(time.perf_counter() - started, 3),
        })
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed": round(time.perf_counter() - started, 3),
        }), 503


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
        "player_source": "direct-official-stream",
        "spectrum_source": "/radio-spectrum-stream",
        "real_spectrum": True,
        "automatic_spectrum_reconnect": True,
        "identification_sample": "mp3",
        "ffmpeg_available": ffmpeg_available,
        "ffmpeg_path": binary,
        "capture_seconds": CAPTURE_SECONDS,
        "shazam_segment_seconds": SHAZAM_SEGMENT_SECONDS,
        "mp3_bitrate": MP3_BITRATE,
        "sample_rate": 44100,
        "tmp_directory": tempfile.gettempdir(),
        "storage": "browser-localStorage",
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        threaded=True,
    )
