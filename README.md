# VTT Subtitle Translator

A Python tool that translates WebVTT subtitle files using LLMs. Version 2.0 uses a **numbered batch translation** strategy: the whole file is translated in large chunks with surrounding context, giving the model a global view of the transcript so terminology and tone stay consistent.

## Features

- **Numbered batch translation** — each chunk of ~50 captions is sent in one call using `[N]` markers; the response is parsed back to the original captions 1:1.
- **Context windows** — captions before/after each chunk are provided to the model for context without being translated.
- **Multi-language** — `source_language` / `target_language` are configurable; no hard-coded Chinese.
- **Pluggable LLM providers** — `LLMProvider` abstract interface; AWS Bedrock (Anthropic Claude) implemented today, OpenAI/etc. can be added without touching the core.
- **Robust retries** — exponential backoff with full jitter; transient Bedrock errors and network errors are retried automatically.
- **Graceful fallback** — if a caption fails to translate after retries and a single-shot retranslation, the original source text is used as a last resort so your output file is always complete.
- **Batch mode** — scan a directory, translate files in order, random inter-file sleep to avoid throttling, move processed files to a `done/` dir.
- **Pydantic-validated config** — typed config model with clear error messages for bad values.
- **webvtt-py parser** — correct handling of standard VTT features including multi-line captions.

## Requirements

- Python 3.10+
- AWS credentials with Bedrock access to the configured model
- Dependencies listed in `requirements.txt`

## Installation

```bash
git clone <repository-url>
cd vtt-translator
pip install -r requirements.txt
```

Configure AWS credentials (any standard method works):

```bash
aws configure
# or export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION
```

## Quickstart

### Generate a default config

```bash
python main.py config my_config.json
```

This writes a JSON file with every tunable option. Edit it to taste — see `examples/config.example.json` for reference.

### Estimate before you translate

Dry-run a file to see how many LLM calls and characters are involved, without spending tokens:

```bash
python main.py estimate path/to/input.vtt --config my_config.json
```

### Translate a single file

```bash
python main.py translate input.vtt output.vtt --config my_config.json
```

Override specific options on the command line:

```bash
python main.py translate input.vtt output.vtt \
    --target-language ja \
    --chunk-size 30 \
    --model us.anthropic.claude-3-7-sonnet-20250219-v1:0
```

### Batch translate a directory

```bash
python main.py batch \
    --input-dir ./vtt \
    --output-dir ./vtt/zh \
    --done-dir ./vtt/done \
    --start 0 --end 10
```

Files already present in `done_dir` or whose translated counterpart already exists in `output_dir` are skipped.

### Use as a library

```python
from vtt_translator import Config, VttTranslator, VttTranslatorManager

# Single file
cfg = Config.load("my_config.json")
VttTranslator(cfg).translate_vtt("input.vtt", "output.vtt")

# Batch
VttTranslatorManager(cfg).batch_process()
```

## Configuration

All options live in a JSON file (or can be overridden on the CLI). The most important ones:

| Key | Default | Meaning |
|---|---|---|
| `provider` | `bedrock` | LLM provider name (only `bedrock` today). |
| `model_id` | `us.anthropic.claude-3-7-sonnet-20250219-v1:0` | Model identifier for the provider. |
| `aws_region` | `us-west-2` | AWS region for Bedrock. |
| `max_tokens` | `4096` | Max tokens the model may return per call. |
| `proxy_url` | `null` | Optional HTTP(S) proxy for provider traffic, e.g. `"http://127.0.0.1:8118"`. Leave `null` for a direct connection. |
| `source_language` | `en` | Source language code. |
| `target_language` | `zh` | Target language code (also used as the output file suffix, e.g. `name-zh.vtt`). |
| `chunk_size` | `50` | Number of captions per LLM call. Larger = fewer calls + better global context, but more tokens per call. |
| `context_window` | `5` | Captions to include before/after each chunk as context only (not translated). |
| `max_retries` | `5` | Max retries for transient errors (throttling, 5xx, network). |
| `retry_base_delay` | `2.0` | Base delay for exponential backoff. |
| `retry_max_delay` | `60.0` | Cap on any single backoff wait. |
| `api_sleep_time` | `2.0` | Fixed sleep after each successful LLM call. |
| `min_sleep_time` / `max_sleep_time` | `180` / `300` | Random sleep between files in batch mode. |
| `fallback_to_source` | `true` | If translation fails, use the original text (rather than fail the whole file). |
| `fallback_marker` | `""` | Optional suffix appended to fallback captions so they are grep-able. |
| `input_dir` / `output_dir` / `done_dir` / `log_dir` | `./vtt`, `./vtt/zh`, `./vtt/done`, `./logs` | Directory layout. |

## How translation works

1. `vtt_parser.parse_vtt` reads the file into `Caption` objects (timestamp + text + stable source index).
2. `chunker.split_into_chunks` splits the captions into batches of `chunk_size`, each with a `context_window` of surrounding context.
3. For each chunk, `prompt_builder.build_batch_prompt` produces a numbered prompt:
   ```
   [1] First caption text.
   [2] Second caption text.
   ...
   ```
4. The LLM is asked to return the same format. `validator.parse_numbered_response` maps the numbers back to the original captions.
5. If any number is missing from the response, the chunk is retried once. Any still-missing caption is translated on its own as a fallback. If *that* also fails, the original text is used (configurable).
6. `vtt_parser.write_vtt` writes a new VTT file using the original timestamps and the collected translations.

## Project layout

```
vtt-translator/
├── main.py                    # CLI entry point
├── requirements.txt
├── README.md
├── examples/
│   └── config.example.json
└── vtt_translator/
    ├── __init__.py
    ├── config.py              # pydantic Config model
    ├── utils.py               # logging, file helpers
    ├── vtt_parser.py          # webvtt-py based parser/writer
    ├── chunker.py             # chunking with context windows
    ├── prompt_builder.py      # numbered-batch prompt templates
    ├── validator.py           # parse + validate LLM responses
    ├── translator.py          # single-file orchestrator
    ├── manager.py             # batch manager
    └── llm/
        ├── __init__.py
        ├── base.py            # LLMProvider ABC + error types
        ├── bedrock.py         # Bedrock/Anthropic implementation
        └── factory.py         # build provider from Config
```

## Roadmap

- Concurrent translation of multiple files and/or multiple chunks.
- Resumable translation (progress file per input).
- Cost estimation command (token counting + price tables).
- Additional providers (OpenAI, Gemini, local models).
- Unit tests and CI.
