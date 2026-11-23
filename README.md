# OpenWhispr + Local ASR (Paraformer / SenseVoice, Fully Local)

English | [中文](README-zh.md)

This small project forwards OpenWhispr's Self-Hosted transcription requests to a
local Sherpa-ONNX server. Two recognition engines are available and you pick one
in `config.ini`:

- `paraformer` (default): Paraformer INT8 fine-tuned for the Sichuan/Chongqing
  dialect, followed by a CT-Transformer model that restores Chinese punctuation.
- `sense_voice`: SenseVoice INT8 for Chinese, English, Japanese, Korean and
  Cantonese. It adds punctuation and normalizes numbers by itself.

English words that the Paraformer model emits as separate letters are re-joined
using a bundled word list. Audio is never sent to the cloud.

## 1. Prerequisites

- macOS on Intel (x86_64) or Apple Silicon
- Python 3.9+
- FFmpeg installed, with the `ffmpeg` command available
- The downloaded model directories, which must contain:
  - Paraformer: `model.int8.onnx`, `tokens.txt`
  - SenseVoice (optional): `model.int8.onnx`, `tokens.txt`
  - Punctuation restoration: `model.int8.onnx`

Official model documentation and downloads:

- https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-paraformer/paraformer-models.html

Paraformer model archive:

- https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-int8-2025-10-07.tar.bz2

SenseVoice documentation:

- https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html

SenseVoice model archive (only needed for `engine = sense_voice`):

- https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2

Punctuation model (CT-Transformer) documentation:

- https://k2-fsa.github.io/sherpa/onnx/punctuation/index.html

Punctuation model releases:

- https://github.com/k2-fsa/sherpa-onnx/releases/tag/punctuation-models

Punctuation model archive:

- https://github.com/k2-fsa/sherpa-onnx/releases/download/punctuation-models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8.tar.bz2

## 2. Install Dependencies

Using a dedicated virtual environment is recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install sherpa-onnx
```

FFmpeg must be installed separately if it is not already available. With
Homebrew:

```bash
brew install ffmpeg
```

## 3. Place the Models

By default, the model directories must sit next to `paraformer_chuan_shim.py`.
The SenseVoice directory is only needed when `engine = sense_voice`:

```text
paraformer_chuan_openwhispr/
├── paraformer_chuan_shim.py
├── config.example.ini
├── data/
│   ├── english_words.txt.gz
│   └── README.md
├── sherpa-onnx-paraformer-zh-int8-2025-10-07/
│   ├── model.int8.onnx
│   └── tokens.txt
├── sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/   # optional
│   ├── model.int8.onnx
│   └── tokens.txt
└── sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8/
    └── model.int8.onnx
```

The English word list is bundled with the project, so no extra download is
needed and the spacing fix works offline. See [`data/README.md`](data/README.md)
for its source and license.

You can point to other model directories with `models.paraformer_dir`,
`models.sense_voice_dir` and `models.punctuation_dir` in `config.ini` (or the
`PARAFORMER_MODEL_DIR`, `SENSE_VOICE_MODEL_DIR` and `PUNCTUATION_MODEL_DIR`
environment variables).

## 4. Configure the Shim

All user-facing settings live in one INI file. Copy the example once:

```bash
cp config.example.ini config.ini
```

Then edit `config.ini`:

```ini
[server]
host = 127.0.0.1
port = 8765

[models]
engine = paraformer

paraformer_dir = ./sherpa-onnx-paraformer-zh-int8-2025-10-07
punctuation_dir = ./sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8
num_threads = 2

# SenseVoice only
sense_voice_dir = ./sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
sense_voice_language = auto
sense_voice_use_itn = true

# auto | always | never
punctuation = auto

[english]
fix = true
words_path =
```

`config.ini` is not tracked by Git; `config.example.ini` is the template.

- Relative paths are resolved against the directory containing `config.ini`
  (normally the project root).
- `~` is expanded, but shell variables such as `$HOME` are not. Use an absolute
  path or `~/...` inside `config.ini`.
- Environment variables override values in `config.ini` when set.
- If `config.ini` is missing, the built-in defaults are used.
- To use a config file somewhere else:

```bash
export CONFIG_PATH="$HOME/.config/paraformer-chuan.ini"
```

## 5. Start the Server

From the project directory:

```bash
source .venv/bin/activate && python paraformer_chuan_shim.py
```

On the first start, the selected recognition model is loaded. With
`engine = paraformer` you will see `Paraformer model loaded.` and
`Punctuation model loaded.` With `engine = sense_voice` you will see
`SenseVoice model loaded` and `Skipping punctuation model: ...`, because
SenseVoice already adds punctuation. Keep this terminal running.

## 6. Configure OpenWhispr

Open Settings → Transcription → Self-Hosted:

- Server URL: `http://localhost:8765`
- Model: `paraformer-chuan` or `sense-voice`

The Model field is not used for routing: the shim ignores it and always uses the
engine from `config.ini`. Both ids are listed by `/models`, so either one works
and switching engines does not require touching OpenWhispr.

After saving, OpenWhispr recordings are sent to the local service, and the
recognized text is returned to OpenWhispr.

## 7. Switch the Recognition Engine

Only one engine is loaded at a time, so memory use stays the same as before.
Edit `config.ini`, then restart the shim:

```ini
[models]
engine = sense_voice
```

Switch back with:

```ini
[models]
engine = paraformer
```

`engine` accepts `paraformer` or `sense_voice`. Changing it requires a restart;
OpenWhispr itself needs no change.

### Punctuation

| `punctuation` | Behavior |
|---|---|
| `auto` (default) | Use the standalone punctuation model, except when SenseVoice already adds punctuation (`use_itn = true`) |
| `always` | Always run the standalone punctuation model |
| `never` | Never run it and return raw recognizer text |

SenseVoice punctuation is controlled by `sense_voice_use_itn`:

- `true` (default): `开饭时间早上9点至下午5点。` — punctuation plus normalized
  numbers, and the standalone punctuation model is skipped.
- `false`: `开饭时间早上九点至下午五点` — no punctuation, so the standalone
  punctuation model runs.

### Trade-offs

| | Paraformer (default) | SenseVoice |
|---|---|---|
| Sichuan/Chongqing dialect | Better, fine-tuned for it | May normalize to Mandarin |
| Mandarin | Good | Usually more stable |
| Chinese-English mixing | Weaker | Much better, outputs whole English words |
| Punctuation | Separate punctuation model | Built in (`use_itn = true`) |
| Languages | Chinese (+ some English) | Chinese, English, Japanese, Korean, Cantonese |

Try a batch of your own recordings before deciding. `sense_voice_language` can
stay `auto`; set it to `zh` if `auto` misdetects your speech.

## 8. Environment Variable Overrides

`config.ini` is the recommended way to change settings. Environment variables
are still supported and take precedence over the config file, which is useful
for temporary or per-process changes.

| Config setting | Environment variable |
|---|---|
| `server.host` | `SHIM_HOST` |
| `server.port` | `SHIM_PORT` |
| `models.engine` | `ASR_ENGINE` |
| `models.paraformer_dir` | `PARAFORMER_MODEL_DIR` |
| `models.sense_voice_dir` | `SENSE_VOICE_MODEL_DIR` |
| `models.sense_voice_language` | `SENSE_VOICE_LANGUAGE` |
| `models.sense_voice_use_itn` | `SENSE_VOICE_USE_ITN` |
| `models.punctuation` | `PUNCTUATION_MODE` |
| `models.punctuation_dir` | `PUNCTUATION_MODEL_DIR` |
| `models.num_threads` | `SHERPA_NUM_THREADS` |
| `english.fix` | `ENGLISH_SPACING_FIX` |
| `english.words_path` | `ENGLISH_WORDS_PATH` |
| config file location | `CONFIG_PATH` |

Examples:

```bash
export SHIM_PORT=9000
export SHERPA_NUM_THREADS=4
export ASR_ENGINE=sense_voice
export ENGLISH_SPACING_FIX=0
```

When an environment variable is set, it wins over the value in `config.ini`.

## 9. English Spacing Normalization

The Chinese Paraformer model sometimes emits an English word as separate
letters, for example `我 l o v e 你`. The shim re-joins these runs with the
bundled 30,000-word frequency list:

```text
我 l o v e 你        -> 我 love 你
i l o v e y o u      -> i love you
h e l l o w o r l d  -> hello world
```

Only runs of space-separated single letters are changed; normal English text is
left untouched. This works offline and does not depend on a system dictionary.

The examples above show the text after spacing normalization and before
punctuation restoration. The punctuation model may remove spaces between
Chinese and English, so the final text can be `我love你。`.

To disable it, set this in `config.ini`:

```ini
[english]
fix = false
```

To use your own word list (one word per line, plain text or gzip-compressed):

```ini
[english]
words_path = /Users/you/Models/english_words.txt.gz
```

You can also override these values with `ENGLISH_SPACING_FIX` and
`ENGLISH_WORDS_PATH`.

If the word list is missing, the shim skips this step and keeps working.

## 10. Test the Local API

With the server running, test it with an audio file (replace `sample.wav` with
your own recording):

```bash
curl -X POST http://localhost:8765/audio/transcriptions -F "file=@sample.wav" -F "model=paraformer-chuan"
```

Response format:

```json
{"text":"recognized text","object":"transcription"}
```

You can also list the available models:

```bash
curl http://localhost:8765/models
```

## Notes

- This is OpenWhispr's batch transcription endpoint: recognition happens after
  you release the shortcut, so it is not word-by-word live captioning.
- OpenWhispr itself, the shim, FFmpeg, Sherpa-ONNX, and the models all run
  locally on your machine.
- The Paraformer model is mainly fine-tuned for the Sichuan/Chongqing dialect,
  but you should still verify actual accuracy with your own recordings.
- SenseVoice is better at Mandarin and Chinese-English mixing, but may lose
  dialect flavor words. Compare both on your own audio before switching.
- English spacing normalization only repairs formatting. If the model
  misrecognizes the letters themselves (for example `you` as `e u`), the text
  will still be wrong. It is mainly useful for the Paraformer engine; SenseVoice
  usually outputs whole English words.
