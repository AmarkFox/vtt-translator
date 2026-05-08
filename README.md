# VTT Subtitle Translator

A Python tool that translates WebVTT subtitle files using LLMs. Version 2.x uses a **numbered batch translation** strategy: the file is translated in large chunks with surrounding context, so the model has a global view of the transcript and terminology stays consistent.

> **Why this exists**: the first version translated subtitles one-or-two at a time, which meant the same term got translated three different ways across a file. See [`docs/DESIGN.md`](docs/DESIGN.md) for the full story of how the current design came to be, plus the open questions for whoever picks this up next.

---

## Table of contents

- [Quickstart](#quickstart)
- [Commands](#commands)
  - [`translate`](#translate) — single file
  - [`batch`](#batch) — a directory of files
  - [`estimate`](#estimate) — dry-run, no LLM calls
  - [`check-proxy`](#check-proxy) — diagnose proxy
  - [`config`](#config-generate) — generate default config
- [Configuration reference](#configuration-reference)
- [How translation works](#how-translation-works)
- [Resumable translation](#resumable-translation)
- [Batch mode explained](#batch-mode-explained)
- [Using as a Python library](#using-as-a-python-library)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)

---

## Quickstart

```bash
# 1. Clone & install (Python 3.10+)
git clone https://github.com/AmarkFox/vtt-translator.git
cd vtt-translator
pip install -r requirements.txt

# 2. Configure AWS credentials (any standard method works)
aws configure
# or: export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION

# 3. Generate a config, edit it to taste
python main.py config my_config.json
$EDITOR my_config.json

# 4. (Optional but recommended) make sure your proxy is working
python main.py check-proxy --config my_config.json

# 5. Translate something
python main.py translate input.vtt output-zh.vtt --config my_config.json
```

### Requirements

| | |
|---|---|
| Python | 3.10+ |
| AWS | Credentials with Bedrock access to the configured model (default: Claude Opus 4.6) |
| Dependencies | `boto3`, `botocore`, `pydantic>=2`, `webvtt-py` (all in `requirements.txt`) |
| Optional | An HTTP proxy if your region (e.g. mainland China) is blocked by Anthropic's availability rules |

---

## Commands

All commands share one CLI entry point: `python main.py <command> …`.

Global-ish flags you'll see on most commands:

| Flag | Type | Description |
|---|---|---|
| `--config PATH` | string | Path to JSON config file (see [Configuration reference](#configuration-reference)). Omit to use pure defaults. |
| `--verbose` / `-v` | flag | Enable DEBUG-level logging. Shows per-caption fallback details, etc. |

### `translate`

Translate a single VTT file.

```bash
python main.py translate <input.vtt> <output.vtt> [options]
```

| Argument | Type | Default | Description |
|---|---|---|---|
| `input` (positional) | path | — | Source VTT file. |
| `output` (positional) | path | — | Destination path for the translated VTT. |
| `--config` | path | — | Config file. |
| `--model` | string | — | Override `model_id` for this run only. |
| `--provider` | string | — | Override `provider` for this run only. |
| `--source-language` | lang code | — | Override `source_language`. |
| `--target-language` | lang code | — | Override `target_language`. |
| `--chunk-size` | int | — | Override `chunk_size`. |
| `--context-window` | int | — | Override `context_window`. |
| `--max-concurrent-chunks` | int | — | Override `max_concurrent_chunks`. |
| `--no-resume` | flag | off | Ignore any existing progress file and retranslate from scratch. Also deletes the stale progress file. |
| `--verbose` / `-v` | flag | off | DEBUG logging. |

**Examples:**

```bash
# Typical run
python main.py translate lecture.vtt lecture-zh.vtt --config my_config.json

# Target Japanese instead, use smaller chunks, more parallelism
python main.py translate lecture.vtt lecture-ja.vtt \
    --config my_config.json \
    --target-language ja \
    --chunk-size 30 \
    --max-concurrent-chunks 5

# Force a fresh translation, discarding any checkpoint
python main.py translate lecture.vtt lecture-zh.vtt \
    --config my_config.json \
    --no-resume
```

Exit codes:
- `0` — output file written successfully (even if some captions fell back to source text)
- `1` — parsing or writing failed catastrophically

### `batch`

Translate every unprocessed `.vtt` file in a directory. See [Batch mode explained](#batch-mode-explained) for the full semantics.

```bash
python main.py batch [options]
```

| Argument | Type | Default | Description |
|---|---|---|---|
| `--start` | int | `0` | Index of the first file to process (0-based, after sorting and filtering). |
| `--end` | int | all | Index of the last file **(exclusive)**. `--start 0 --end 10` = files 0..9, which is 10 files. |
| `--input-dir` | path | from config | Override `input_dir`. |
| `--output-dir` | path | from config | Override `output_dir`. |
| `--done-dir` | path | from config | Override `done_dir`. |
| `--config` | path | — | Config file. |
| `--no-resume` | flag | off | Same as in `translate`, applied per file. |
| `--verbose` / `-v` | flag | off | DEBUG logging. |
| (all common overrides) | | | `--model`, `--chunk-size`, `--max-concurrent-chunks`, etc. |

The batch manager:
1. Lists `*.vtt` in `input_dir`, sorted alphabetically.
2. Filters out files whose translation already exists (in `output_dir` as `<name>-<target_language>.vtt`) or whose source already moved to `done_dir`.
3. Takes `files[start:end]` from what's left.
4. Processes them **serially**, moving each successful source file to `done_dir`.
5. Between files, sleeps a **random** duration in `[min_sleep_time, max_sleep_time]` seconds.

**Examples:**

```bash
# Translate everything in ./vtt (first time)
python main.py batch --config my_config.json

# Only the first 10 files (useful when iterating on config)
python main.py batch --config my_config.json --start 0 --end 10

# Files 10..19 (continue where the previous run stopped)
python main.py batch --config my_config.json --start 10 --end 20

# Override directories without editing the config file
python main.py batch \
    --input-dir ./my-vtts \
    --output-dir ./my-vtts/zh \
    --done-dir ./my-vtts/done
```

Exit code is `0` iff **every** selected file succeeded.

### `estimate`

Dry-run: parse and chunk a file, print stats. **No LLM calls, no cost, no network.**

```bash
python main.py estimate <input.vtt> [options]
```

Accepts the same config-override flags as `translate`. Output example:

```
File:            95.Caching.vtt
Captions:        563
Total characters:31045
Chunk size:      50
Context window:  5
Chunks:          12 (= number of LLM calls, before fallbacks)
Concurrency:     3 chunk(s) in parallel
Resume enabled:  true
Model:           bedrock/global.anthropic.claude-opus-4-6-v1
Source -> Target:en -> zh
```

Use this to sanity-check a file before spending money, or to see how `--chunk-size` changes the LLM call count.

### `check-proxy`

Probe your proxy and report its **exit IP**. **No LLM calls.** Uses `https://checkip.amazonaws.com` because if that works through the proxy, Bedrock should too.

```bash
python main.py check-proxy [options]
```

| Argument | Type | Default | Description |
|---|---|---|---|
| `--config` | path | — | Read `proxy_url` from this config file. |
| `--proxy-url` | string | from config | Override the proxy URL for this probe. Pass `""` to test the **direct** connection. |
| `--timeout` | float | `10.0` | Probe timeout in seconds. |

Sample output:

```
Proxy:     http://127.0.0.1:8118
Probe URL: https://checkip.amazonaws.com
Exit IP:   104.16.x.x
Notes:     If this IP is your own machine or a region Anthropic blocks
           (e.g. China), the proxy is reachable but not actually
           forwarding traffic abroad. Check your proxy's upstream
           configuration.
```

If the exit IP is your home IP when you expected a foreign one, your proxy is **reachable but not forwarding** (a very common Privoxy misconfiguration). See [Troubleshooting](#troubleshooting).

Exit code is `0` on successful probe, `1` otherwise.

### `config` (generate)

Write a JSON file containing every field with its default value. Useful as a starting template.

```bash
python main.py config <output-path>
```

---

## Configuration reference

All settings live in one JSON file (see `examples/config.example.json` for a filled-in sample). Values have sensible defaults and are validated with pydantic — a typo like `"chunk_size": -1` will produce a clear error before any translation runs.

Most options can also be overridden per-run via CLI flags; see each command's table above.

### Directories

| Key | Default | What it's for |
|---|---|---|
| `input_dir` | `./vtt` | Where `batch` looks for source `.vtt` files. |
| `output_dir` | `./vtt/zh` | Where translated files are written. The filename gets a `-<target_language>.vtt` suffix (e.g. `foo.vtt` → `foo-zh.vtt`). |
| `done_dir` | `./vtt/done` | Successful source files are **moved** (not copied) here after `batch` finishes them, so re-running doesn't reprocess them. |
| `log_dir` | `./logs` | Log files and the `.progress/` checkpoint directory live here. |

### LLM provider

| Key | Default | What it's for |
|---|---|---|
| `provider` | `bedrock` | LLM backend. Today only `bedrock` is implemented — the abstraction in `vtt_translator/llm/` is ready for OpenAI / Gemini / local models. |
| `model_id` | `global.anthropic.claude-opus-4-6-v1` | Model ID the provider understands. For Bedrock this is the inference-profile ARN short form. |
| `aws_region` | `us-west-2` | AWS region. Must have Bedrock model access enabled for the chosen `model_id`. |
| `max_tokens` | `4096` | Cap on the LLM response size per call. 4096 is enough for ~50 Chinese captions; raise if you use a larger `chunk_size`. |
| `proxy_url` | `null` | HTTP(S) proxy URL for all Bedrock traffic, e.g. `"http://127.0.0.1:8118"`. `null` = direct connection. Set this if Anthropic blocks your region — they do a server-side IP check. |
| `verify_proxy_on_startup` | `true` | Probe `proxy_url` once at startup and log the exit IP. Adds ~one HTTP round-trip. Set to `false` if the probe service is blocked in your network but AWS is reachable. |

### Languages

| Key | Default | What it's for |
|---|---|---|
| `source_language` | `en` | Source language code. Used in the prompt so the model knows what to translate. |
| `target_language` | `zh` | Target language code. Used in the prompt **and** as the output file suffix (e.g. `-zh.vtt`). Supported codes include `en`, `zh`, `zh-hant`, `ja`, `ko`, `es`, `fr`, `de`, `pt`, `ru`, `it`, `ar`. Unknown codes work too — they're just passed through verbatim. |

### Chunking

| Key | Default | What it's for |
|---|---|---|
| `chunk_size` | `50` | Captions sent to the LLM per call. Larger = fewer calls + better global context + higher token cost per call. Valid range: 1–500. For a 30-minute lecture this means ~10 calls at default. |
| `context_window` | `5` | Captions to include **before and after** each chunk as context for the model (not translated themselves). Helps the model pick up mid-sentence cuts. 0 disables. Valid range: 0–50. |

### Concurrency

| Key | Default | What it's for |
|---|---|---|
| `max_concurrent_chunks` | `3` | Chunks translated in parallel within **one** file, using a thread pool. Higher = faster wall-clock time but more likely to hit Bedrock rate limits. 1 = fully serial. Valid range: 1–32. |
| `max_concurrent_files` | `1` | Reserved for a future file-level parallelism feature in `batch`. **Currently has no effect.** |

### Resumable translation

| Key | Default | What it's for |
|---|---|---|
| `enable_resume` | `true` | If true, per-file progress is checkpointed after each chunk under `<log_dir>/.progress/`, and the next run picks up where it stopped. See [Resumable translation](#resumable-translation) for the full story. |

### Retry / backoff

These apply to transient errors from the LLM provider — rate-limit 429s, server 5xx, network glitches.

| Key | Default | What it's for |
|---|---|---|
| `max_retries` | `5` | Max retry attempts per failing call before giving up. 0 disables retries. Valid range: 0–20. |
| `retry_base_delay` | `2.0` (seconds) | Starting delay for exponential backoff. With full jitter, the first retry waits `random(0, 2)` seconds, the second `random(0, 4)`, and so on, doubling each time. |
| `retry_max_delay` | `60.0` (seconds) | Cap on any single backoff wait, so a 5th retry doesn't sleep for `2×2⁵ = 64s`. |

### Throttling (non-retry pacing)

| Key | Default | What it's for |
|---|---|---|
| `api_sleep_time` | `2.0` (seconds) | Fixed sleep after **each successful** LLM call. Helps stay under rate limits when running many chunks in quick succession. Set to 0 if your account is generous. |
| `min_sleep_time` | `180` (seconds) | Minimum sleep between files in `batch` mode. |
| `max_sleep_time` | `300` (seconds) | Maximum sleep between files. Actual sleep is `random.randint(min, max)` — see [Batch mode explained](#batch-mode-explained) for why it's randomized. Set both to 0 for no inter-file sleep. |

### Fallback

| Key | Default | What it's for |
|---|---|---|
| `fallback_to_source` | `true` | If a chunk fails after retries **and** single-caption retranslation also fails, use the source text verbatim. Guarantees the output file is always complete. Set to `false` to leave failed captions as empty strings instead. |
| `fallback_marker` | `""` | Optional suffix appended to fallback captions, e.g. `"[UNTRANSLATED]"`. Makes it grep-able so you can find failures in the output file. Empty = no marker. |

---

## How translation works

```
  input.vtt
      │
      ▼
  parse_vtt ──► List[Caption] (timestamp + text + stable source index)
      │
      ▼
  split_into_chunks ──► List[Chunk]       each chunk has:
      │                                     target:  N captions to translate
      │                                     prev_context: context_window captions before (not translated)
      │                                     next_context: context_window captions after  (not translated)
      ▼
  ProgressStore.load ──► Dict[int, str]   captions already translated in a previous run
      │
      ▼
  ThreadPoolExecutor(max_concurrent_chunks) — process chunks that still need work
      │
      ▼ per chunk:
  build_batch_prompt ──► "[1] caption 1\n[2] caption 2\n..." + context sections
      │
      ▼
  LLMProvider.complete ──► raw text response
      │                    (retries on transient errors with exponential backoff + jitter)
      │
      ▼
  parse_numbered_response + validate_coverage
      │
      ├── all N numbered items present? ──► merge into results
      └── some missing? ──► retry the chunk ONCE
                            still missing? ──► translate each missing caption individually
                                                still failing? ──► use source text (if fallback_to_source)
      │
      ▼ after each chunk completes:
  ProgressStore.update(results)   atomic write to .progress/<hash>.json
      │
      ▼ after all chunks done:
  write_vtt ──► output-zh.vtt (original timestamps + translated text)
      │
      ▼
  ProgressStore.clear              delete checkpoint; run is clean
```

Two invariants worth knowing:
- **The output file is always produced** if the input was parseable. Chunks that can't be translated fall back to source text. A file only fails if parsing or file I/O fails.
- **No cross-file state.** `batch` processes files one at a time; resuming a file doesn't care about other files.

---

## Resumable translation

When `enable_resume: true` (the default), a **progress file** tracks which captions in a given input have already been translated. This survives `Ctrl+C`, network drops, and provider outages. The design goals:

- **Granular**: check point per-caption, not per-chunk — so if you change `chunk_size` between runs, the translations are still reused.
- **Safe**: atomic writes (tempfile + `os.replace` + `fsync`), so a crash mid-write can't corrupt it.
- **Auto-cleaning**: progress file is deleted as soon as the output VTT is successfully written.

### Where progress files live

```
<log_dir>/.progress/<sha1-of-abs-input-path[:12]>.json
```

The filename hashes the absolute input path so you can translate files with identical names from different directories without collision.

### When a progress file is invalidated (silently ignored)

- The input file's **content** or **mtime** changed since the checkpoint was written (both are stored; 1 second of mtime drift is tolerated for filesystems with coarse resolution).
- Any of these config fields changed: `provider`, `model_id`, `source_language`, `target_language`.
  - ⚠️ `chunk_size` and `context_window` are **not** in this list — those can change between runs because we store per-caption.

### Forcing a fresh translation

```bash
python main.py translate input.vtt output.vtt --no-resume
```

This **both** ignores any existing progress file **and** deletes it (so a later run without `--no-resume` also starts clean).

---

## Batch mode explained

A few things about `batch` that surprised at least one user (hi):

### `--start` / `--end` are file indices, not caption indices

The batch manager builds a sorted list of files to process, then takes `files[start:end]` (standard Python slice semantics — `end` is **exclusive**).

So if 20 unprocessed files are found:

| Command | Files processed |
|---|---|
| `batch --start 0 --end 10` | files 0..9 — **ten** files |
| `batch --start 10 --end 20` | files 10..19 |
| `batch --start 5` | files 5..19 (everything from index 5) |
| `batch --end 3` | files 0..2 (the first three) |
| `batch` | all 20 |

### Inter-file sleep is randomized on purpose

Between files, the manager sleeps `random.randint(min_sleep_time, max_sleep_time)` seconds. Default: 180–300 seconds, so **3–5 minutes between files**.

Why randomize instead of a fixed delay?
- **Avoid detection as scripted traffic.** A fixed cadence looks different from human usage to rate limiters.
- **Desync future parallel runs.** If you ever run multiple batches at once, fixed intervals would sync; random ones naturally stagger.

If your account is generous and you want to blast through a directory, set both to 0:

```json
"min_sleep_time": 0,
"max_sleep_time": 0
```

### Files already done are skipped

On startup, `batch` excludes a file if:
- the source has already been moved to `done_dir/<name>.vtt`, OR
- the translated output already exists at `output_dir/<name>-<target_language>.vtt`, OR
- the filename ends in `-zh.vtt` or `_zh.vtt` (legacy/safety net — won't try to translate a translation)

This means `Ctrl+C` and re-running is safe: finished files are skipped, the in-flight file resumes via the progress store, and unprocessed files continue fresh.

---

## Using as a Python library

The CLI is a thin wrapper; the same classes work programmatically.

```python
from vtt_translator import Config, VttTranslator, VttTranslatorManager

# Load your config (or construct Config() directly for pure defaults)
cfg = Config.load("my_config.json")

# Translate one file
VttTranslator(cfg).translate_vtt("input.vtt", "output.vtt")

# ... or disable resume for one call
VttTranslator(cfg).translate_vtt("input.vtt", "output.vtt", resume=False)

# Batch
mgr = VttTranslatorManager(cfg)
successes, total = mgr.batch_process(start_index=0, end_index=10)

# Plug in a custom LLM provider
from vtt_translator.llm import LLMProvider

class MyProvider(LLMProvider):
    @property
    def model_id(self):
        return "my-model"
    def complete(self, prompt, *, max_tokens, tag=None):
        # your implementation
        ...

VttTranslator(cfg, provider=MyProvider()).translate_vtt(...)
```

---

## Project layout

```
vtt-translator/
├── main.py                         # CLI entry point
├── requirements.txt
├── README.md                       # this file
├── docs/
│   └── DESIGN.md                   # how the current design came to be (handoff notes)
├── examples/
│   └── config.example.json         # every config field with a value
└── vtt_translator/
    ├── __init__.py                 # public API: Config, VttTranslator, VttTranslatorManager
    ├── config.py                   # pydantic Config model + Config.load/save/resume_fingerprint
    ├── utils.py                    # logger setup, file helpers
    ├── vtt_parser.py               # webvtt-py based Caption dataclass, parse_vtt, write_vtt
    ├── chunker.py                  # Chunk dataclass + split_into_chunks (with context windows)
    ├── prompt_builder.py           # numbered-batch prompt templates
    ├── validator.py                # parse_numbered_response + validate_coverage
    ├── translator.py               # single-file orchestrator (concurrent chunks + resume)
    ├── progress.py                 # ProgressStore (atomic-write, per-caption checkpoint)
    ├── proxy_diagnostics.py        # stdlib-only check_proxy() + ProxyCheckResult
    ├── manager.py                  # batch manager (VttTranslatorManager)
    └── llm/
        ├── __init__.py
        ├── base.py                 # LLMProvider ABC + TranslationError / RateLimitError
        ├── bedrock.py              # Bedrock (Anthropic messages API) implementation
        └── factory.py              # create_provider(config) — dispatch on config.provider
```

---

## Troubleshooting

### "Access to Anthropic models is not allowed from unsupported countries"

Anthropic blocks requests from certain regions (notably mainland China) at the IP level. You need a proxy whose **exit IP** is in a supported region.

1. Run `python main.py check-proxy --config my_config.json`.
2. If the exit IP shown is your home IP, your proxy isn't forwarding — check its upstream config. Privoxy on its own is just an HTTP-to-HTTP forwarder; you need `forward-socks5 / 127.0.0.1:1080 .` (or similar) in `privoxy.conf` pointing to a working SOCKS tunnel.
3. Shadowsocks / V2Ray / Clash etc. usually expose an HTTP proxy directly (commonly `http://127.0.0.1:7890`). Setting that as `proxy_url` skips Privoxy entirely.

### `boto3` seems to ignore `HTTPS_PROXY`

It does. Unlike `requests`, `botocore` does not auto-read those env vars. That's exactly why `proxy_url` exists — setting it in the config explicitly wires `botocore.config.Config(proxies=...)` into the Bedrock client.

### Everything is slow even with concurrency

Check the log for `Bedrock throttling` warnings. If you see any, your `max_concurrent_chunks` is too high for your account's Bedrock RPM. Try 2 or 1. The retry machinery will handle the throttling itself, but wall-clock time suffers.

### Progress file stuck after a weird crash

They self-invalidate if the input file changes, or if the relevant config fields change. Worst case just delete `<log_dir>/.progress/*.json`.

### Chunk responses come back without `[N]` markers

The model occasionally produces a paragraph instead of a numbered list. The orchestrator retries the chunk once; if it still comes back malformed, it translates each missing caption individually, then falls back to source text if *that* also fails. You'll see this in the log as `Incomplete numbered response` followed by `Single-caption fallback` (DEBUG) and/or `Falling back to source text for caption N` (WARNING).

---

## Roadmap

- File-level concurrency in `batch` mode (`max_concurrent_files`).
- Token counting + cost estimation (in `estimate` and post-run).
- Additional providers — OpenAI, Gemini, local models via the existing `LLMProvider` interface.
- Glossary / term-list injection for domain-specific consistency.
- `pytest` suite + GitHub Actions CI + `pyproject.toml` for pip-install.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the history of why things are the way they are, plus the open decisions waiting for the next contributor.
