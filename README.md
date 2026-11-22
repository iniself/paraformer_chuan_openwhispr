# OpenWhispr + Sichuan/Chongqing Paraformer (Fully Local)

English | [中文](README-zh.md)

This small project forwards OpenWhispr's Self-Hosted transcription requests to a
local Sherpa-ONNX server. Speech is recognized with a Paraformer INT8 model
fine-tuned for the Sichuan/Chongqing dialect, and the result is passed through a
CT-Transformer model to restore Chinese punctuation. English words that the
model emits as separate letters are re-joined using a bundled word list. Audio
is never sent to the cloud.

## 1. Prerequisites

- macOS on Intel (x86_64) or Apple Silicon
- Python 3.9+
- FFmpeg installed, with the `ffmpeg` command available
- The downloaded model directories, which must contain:
  - Paraformer: `model.int8.onnx`, `tokens.txt`
  - Punctuation restoration: `model.int8.onnx`

Official model documentation and downloads:

- https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-paraformer/paraformer-models.html

Paraformer model archive:

- https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-int8-2025-10-07.tar.bz2

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

By default, both model directories must sit next to `paraformer_chuan_shim.py`:

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
└── sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8/
    └── model.int8.onnx
```

The English word list is bundled with the project, so no extra download is
needed and the spacing fix works offline. See [`data/README.md`](data/README.md)
for its source and license.

You can point to other model directories with `models.paraformer_dir` and
`models.punctuation_dir` in `config.ini` (or the `PARAFORMER_MODEL_DIR` and
`PUNCTUATION_MODEL_DIR` environment variables).

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
paraformer_dir = ./sherpa-onnx-paraformer-zh-int8-2025-10-07
punctuation_dir = ./sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8
num_threads = 2

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

On the first start, the ~227 MB Paraformer model is loaded, followed by the
punctuation model. Once both are ready you will see `Paraformer model loaded.`
and `Punctuation model loaded.` Keep this terminal running.

## 6. Configure OpenWhispr

Open Settings → Transcription → Self-Hosted:

- Server URL: `http://localhost:8765`
- Model: `paraformer-chuan`

After saving, OpenWhispr recordings are sent to the local service, and the
recognized text is returned to OpenWhispr.

## 7. Environment Variable Overrides

`config.ini` is the recommended way to change settings. Environment variables
are still supported and take precedence over the config file, which is useful
for temporary or per-process changes.

| Config setting | Environment variable |
|---|---|
| `server.host` | `SHIM_HOST` |
| `server.port` | `SHIM_PORT` |
| `models.paraformer_dir` | `PARAFORMER_MODEL_DIR` |
| `models.punctuation_dir` | `PUNCTUATION_MODEL_DIR` |
| `models.num_threads` | `SHERPA_NUM_THREADS` |
| `english.fix` | `ENGLISH_SPACING_FIX` |
| `english.words_path` | `ENGLISH_WORDS_PATH` |
| config file location | `CONFIG_PATH` |

Examples:

```bash
export SHIM_PORT=9000
export SHERPA_NUM_THREADS=4
export ENGLISH_SPACING_FIX=0
```

When an environment variable is set, it wins over the value in `config.ini`.

## 8. English Spacing Normalization

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

## 9. Test the Local API

With the server running, test it with an audio file (replace `sample.wav` with
your own recording):

```bash
curl -X POST http://localhost:8765/audio/transcriptions -F "file=@sample.wav" -F "model=paraformer-chuan"
```

Response format:

```json
{"text":"recognized text","object":"transcription"}
```

You can also list the available model:

```bash
curl http://localhost:8765/models
```

## Notes

- This is OpenWhispr's batch transcription endpoint: recognition happens after
  you release the shortcut, so it is not word-by-word live captioning.
- OpenWhispr itself, the shim, FFmpeg, Sherpa-ONNX, and the models all run
  locally on your machine.
- The model is mainly fine-tuned for the Sichuan/Chongqing dialect, but you
  should still verify actual accuracy with your own recordings.
- English spacing normalization only repairs formatting. If the model
  misrecognizes the letters themselves (for example `you` as `e u`), the text
  will still be wrong. For heavy Chinese-English code-switching, consider a
  bilingual ASR model.
