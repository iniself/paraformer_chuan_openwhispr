# OpenWhispr + 本地 ASR（川渝 Paraformer / SenseVoice，完全本地）

[English](README.md) | 中文

这个小项目把 OpenWhispr 的 Self-Hosted 转录请求转交给本机 Sherpa-ONNX。
项目支持两种识别引擎，在 `config.ini` 里选一个：

- `paraformer`（默认）：针对四川话 / 重庆话微调的 Paraformer INT8 模型，
  识别结果再经过 CT-Transformer 模型恢复中文标点。
- `sense_voice`：SenseVoice INT8，支持中、英、日、韩、粤语，自带标点并会
  把数字规范化。

Paraformer 引擎还会用内置词表把被模型拆成单字母的英文重新合并。音频不发送
到云端。

## 1. 前置条件

- macOS Intel（x86_64）或 Apple Silicon
- Python 3.9+
- FFmpeg 已安装并且 `ffmpeg` 命令可用
- 下载好的模型目录，里面必须有：
  - Paraformer：`model.int8.onnx`、`tokens.txt`
  - SenseVoice（可选）：`model.int8.onnx`、`tokens.txt`
  - 标点恢复：`model.int8.onnx`

Paraformer 模型官方说明和下载：
https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-paraformer/paraformer-models.html

Paraformer 模型压缩包：
https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-paraformer-zh-int8-2025-10-07.tar.bz2

SenseVoice 官方说明：
https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html

SenseVoice 模型压缩包（只有 `engine = sense_voice` 时需要）：
https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2

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

默认要求模型目录与 `paraformer_chuan_shim.py` 在同一目录。SenseVoice 目录
只在 `engine = sense_voice` 时需要：

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
├── sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/   # 可选
│   ├── model.int8.onnx
│   └── tokens.txt
└── sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8/
    └── model.int8.onnx
```

英文词表已经随项目一起提供，不需要额外下载，断网也能使用。词表来源和许可
见 [`data/README.md`](data/README.md)。

也可以在 `config.ini` 中通过 `models.paraformer_dir`、
`models.sense_voice_dir` 和 `models.punctuation_dir` 指定其他模型目录
（或使用环境变量 `PARAFORMER_MODEL_DIR`、`SENSE_VOICE_MODEL_DIR` 和
`PUNCTUATION_MODEL_DIR`）。

## 4. 配置 Shim

所有用户配置都放在一个 INI 文件里。先复制示例文件：

```bash
cp config.example.ini config.ini
```

然后编辑 `config.ini`：

```ini
[server]
host = 127.0.0.1
port = 8765

[models]
engine = paraformer

paraformer_dir = ./sherpa-onnx-paraformer-zh-int8-2025-10-07
punctuation_dir = ./sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8
num_threads = 2

# 仅 SenseVoice 使用
sense_voice_dir = ./sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
sense_voice_language = auto
sense_voice_use_itn = true

# auto | always | never
punctuation = auto

[english]
fix = true
words_path =
```

`config.ini` 不会被 Git 跟踪，`config.example.ini` 是模板。

- 相对路径相对于 `config.ini` 所在目录解析（通常就是项目根目录）。
- 支持 `~`，但不会展开 `$HOME` 这类 shell 变量。配置里请用绝对路径或
  `~/...`。
- 环境变量优先级高于 `config.ini`。
- 没有 `config.ini` 时使用内置默认值。
- 如果配置文件放在其他位置：

```bash
export CONFIG_PATH="$HOME/.config/paraformer-chuan.ini"
```

## 5. 启动

在项目目录执行：

```bash
source .venv/bin/activate && python paraformer_chuan_shim.py
```

第一次启动会加载所选识别模型。`engine = paraformer` 时会显示
`Paraformer model loaded.` 和 `Punctuation model loaded.`；
`engine = sense_voice` 时会显示 `SenseVoice model loaded` 和
`Skipping punctuation model: ...`，因为 SenseVoice 自带标点。
保持这个终端窗口运行。

## 6. 配置 OpenWhispr

打开 Settings → Transcription → Self-Hosted：

- Server URL：`http://localhost:8765`
- Model：`paraformer-chuan` 或 `sense-voice`

Model 字段不参与路由：Shim 会忽略它，始终使用 `config.ini` 里配置的引擎。
`/models` 会同时列出两个 id，所以填哪个都能用，切换引擎时也不用改
OpenWhispr。

保存后，OpenWhispr 的录音会发到本机服务，识别结果再返回 OpenWhispr。

## 7. 切换识别引擎

同一时间只加载一个引擎，内存占用和以前一样。修改 `config.ini` 后重启 Shim：

```ini
[models]
engine = sense_voice
```

切回川渝模型：

```ini
[models]
engine = paraformer
```

`engine` 只接受 `paraformer` 或 `sense_voice`。切换后需要重启，OpenWhispr
本身不用改。

### 标点

| `punctuation` | 行为 |
|---|---|
| `auto`（默认） | 使用独立标点模型，但 SenseVoice 自带标点时（`use_itn = true`）跳过 |
| `always` | 总是使用独立标点模型 |
| `never` | 不使用独立标点模型，只返回识别原文 |

SenseVoice 的标点由 `sense_voice_use_itn` 控制：

- `true`（默认）：输出 `开饭时间早上9点至下午5点。`，自带标点并规范化数字，
  同时跳过独立标点模型。
- `false`：输出 `开饭时间早上九点至下午五点`，没有标点，由独立标点模型补。

### 两者取舍

| | Paraformer（默认） | SenseVoice |
|---|---|---|
| 川渝方言 | 更好，专门微调过 | 可能被“普通话化” |
| 普通话 | 好 | 通常更稳 |
| 中英混说 | 较弱 | 明显更好，英文按完整单词输出 |
| 标点 | 独立标点模型 | 自带（`use_itn = true`） |
| 语言 | 中文（含少量英文） | 中、英、日、韩、粤 |

建议先用一批自己的录音对比再决定。`sense_voice_language` 可以先保持
`auto`；如果 `auto` 识别语言不准，再改成 `zh`。

## 8. 环境变量覆盖

推荐用 `config.ini` 修改配置。环境变量仍然可用，并且优先级高于配置文件，
适合临时调试或脚本启动。

| 配置项 | 环境变量 |
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
| 配置文件位置 | `CONFIG_PATH` |

示例：

```bash
export SHIM_PORT=9000
export SHERPA_NUM_THREADS=4
export ASR_ENGINE=sense_voice
export ENGLISH_SPACING_FIX=0
```

设置了环境变量时，会覆盖 `config.ini` 中的同名配置。

## 9. 英文空格修复

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

关闭该功能，在 `config.ini` 中设置：

```ini
[english]
fix = false
```

使用自定义词表（每行一个单词，普通文本或 gzip 压缩均可）：

```ini
[english]
words_path = /Users/you/Models/english_words.txt.gz
```

也可以用 `ENGLISH_SPACING_FIX` 和 `ENGLISH_WORDS_PATH` 环境变量临时覆盖。

如果词表文件不存在，Shim 会跳过这一步，不影响正常识别。

## 10. 本地接口自测

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
- Paraformer 模型主要针对川渝方言微调，但实际效果仍应使用你自己的录音验证。
- SenseVoice 的普通话和中英混说更好，但可能丢掉方言特色词。切换前建议先用
  自己的录音对比两种引擎。
- 英文空格修复只改善格式。如果模型把字母本身听错（例如把 `you` 听成 `e u`），
  文字仍然是错的。它主要对 Paraformer 有用，SenseVoice 一般直接输出完整英文
  单词。
