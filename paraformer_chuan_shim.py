#!/usr/bin/env python3
"""Local OpenWhispr ASR shim using the Sichuan/Chongqing Paraformer model."""

from __future__ import annotations

import array
import configparser
import gzip
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sherpa_onnx


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get(
    "CONFIG_PATH",
    str(PROJECT_DIR / "config.ini"),
)).expanduser()
if not CONFIG_PATH.is_absolute():
    CONFIG_PATH = PROJECT_DIR / CONFIG_PATH
CONFIG_PATH = CONFIG_PATH.resolve()


def load_config() -> configparser.ConfigParser:
    """Load config.ini if present. Environment variables override it later."""
    parser = configparser.ConfigParser(
        interpolation=None,
        inline_comment_prefixes=("#", ";"),
    )
    if not CONFIG_PATH.is_file():
        return parser

    try:
        with CONFIG_PATH.open(encoding="utf-8") as config_file:
            parser.read_file(config_file)
    except (OSError, UnicodeError, configparser.Error) as exc:
        raise SystemExit(
            f"Failed to read config file {CONFIG_PATH}: {exc}"
        ) from exc

    return parser


_CONFIG = load_config()
BASE_DIR = CONFIG_PATH.parent if CONFIG_PATH.is_file() else PROJECT_DIR


def get_setting(env_name: str, section: str, option: str, default: str) -> str:
    """Return the environment variable, then config.ini, then the default."""
    if env_name in os.environ:
        return os.environ[env_name]
    return _CONFIG.get(section, option, fallback=default)


def get_int_setting(
    env_name: str,
    section: str,
    option: str,
    default: int,
) -> int:
    raw = get_setting(env_name, section, option, str(default)).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid integer for {env_name} or [{section}] {option}: {raw!r}"
        ) from exc


def get_bool_setting(
    env_name: str,
    section: str,
    option: str,
    default: bool,
) -> bool:
    raw = get_setting(
        env_name, section, option, "true" if default else "false"
    ).strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise SystemExit(
        f"Invalid boolean for {env_name} or [{section}] {option}: {raw!r}"
    )


def get_path_setting(
    env_name: str,
    section: str,
    option: str,
    default: Path,
) -> Path:
    raw = get_setting(env_name, section, option, str(default)).strip()
    if not raw:
        raw = str(default)

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


PORT = get_int_setting("SHIM_PORT", "server", "port", 8765)
HOST = get_setting("SHIM_HOST", "server", "host", "127.0.0.1").strip()
if not HOST:
    HOST = "127.0.0.1"
if not 0 < PORT < 65536:
    raise SystemExit(f"Invalid port: {PORT}")

MAX_BODY_BYTES = 25 * 1024 * 1024

MODEL_DIR = get_path_setting(
    "PARAFORMER_MODEL_DIR",
    "models",
    "paraformer_dir",
    PROJECT_DIR / "sherpa-onnx-paraformer-zh-int8-2025-10-07",
)

MODEL_PATH = MODEL_DIR / "model.int8.onnx"
TOKENS_PATH = MODEL_DIR / "tokens.txt"
NUM_THREADS = get_int_setting("SHERPA_NUM_THREADS", "models", "num_threads", 2)
if NUM_THREADS < 1:
    raise SystemExit(f"num_threads must be at least 1, got {NUM_THREADS}")

# [新增] 中文标点恢复模型配置
PUNCTUATION_MODEL_DIR = get_path_setting(
    "PUNCTUATION_MODEL_DIR",
    "models",
    "punctuation_dir",
    PROJECT_DIR / "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8",
)

PUNCTUATION_MODEL_PATH = PUNCTUATION_MODEL_DIR / "model.int8.onnx"

# [新增] 英文单字母空格修复配置
ENGLISH_SPACING_FIX = get_bool_setting("ENGLISH_SPACING_FIX", "english", "fix", True)

ENGLISH_WORDS_PATH = get_path_setting(
    "ENGLISH_WORDS_PATH",
    "english",
    "words_path",
    PROJECT_DIR / "data" / "english_words.txt.gz",
)

if CONFIG_PATH.is_file():
    print(f"Using config file: {CONFIG_PATH}")


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

# [新增] 英文单字母空格修复状态
_ENGLISH_WORDS_LOCK = threading.Lock()
_ENGLISH_WORD_COSTS: dict[str, float] | None = None
_ENGLISH_WORD_MAX_LEN = 0
_ENGLISH_WORDS_LOAD_FAILED = False

LETTER_RUN_RE = re.compile(
    r"(?<![A-Za-z])(?:[A-Za-z][ \t]+)+[A-Za-z](?![A-Za-z])"
)


def load_english_words() -> dict[str, float] | None:
    """Load the bundled English word list once, on first use."""
    global _ENGLISH_WORD_COSTS, _ENGLISH_WORD_MAX_LEN, _ENGLISH_WORDS_LOAD_FAILED

    if _ENGLISH_WORD_COSTS is not None or _ENGLISH_WORDS_LOAD_FAILED:
        return _ENGLISH_WORD_COSTS

    with _ENGLISH_WORDS_LOCK:
        if _ENGLISH_WORD_COSTS is not None or _ENGLISH_WORDS_LOAD_FAILED:
            return _ENGLISH_WORD_COSTS

        path = ENGLISH_WORDS_PATH
        if not path.is_file():
            print(f"English word list not found: {path}")
            print("English letter spacing fix is disabled.")
            _ENGLISH_WORDS_LOAD_FAILED = True
            return None

        try:
            opener = gzip.open if path.suffix == ".gz" else open
            with opener(path, "rt", encoding="utf-8") as word_file:
                words = [
                    line.strip().lower()
                    for line in word_file
                    if line.strip()
                ]
        except (OSError, UnicodeError) as exc:
            print(f"Failed to load English word list: {exc}")
            print("English letter spacing fix is disabled.")
            _ENGLISH_WORDS_LOAD_FAILED = True
            return None

        words = [word for word in words if word.isalpha()]
        if not words:
            print(f"English word list is empty: {path}")
            print("English letter spacing fix is disabled.")
            _ENGLISH_WORDS_LOAD_FAILED = True
            return None

        # Words are ordered by frequency, so earlier words get a lower cost.
        log_word_count = max(math.log(len(words)), 1.0)
        costs: dict[str, float] = {}
        for index, word in enumerate(words):
            costs.setdefault(word, math.log((index + 1) * log_word_count))

        _ENGLISH_WORD_COSTS = costs
        _ENGLISH_WORD_MAX_LEN = max(len(word) for word in costs)
        print(f"English word list loaded: {len(costs)} words")
        return _ENGLISH_WORD_COSTS


def _segment_english_letters(
    letters: str,
    costs: dict[str, float],
    max_word_len: int,
) -> str | None:
    """Split a run of letters into the most likely English words."""
    length = len(letters)
    best = [math.inf] * (length + 1)
    best[0] = 0.0
    previous = [0] * (length + 1)

    for end in range(1, length + 1):
        for start in range(max(0, end - max_word_len), end):
            word = letters[start:end].lower()
            cost = costs.get(word)
            if cost is None:
                continue

            if len(word) == 1:
                # Only allow "a" and "i", and make them less attractive than
                # a real word such as "ai", "am", or "is".
                if word not in ("a", "i"):
                    continue
                cost += 5.0

            candidate = best[start] + cost
            if candidate < best[end]:
                best[end] = candidate
                previous[end] = start

    if best[length] == math.inf:
        return None

    words = []
    end = length
    while end > 0:
        start = previous[end]
        words.append(letters[start:end].lower())
        end = start

    return " ".join(reversed(words))


def normalize_english_spacing(text: str) -> str:
    """Join English words that the ASR model emitted as separate letters."""
    if not ENGLISH_SPACING_FIX or not text:
        return text

    costs = load_english_words()
    if not costs:
        return text

    def replace(match: re.Match[str]) -> str:
        letters = "".join(match.group(0).split())
        if len(letters) < 2:
            return match.group(0)

        normalized = _segment_english_letters(
            letters, costs, _ENGLISH_WORD_MAX_LEN
        )
        return normalized or match.group(0)

    return LETTER_RUN_RE.sub(replace, text)


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

    # [新增] 合并被模型拆成单字母的英文，例如 "l o v e" -> "love"
    transcript = normalize_english_spacing(transcript)

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
