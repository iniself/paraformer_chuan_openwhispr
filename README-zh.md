# OpenWhispr + 川渝 Paraformer（完全本地）

[English](README.md) | 中文

这个小项目把 OpenWhispr 的 Self-Hosted 转录请求转交给本机 Sherpa-ONNX，
使用针对四川话 / 重庆话微调的 Paraformer INT8 模型识别，识别结果再经过
CT-Transformer 模型恢复中文标点，并用内置词表把被模型拆成单字母的英文
重新合并。音频不发送到云端。

## 1. 前置条件

- macOS Intel（x86_64）或 Apple Silicon
- Python 3.9+
- FFmpeg 已安装并且 `ffmpeg` 命令可用
- 下载好的模型目录，里面必须有：
  - Paraformer：`model.int8.onnx`、`tokens.txt`
  - 标点恢复：`model.int8.onnx`

Paraformer 模型官方说明和下载：
https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-paraformer/paraformer-models.html

Paraformer 模型压缩包：
https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-int8-2025-10-07.tar.bz2

标点模型（CT-Transformer）官方说明：
https://k2-fsa.github.io/sherpa/onnx/punctuation/index.html

标点模型发布页：
https://github.com/k2-fsa/sherpa-onnx/releases/tag/punctuation-models

标点模型压缩包：
https://github.com/k2-fsa/sherpa-onnx/releases/download/punctuation-models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8.tar.bz2

## 2. 安装依赖

建议使用独立虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install sherpa-onnx
```

FFmpeg 如果尚未安装，需要单独安装。若使用 Homebrew：

```bash
brew install ffmpeg
```

## 3. 放置模型

默认要求两个模型目录都与 `paraformer_chuan_shim.py` 在同一目录：

```text
paraformer_chuan_openwhispr/
├── paraformer_chuan_shim.py
├── data/
│   ├── english_words.txt.gz
│   └── README.md
├── sherpa-onnx-paraformer-zh-int8-2025-10-07/
│   ├── model.int8.onnx
│   └── tokens.txt
└── sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8/
    └── model.int8.onnx
```

英文词表已经随项目一起提供，不需要额外下载，断网也能使用。词表来源和许可
见 [`data/README.md`](data/README.md)。

也可以通过环境变量 `PARAFORMER_MODEL_DIR` 和 `PUNCTUATION_MODEL_DIR`
指定其他模型目录。

## 4. 启动

在项目目录执行：

```bash
source .venv/bin/activate && python paraformer_chuan_shim.py
```

第一次启动会加载约 227 MB 的 Paraformer 模型，随后加载标点模型。两者都
就绪后会显示 `Paraformer model loaded.` 和 `Punctuation model loaded.`。
保持这个终端窗口运行。

## 5. 配置 OpenWhispr

打开 Settings → Transcription → Self-Hosted：

- Server URL：`http://localhost:8765`
- Model：`paraformer-chuan`

保存后，OpenWhispr 的录音会发到本机服务，识别结果再返回 OpenWhispr。

## 6. 可选设置

例如把模型放在其他位置：

```bash
export PARAFORMER_MODEL_DIR="$HOME/Models/sherpa-onnx-paraformer-zh-int8-2025-10-07"
export PUNCTUATION_MODEL_DIR="$HOME/Models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8"
```

调整 CPU 线程数（默认 2）：

```bash
export SHERPA_NUM_THREADS=4
```

修改监听地址或端口（默认 `127.0.0.1:8765`）：

```bash
export SHIM_HOST=127.0.0.1
export SHIM_PORT=8765
```

## 7. 英文空格修复

中文 Paraformer 有时会把一个英文单词拆成单字母输出，例如 `我 l o v e 你`。
Shim 会用内置的 3 万词频表把这些片段重新拼回去：

```text
我 l o v e 你        -> 我 love 你
i l o v e y o u      -> i love you
h e l l o w o r l d  -> hello world
```

只处理“单个字母 + 空格”的片段，正常英文不会被改动。该功能完全离线运行，
不依赖系统词典。

上面的例子展示的是标点恢复前的效果。标点模型可能会去掉中英文之间的空格，
因此最终结果可能是 `我love你。`。

关闭该功能：

```bash
export ENGLISH_SPACING_FIX=0
```

使用自定义词表（每行一个单词，普通文本或 gzip 压缩均可）：

```bash
export ENGLISH_WORDS_PATH="$HOME/Models/english_words.txt.gz"
```

如果词表文件不存在，Shim 会跳过这一步，不影响正常识别。

## 8. 本地接口自测

服务启动后，可用一段音频测试（把 `sample.wav` 换成自己的音频文件）：

```bash
curl -X POST http://localhost:8765/audio/transcriptions -F "file=@sample.wav" -F "model=paraformer-chuan"
```

返回格式：

```json
{"text":"识别出的文字","object":"transcription"}
```

也可以查看当前可用的模型：

```bash
curl http://localhost:8765/models
```

## 说明

- 这是 OpenWhispr 的批量转录接口：说完松开快捷键后再识别，不是逐字实时字幕。
- OpenWhispr 自身、Shim、FFmpeg、Sherpa-ONNX、标点模型和识别模型均在本机运行，音频和识别文本都不会离开本机。
- 模型主要针对川渝方言微调，但实际效果仍应使用你自己的录音验证。
- 英文空格修复只改善格式。如果模型把字母本身听错（例如把 `you` 听成 `e u`），文字仍然是错的。经常整句中英混说时，建议换用双语 ASR 模型。
