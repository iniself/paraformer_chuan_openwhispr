# OpenWhispr + Sichuan/Chongqing Paraformer (Fully Local)

English | [中文](README-zh.md)

This small project forwards OpenWhispr's Self-Hosted transcription requests to a
local Sherpa-ONNX server. Speech is recognized with a Paraformer INT8 model
fine-tuned for the Sichuan/Chongqing dialect, and the result is passed through a
CT-Transformer model to restore Chinese punctuation. Audio is never sent to the
cloud.

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
├── sherpa-onnx-paraformer-zh-int8-2025-10-07/
│   ├── model.int8.onnx
│   └── tokens.txt
└── sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8/
    └── model.int8.onnx
```

You can point to other model directories with the `PARAFORMER_MODEL_DIR` and
`PUNCTUATION_MODEL_DIR` environment variables.

## 4. Start the Server

From the project directory:

```bash
source .venv/bin/activate && python paraformer_chuan_shim.py
```

On the first start, the ~227 MB Paraformer model is loaded, followed by the
punctuation model. Once both are ready you will see `Paraformer model loaded.`
and `Punctuation model loaded.` Keep this terminal running.

## 5. Configure OpenWhispr

Open Settings → Transcription → Self-Hosted:

- Server URL: `http://localhost:8765`
- Model: `paraformer-chuan`

After saving, OpenWhispr recordings are sent to the local service, and the
recognized text is returned to OpenWhispr.

## 6. Optional Settings

For example, to keep the models somewhere else:

```bash
export PARAFORMER_MODEL_DIR="$HOME/Models/sherpa-onnx-paraformer-zh-int8-2025-10-07"
export PUNCTUATION_MODEL_DIR="$HOME/Models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8"
```

To adjust the number of CPU threads (default is 2):

```bash
export SHERPA_NUM_THREADS=4
```

To change the listening address or port (defaults are `127.0.0.1:8765`):

```bash
export SHIM_HOST=127.0.0.1
export SHIM_PORT=8765
```

## 7. Test the Local API

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
