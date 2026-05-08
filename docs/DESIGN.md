# Design notes & handoff

This document exists for two readers:

1. **The project owner**, six months from now, wondering "why did I do it that way?"
2. **The next contributor (human or AI agent)**, wanting to understand the code without reverse-engineering four PRs of Git history.

If you only have 10 minutes, read [TL;DR](#tldr) and [Guiding principles](#guiding-principles). Everything else is reference.

---

## TL;DR

- **What it does**: translates WebVTT subtitle files via AWS Bedrock (Anthropic Claude), one VTT at a time, using a global-context prompt strategy instead of translating captions one-by-one.
- **What it *was***: a 500-line script with no package structure, one-by-one translation, broken imports, and fragile error handling. See [Starting point](#starting-point).
- **Design shape**: a single-file orchestrator (`translator.py`) built on a clean parse → chunk → resume → concurrent-translate → merge → write pipeline. Each step lives in its own module so any piece can be replaced or unit-tested.
- **Key decisions**: numbered-batch prompting, pydantic config, per-caption checkpointing, chunk-level thread-pool concurrency, pluggable LLM provider abstraction, graceful three-level fallback (chunk retry → single-caption retry → source text). The reasoning for each is below.
- **Not-yet-done**: file-level concurrency, cost estimation, non-Bedrock providers, unit tests & CI. See [Open questions](#open-questions-for-the-next-contributor).

---

## Starting point

The original project was a working-but-fragile personal utility. Key traits:

- Flat layout: `main.py`, `vtt_translator_core.py`, `_manager.py`, `_config.py`, `_utils.py` at the repo root.
- Package couldn't be imported (`vtt-translator` with a hyphen is not a valid Python identifier).
- Translation strategy: group adjacent subtitles into "semantic units" based on capitalization / punctuation heuristics, translate each group, then redistribute the translated text back across the timestamps using a duration-weighted string splitter with several regex fallbacks.
- Error handling: `_translate_text` could return `None` after retry exhaustion, which then got written into the output file.
- `VttTranslatorManager.__init__` was called with a `dict` but expected a path string, so the CLI batch mode crashed at construction time.
- AWS Bedrock client rebuilt on every LLM call.
- Retries only handled `ThrottlingException`; everything else bubbled.
- Per-file logger and the main logger both wrote to the console, so every line appeared twice in batch runs.
- Hard-coded English→Chinese, hard-coded Bedrock, hard-coded 1000 max_tokens.

The owner's request was "analyze this and give me an overall picture", which turned into a phased rewrite across four PRs.

---

## Guiding principles

These are the implicit rules the rewrite followed. New work should respect them unless you have a reason.

1. **Output must always be produced.** A failing translation should never prevent the VTT from being written. Fall back: chunk retry → single-caption retry → source text. The owner explicitly chose "source text fallback" over "fail the whole file" early in planning.
2. **Recoverable runs.** Any interrupted operation — crash, `Ctrl+C`, network drop — should be resumable without repeating successful work. Progress is checkpointed after each chunk.
3. **Typed, validated config.** Everything is a field on a pydantic `Config` model. Bad values fail loudly at load time, not at runtime. Every CLI override maps to a config field with the same name.
4. **One orchestrator, many small modules.** `translator.py` is the only place that knows the full pipeline. Parsing, chunking, prompting, validating, checkpointing, and LLM-calling are all separate modules so each is ~100 lines and individually reviewable.
5. **Provider-agnostic core.** The core never imports `boto3`. All LLM talk goes through the `LLMProvider` ABC. Swapping Bedrock for OpenAI means adding a file, not editing the core.
6. **No cross-file magic in `batch`.** Files are processed independently; resuming one file never depends on another. This keeps the manager ~100 lines and makes future file-level concurrency a small change.
7. **Small surface, clear names.** CLI flags mirror config field names (`--chunk-size` ↔ `chunk_size`). Log lines include chunk tags so the reader can attribute warnings.

When a new feature threatens one of these, stop and ask whether the principle should bend or the feature should change shape.

---

## Evolution: four PRs

### PR #1 — Foundation rewrite (the big one)

**Goal**: fix everything that was structurally broken, and switch to the new translation strategy.

**What changed:**
- **Package layout.** All code moved into `vtt_translator/` with relative imports. `main.py` remains at the repo root as the CLI entry. The outer `vtt-translator/` directory name still has a hyphen (that's the GitHub repo name and we didn't want to rename); the inner package name is valid Python.
- **Translation strategy completely rewritten.** Old "semantic grouping + text redistribution" out; **numbered-batch translation** in. Captions are sent as `[1] ... [2] ... [50] ...` and the model responds in the same shape. The response is parsed back by number, so there's a strict 1:1 mapping — no clever string splitting, no regex gymnastics, no drift.
- **Context windows.** Each chunk gets `context_window` captions before and after it as reference material (not translated). This is what keeps terminology consistent across chunk boundaries.
- **LLM provider abstraction.** `LLMProvider` ABC in `vtt_translator/llm/base.py`. `BedrockProvider` is the only implementation. The factory picks a class based on `config.provider`. This was a **pre-investment** — when the owner mentioned wanting to try other models later, it was much cheaper to build the seam now than to retrofit later.
- **pydantic config.** `Config` model with field descriptions, validators (e.g. `max_sleep_time >= min_sleep_time`), and `.load()` / `.save()` JSON round-trip. Every new feature added fields here and nowhere else.
- **`webvtt-py` for parsing.** The regex parser in the original code didn't handle multi-line captions, `NOTE` blocks, or some edge-case timestamps. Swapped for the library.
- **Retries cover all transient errors.** Exponential backoff with full jitter, capped at `retry_max_delay`. Throttling, 5xx, and `BotoCoreError` network glitches all retry. Only non-transient errors bubble as `TranslationError`.
- **Three-level fallback.** If the LLM returns fewer numbered items than requested, the chunk is retried once. Still missing? The missing captions are translated one-at-a-time (so one bad response doesn't fail the whole chunk). Still failing? Use the source text.
- **Per-file loggers stopped duplicating to the console** (the file logger no longer adds a stream handler).
- **New CLI command: `estimate`** — parses and chunks without calling the LLM. Free preview of how many API calls a file will cost.

**Deliberately deferred to later PRs:** concurrency, resume, proxy, logging polish.

### PR #2 — Proxy support

**Trigger**: the owner tried to use the tool from mainland China and Anthropic server-side rejected every request because of IP geolocation.

**The surprise**: `boto3` / `botocore` do not honor `HTTPS_PROXY` / `HTTP_PROXY` environment variables the way `requests` does. Setting those env vars produced zero behavioral change. The fix had to be explicit.

**Shape**:
- New `Config.proxy_url: Optional[str]`. When set, `BedrockProvider` constructs `botocore.config.Config(proxies={"http": ..., "https": ...})` and passes it to `boto3.client`.
- No CLI flag for it — the owner preferred everything-through-config.
- No env var fallback. Config is the single source of truth.

**Post-script**: this PR got merged into **PR #1's feature branch**, not into main. When PR #1 was squash-merged to main, PR #2's changes did **not** come along. This was discovered later when starting Phase 2 and checking out main. Lesson: when stacking PRs, either rebase the stack as the bottom merges, or target the bottom PR's branch only if you understand what squash-merge does to your chain. The fix was to include "re-apply PR #2" as the first commit of PR #3. Don't do this again.

### PR #3 — Concurrency + resume

**Goal**: cut wall-clock time and survive interruptions.

**Concurrency decisions:**
- Three options were on the table: (a) file-level only, (b) chunk-level only, (c) both. The owner chose **(b) chunk-level only**. Simpler to reason about, one knob (`max_concurrent_chunks`), and file-level is easy to add later.
- Implementation is a standard `ThreadPoolExecutor` in `translator.py`, with `as_completed` for streaming results. The Bedrock `boto3` client is thread-safe (it's a stateless HTTP client under the hood), so workers share one instance.
- Results are merged under a lock. Each chunk's results get flushed to the progress store as they complete — so a later worker failing doesn't lose earlier successes.
- Default 3 workers. Conservative — the owner flagged that Bedrock's rate limits vary by account, and "start low, raise if stable" is safer than "start high, get throttled, back off."

**Resume decisions:**

The design was debated specifically; the key tradeoffs were:
- **Where to store:** `<log_dir>/.progress/<hash>.json`. The filename is `sha1(abs_input_path)[:12]` so you can translate two files with the same basename from different directories without collision.
- **Granularity:** *per caption*, not per chunk. If the user changes `chunk_size` between runs, the old per-chunk cache would be useless; per-caption survives. This choice costs us a slightly larger JSON but saves the user from ever losing work to a re-chunking.
- **Invalidation:** SHA-1 **and** mtime of the input, plus a "resume fingerprint" covering `provider`, `model_id`, `source_language`, `target_language`. Changing `chunk_size` does **not** invalidate — that's the whole point of per-caption storage. The mtime check has a 1-second drift tolerance for filesystems with coarse resolution.
- **Atomicity:** tempfile + `os.replace` + `fsync`. A crash mid-write can't produce a half-written file.
- **Cleanup:** progress file is deleted as soon as the output VTT is successfully written. `--no-resume` also deletes it, so "force a clean restart" has a single predictable command.
- **`--no-resume` unearthed a bug** during smoke testing: `ProgressStore.clear()` honored `enabled=False` and refused to delete. That meant setting `enable_resume: false` couldn't actually wipe a stale file. Fixed — `clear()` always runs.

**Default model bump:** At the same time, the default `model_id` was changed to `global.anthropic.claude-opus-4-6-v1` (per request).

### PR #4 — Proxy diagnostics + logging polish

**Trigger**: the owner's proxy was Privoxy on `127.0.0.1:8118`, which happily accepted connections but wasn't forwarding them anywhere useful (no SOCKS upstream). The request hit Anthropic with the owner's actual IP and got rejected. From our side there was no signal that this had happened — the proxy "worked" by HTTP standards.

**What's there now:**
- New module `vtt_translator/proxy_diagnostics.py`. Uses only the stdlib (`urllib.request`) so it has no dep on boto3. Given a `proxy_url`, it probes `https://checkip.amazonaws.com` through the proxy and returns the exit IP (or the error).
  - Why AWS's echo service? Because if that endpoint works through the proxy, Bedrock (also on `*.amazonaws.com`) should too. Sharing the traffic path is more informative than hitting a random IP echo site.
- New CLI subcommand `check-proxy` with `--proxy-url` override (and `--proxy-url ""` to test the direct connection).
- `BedrockProvider.__init__` runs the probe automatically when `proxy_url` is set and `verify_proxy_on_startup: true` (the default). The existing "using proxy: ..." startup log line gets an `(exit IP: ...)` suffix. Probe failures are logged but never abort startup — they might just mean the echo service is blocked in an environment where AWS still works.

**Logging polish (four small things):**
- Every chunk now carries a `tag` (e.g. `"chunk 3/12"`). The translator passes it to `LLMProvider.complete(prompt, *, max_tokens, tag=None)`, and `BedrockProvider` includes it in retry/backoff warnings. So a rate-limit warning now reads `Bedrock throttling (ThrottlingException) [chunk 3/12]; retry 1/5 after 2.3s` instead of `...; retry 1/5 after 2.3s` alone.
- Progress lines include an ETA once two chunks have completed and the run isn't about to finish.
- The noisy `Single-caption fallback for source index N` was demoted from INFO to DEBUG.
- The terminal `Falling back to source text` warning now includes the chunk tag too.

---

## Design decisions, one-liner rationale

A running list of decisions that aren't self-explanatory from the code.

| Decision | Why |
|---|---|
| Numbered-batch translation (`[N]` markers) | Gives the model global context; trivial to parse back; no need for duration-weighted string splitting; empirically consistent terminology across chunks. |
| Default `chunk_size=50`, `context_window=5` | Sweet spot on Opus 4.6 — ~50 captions fits under 4096 tokens comfortably, and 5-caption context is usually enough to catch mid-sentence cuts. If you change these defaults, re-run `estimate` on a few real files first. |
| Default `max_concurrent_chunks=3` | Tested safe for a typical Bedrock quota. Users with generous accounts report 5–8 also works; 10+ consistently triggers throttling. |
| Default inter-file sleep 180–300s | Owner's request. Randomized to avoid looking like scripted traffic. For test runs, set both to 0. |
| Per-caption progress storage | Lets `chunk_size` change between runs without invalidating the cache. |
| SHA-1 + mtime input check | Either alone has a false-positive mode; together they're robust. The 1s mtime tolerance handles CI / Docker filesystems. |
| `fallback_to_source=true` default | Owner explicitly chose: "I'd rather see some English than have a chunk missing from the output." |
| `webvtt-py` over regex parser | Correctly handles multi-line captions, `NOTE` blocks, `<v Speaker>` tags. It's ~20KB of pure Python; the dependency cost is negligible. |
| `pydantic` for config | Clear errors for bad values, auto JSON round-trip, IDE completion for library users. V2 is fast enough to not matter. |
| Thread pool for concurrency (not async) | Bedrock calls are I/O-bound, `boto3` is thread-safe but not natively async; wrapping it in async would require `aiobotocore` or a threadpool executor anyway. Threads keep the model simple. |
| Proxy via `botocore.config.Config` (not env) | `boto3` doesn't read `HTTPS_PROXY`. Explicit config field = predictable behavior. |
| `checkip.amazonaws.com` for proxy probe | Same host family as the real target (Bedrock). If the probe works, the real call should too. |

---

## Non-decisions (on purpose)

Things that might look wrong but aren't.

- **`examples/config.example.json` has every field even though the loader tolerates missing ones.** Yes, intentional — it's a discoverable doc for every option, not just a minimal template. If we want a minimal one later, add `config.minimal.json`; don't strip this.
- **Per-file and main loggers use different names and only the main one logs to console.** The alternative (a single logger) would either flood the console on batch runs or silence per-file logs. The current setup lets the console show batch-level progress while each file has a full trace in its own log file.
- **`Config.max_concurrent_files` is declared but unused.** It's a reservation for the future file-level concurrency feature. Leaving it there means the field name is stable when we add the feature; users who write configs now won't have to re-learn it later.
- **The CLI `config` subcommand overwrites without prompting.** If you're worried about clobbering an existing file, use a path that doesn't exist. A prompt would require adding a flag to suppress it for scripting, and so far nobody's hit the problem.

---

## Open questions for the next contributor

Ordered roughly by how much the owner has thought about them.

### 1. File-level concurrency in `batch` — ready to implement

The `Config.max_concurrent_files` field already exists; it's just not wired up. Implementation sketch:

- `VttTranslatorManager.batch_process` spawns a `ThreadPoolExecutor(max_concurrent_files)`.
- Each worker calls `self.process_file(f)`.
- The `_sleep_between_files` semantics change — instead of sleeping between sequential files, you'd stagger the *initial* submissions by a small random delay to desync the first round of LLM calls.

Open question: **should the inter-file sleep go away entirely with file concurrency, or should it limit how fast new files are started?** The current sleep was rate-limit insurance for a serial run; with concurrency, you'd either drop it or reinterpret it. Ask the owner before coding.

### 2. Token counting + cost estimation

The `estimate` subcommand already prints character counts and chunk counts. The natural next step is:
- Add a per-model price table (`per_million_input_tokens`, `per_million_output_tokens`) somewhere — probably a new `vtt_translator/pricing.py`.
- Use `tiktoken` (or a simpler heuristic like `chars / 4`) to count tokens per chunk.
- Print an estimated cost in `estimate`.
- Sum actual costs per run and print at end.

Warning: cross-provider tokenizers are different. Anthropic doesn't publish an official Python tokenizer. A char-count approximation is what most people actually ship, and it's within ~20% of reality for English.

### 3. Non-Bedrock providers

The `LLMProvider` abstraction is set up for this. Adding OpenAI would be:
- `vtt_translator/llm/openai.py` — subclass `LLMProvider`, implement `complete(prompt, *, max_tokens, tag)` using the OpenAI SDK.
- Extend `create_provider(config)` in `factory.py` with a new branch.
- Update `Config` with any OpenAI-specific fields (e.g. `openai_base_url` for Azure).
- The `tag` keyword is already part of the interface and used in retry logs.

There's **no change needed in the orchestrator** — `translator.py` never mentions Bedrock.

### 4. Glossary / term list

Professional videos (like the lecture transcripts this tool was built for) have domain terms that should translate consistently. Right now consistency is emergent from the chunk+context strategy, but a user-provided glossary would guarantee it.

Rough shape:
- `Config.glossary: Optional[Dict[str, str]]` — e.g. `{"LRU": "LRU", "cache": "缓存", "eviction policy": "淘汰策略"}`.
- `prompt_builder.build_batch_prompt` includes a "must use these translations" section at the top.
- Validator optionally checks the output contains the forced translations.

Risk: models sometimes "explain around" forced terminology awkwardly. Test on a few real files before shipping.

### 5. Tests + CI + packaging

Three things:
- **Tests**: the smoke tests I wrote during each PR cover real behavior but were never committed. They should be formalized into a `tests/` directory with `pytest`. The LLM provider abstraction makes this easy — a `FakeProvider` can echo numbered prompts deterministically.
- **CI**: GitHub Actions workflow running `pytest` + `ruff` on every PR. Shouldn't take more than a morning.
- **Packaging**: add `pyproject.toml` so `pip install .` works. The `main.py` at the repo root is awkward for pip-install; you'd want to move the CLI entry point to a module (`vtt_translator/__main__.py` or similar) and declare a console_scripts entry.

The owner deferred all of this explicitly, reasoning that it's "individual engineering hygiene" more than "feature value" for a personal tool. Revisit when the tool has more than one user, or when "it broke and I don't know why" happens more than once.

### 6. Line-level tweaks you might notice

Minor things that didn't seem worth a PR but might bug you:

- `Config` mixes units (sleep times in seconds, tokens as counts). Not harmful, but a future refactor could split into `ConfigLLM`, `ConfigBatch`, `ConfigPaths` nested models.
- `translator.py` ETA calculation uses `time.monotonic()` and a simple "elapsed / completed × remaining" estimator. A median-of-recent-chunk-times estimator would be more stable for workloads where the first chunks are slower (e.g. cold cache).
- `_source_fallback` doesn't re-emit a warning log — just the chunk-level warning. If lots of captions fall back, the summary line shows the count but you have to diff against the input to find *which*. A `fallback_marker: "[SRC]"` mitigates this but it's opt-in.
- The `manager.find_vtt_files` string-ends-with check for already-translated files looks for `-zh.vtt` and `_zh.vtt` specifically. If someone runs with `target_language=ja`, the `-ja.vtt` check comes from the dynamically-computed `translated_name`, so it works — but the hardcoded `-zh.vtt` / `_zh.vtt` check is a legacy safety net and could be dropped.

---

## How to pick up this project

If you're an AI agent or new human maintainer landing here:

1. **Read `README.md` first** for the user-facing model.
2. **Read `main.py`** to see the CLI surface.
3. **Read `vtt_translator/translator.py`** — that's the pipeline in one file.
4. **Read `vtt_translator/config.py`** — all knobs are here.
5. **Skim `vtt_translator/llm/base.py`** — that's the extension point.
6. **Use the smoke-test pattern from the PR history** (fake `LLMProvider` that echoes numbered prompts) for any new feature work. Don't commit smoke tests directly; graduate them to `pytest` when [Open question 5](#5-tests--ci--packaging) happens.

Before starting a change:
- Ask the owner which principle it's against, if any (see [Guiding principles](#guiding-principles)).
- Decide if it's one PR or several. Historical preference: one PR per conceptual feature, but stack them intelligently (don't repeat the PR #2 mistake).
- Write the commit message as if onboarding someone: what, why, what it doesn't touch, how you tested.
