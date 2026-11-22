#!/usr/bin/env python3
"""Local OpenWhispr ASR shim using the Sichuan/Chongqing Paraformer model."""

from __future__ import annotations

import array
import json
import os
import re
import subprocess
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sherpa_onnx


PORT = int(os.environ.get("SHIM_PORT", "8765"))
HOST = os.environ.get("SHIM_HOST", "127.0.0.1")
MAX_BODY_BYTES = 25 * 1024 * 1024

MODEL_DIR = Path(os.environ.get(
    "PARAFORMER_MODEL_DIR",
    "./sherpa-onnx-paraformer-zh-int8-2025-10-07",
)).expanduser().resolve()

MODEL_PATH = MODEL_DIR / "model.int8.onnx"
TOKENS_PATH = MODEL_DIR / "tokens.txt"
NUM_THREADS = int(os.environ.get("SHERPA_NUM_THREADS", "2"))

# [新增] 中文标点恢复模型配置
PUNCTUATION_MODEL_DIR = Path(os.environ.get(
    "PUNCTUATION_MODEL_DIR",
    "./sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8",
)).expanduser().resolve()

PUNCTUATION_MODEL_PATH = PUNCTUATION_MODEL_DIR / "model.int8.onnx"


def create_recognizer():
    """Load the offline Sichuan/Chongqing Paraformer once at startup."""
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")
    if not TOKENS_PATH.is_file():
        raise FileNotFoundError(f"Tokens file not found: {TOKENS_PATH}")

    print(f"Loading Paraformer model from: {MODEL_DIR}")
    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(MODEL_PATH),
        tokens=str(TOKENS_PATH),
        num_threads=NUM_THREADS,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        provider="cpu",
    )
    print("Paraformer model loaded.")
    return recognizer


# [新增] 加载中文标点恢复模型
def create_punctuator():
    """Load the offline CT-Transformer punctuation model once at startup."""
    if not PUNCTUATION_MODEL_PATH.is_file():
        raise FileNotFoundError(
            f"Punctuation model file not found: {PUNCTUATION_MODEL_PATH}"
        )

    print(f"Loading punctuation model from: {PUNCTUATION_MODEL_PATH}")

    config = sherpa_onnx.OfflinePunctuationConfig(
        model=sherpa_onnx.OfflinePunctuationModelConfig(
            ct_transformer=str(PUNCTUATION_MODEL_PATH),
            num_threads=1,
            provider="cpu",
        )
    )

    punctuator = sherpa_onnx.OfflinePunctuation(config)
    print("Punctuation model loaded.")
    return punctuator


RECOGNIZER = create_recognizer()

# [新增] 服务启动时只加载一次标点模型
PUNCTUATOR = create_punctuator()

# [新增] 避免多个请求同时调用同一个标点模型实例
PUNCTUATION_LOCK = threading.Lock()


def parse_multipart_form(body: bytes, content_type: str):
    """Parse multipart/form-data without the removed Python cgi module."""
    match = re.search(r'boundary="?([^";]+)"?', content_type)
    if not match:
        raise ValueError("missing multipart boundary in Content-Type")

    delimiter = b"--" + match.group(1).strip().encode()
    fields = {}
    files = {}

    for chunk in body.split(delimiter):
        if not chunk or chunk.startswith(b"--"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        if b"\r\n\r\n" not in chunk:
            continue

        raw_headers, content = chunk.split(b"\r\n\r\n", 1)
        disposition = ""
        for line in raw_headers.decode("utf-8", "replace").split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                disposition = line

        name_match = re.search(r'name="([^"]*)"', disposition)
        if not name_match:
            continue

        name = name_match.group(1)
        file_match = re.search(r'filename="([^"]*)"', disposition)
        if file_match is not None:
            files[name] = (file_match.group(1), content)
        else:
            fields[name] = content.decode("utf-8", "replace")

    return fields, files


def convert_audio(input_path: str) -> str:
    """Convert OpenWhispr audio to 16 kHz mono PCM WAV."""
    fd, output_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-y", "-i", input_path,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                "-f", "wav", output_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        Path(output_path).unlink(missing_ok=True)
        raise
    except subprocess.CalledProcessError as exc:
        Path(output_path).unlink(missing_ok=True)
        detail = (exc.stderr or "").strip()
        raise RuntimeError(f"ffmpeg conversion failed: {detail}") from exc

    return output_path


def transcribe(audio_path: str, model: str = "", language=None, prompt=None) -> str:
    """Run local Paraformer inference and restore punctuation."""
    with wave.open(audio_path, "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        raw_audio = wav.readframes(frame_count)

    if channels != 1 or sample_width != 2 or sample_rate != 16000:
        raise ValueError(
            "Expected 16 kHz, mono, 16-bit PCM WAV after ffmpeg conversion; "
            f"got channels={channels}, sample_width={sample_width}, "
            f"sample_rate={sample_rate}"
        )

    samples = array.array("h")
    samples.frombytes(raw_audio)
    if os.sys.byteorder != "little":
        samples.byteswap()

    # Sherpa-ONNX expects float samples normalized to [-1.0, 1.0].
    audio = [sample / 32768.0 for sample in samples]

    stream = RECOGNIZER.create_stream()
    stream.accept_waveform(16000, audio)
    RECOGNIZER.decode_stream(stream)

    # 原有 Paraformer 识别结果
    transcript = stream.result.text.strip()

    # [新增] 对识别结果进行中文标点恢复
    if transcript:
        with PUNCTUATION_LOCK:
            transcript = PUNCTUATOR.add_punctuation(transcript)

    return transcript.strip()


class ShimHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") not in (
            "/audio/transcriptions",
            "/v1/audio/transcriptions",
        ):
            self._send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return

        if length <= 0:
            self._send_json(400, {"error": "empty body"})
            return
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "request body too large"})
            return

        body = self.rfile.read(length)
        try:
            fields, files = parse_multipart_form(
                body, self.headers.get("Content-Type", "")
            )
        except ValueError as exc:
            self._send_json(400, {"error": f"bad multipart: {exc}"})
            return

        if "file" not in files:
            self._send_json(400, {"error": "missing 'file' field"})
            return

        filename, file_bytes = files["file"]
        suffix = Path(filename).suffix or ".webm"
        fd, input_path = tempfile.mkstemp(suffix=suffix)
        wav_path = None

        try:
            with os.fdopen(fd, "wb") as audio_file:
                audio_file.write(file_bytes)

            wav_path = convert_audio(input_path)
            transcript = transcribe(
                wav_path,
                fields.get("model", ""),
                fields.get("language"),
                fields.get("prompt"),
            )
            print(f"Transcribed {filename}: {transcript[:100]}")
            self._send_json(
                200,
                {"text": transcript or "", "object": "transcription"},
            )
        except FileNotFoundError as exc:
            self._send_json(500, {"error": str(exc)})
        except RuntimeError as exc:
            self._send_json(500, {"error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"error": f"transcription failed: {exc}"})
        finally:
            for path in (input_path, wav_path):
                if path and os.path.exists(path):
                    os.remove(path)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("/models", "/v1/models"):
            self._send_json(200, {
                "object": "list",
                "data": [
                    {
                        "id": "paraformer-chuan",
                        "object": "model",
                        "owned_by": "local"
                    }
                ]
            })
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, format_string, *args):
        print(f"[HTTP] {format_string % args}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), ShimHandler)
    server.daemon_threads = True
    print(f"OpenWhispr Paraformer shim: http://localhost:{PORT}")
    print("OpenWhispr setting: Transcription -> Self-Hosted")
    print(f"Server URL: http://localhost:{PORT}")
    print("Model: paraformer-chuan")
    print("All audio recognition runs locally. Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
