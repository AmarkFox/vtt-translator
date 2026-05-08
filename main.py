"""CLI entry point for vtt-translator.

Subcommands:
  translate   Translate a single VTT file.
  batch       Translate all unprocessed VTT files in a directory.
  config      Generate a default config file.
  estimate    Dry-run: parse and chunk a file, print stats without calling the LLM.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from vtt_translator.chunker import split_into_chunks
from vtt_translator.config import Config
from vtt_translator.manager import VttTranslatorManager
from vtt_translator.translator import VttTranslator
from vtt_translator.utils import setup_logger
from vtt_translator.vtt_parser import parse_vtt


def _add_common_config_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="Path to JSON config file")
    p.add_argument("--model", help="Override model_id (e.g. a specific Claude model)")
    p.add_argument("--provider", help="Override LLM provider (default: bedrock)")
    p.add_argument("--source-language", help="Source language code (e.g. en)")
    p.add_argument("--target-language", help="Target language code (e.g. zh)")
    p.add_argument("--chunk-size", type=int, help="Captions per translation batch")
    p.add_argument("--context-window", type=int, help="Context-only captions before/after each batch")
    p.add_argument(
        "--max-concurrent-chunks", type=int,
        help="Max chunks translated in parallel per file",
    )
    p.add_argument(
        "--no-resume", action="store_true",
        help="Ignore any existing progress file and retranslate from scratch",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vtt-translator", description="VTT subtitle translator")
    sub = parser.add_subparsers(dest="command", required=True)

    t = sub.add_parser("translate", help="Translate a single VTT file")
    t.add_argument("input", help="Input VTT file")
    t.add_argument("output", help="Output VTT file")
    _add_common_config_args(t)

    b = sub.add_parser("batch", help="Translate all VTT files in a directory")
    b.add_argument("--start", type=int, default=0, help="Start index (0-based, default 0)")
    b.add_argument("--end", type=int, help="End index (exclusive); default: all")
    b.add_argument("--input-dir", help="Override input directory")
    b.add_argument("--output-dir", help="Override output directory")
    b.add_argument("--done-dir", help="Override done directory")
    _add_common_config_args(b)

    c = sub.add_parser("config", help="Generate a default config file")
    c.add_argument("output", help="Path to write the generated config JSON")

    e = sub.add_parser("estimate", help="Dry-run: parse & chunk a file without calling the LLM")
    e.add_argument("input", help="Input VTT file")
    _add_common_config_args(e)

    return parser


def _load_config_from_args(args: argparse.Namespace) -> Config:
    """Load config from file (if any) and apply CLI overrides."""
    cfg = Config.load(getattr(args, "config", None))

    overrides = {
        "model_id": getattr(args, "model", None),
        "provider": getattr(args, "provider", None),
        "source_language": getattr(args, "source_language", None),
        "target_language": getattr(args, "target_language", None),
        "chunk_size": getattr(args, "chunk_size", None),
        "context_window": getattr(args, "context_window", None),
        "max_concurrent_chunks": getattr(args, "max_concurrent_chunks", None),
        "input_dir": getattr(args, "input_dir", None),
        "output_dir": getattr(args, "output_dir", None),
        "done_dir": getattr(args, "done_dir", None),
    }
    clean = {k: v for k, v in overrides.items() if v is not None}
    if clean:
        cfg = cfg.model_copy(update=clean)
    return cfg


def _cmd_translate(args: argparse.Namespace) -> int:
    cfg = _load_config_from_args(args)
    logger = setup_logger(
        cfg.log_dir,
        level=logging.DEBUG if args.verbose else logging.INFO,
    )
    translator = VttTranslator(cfg, logger)
    resume = False if args.no_resume else None
    ok = translator.translate_vtt(args.input, args.output, resume=resume)
    if ok:
        print(f"Translated -> {args.output}")
        return 0
    print("Translation failed (see logs).", file=sys.stderr)
    return 1


def _cmd_batch(args: argparse.Namespace) -> int:
    cfg = _load_config_from_args(args)
    resume = False if args.no_resume else None
    manager = VttTranslatorManager(cfg, resume=resume)
    if args.verbose:
        manager.logger.setLevel(logging.DEBUG)
    success, total = manager.batch_process(args.start, args.end)
    print(f"Batch: {success}/{total} succeeded")
    return 0 if success == total else 1


def _cmd_config(args: argparse.Namespace) -> int:
    Config().save(args.output)
    print(f"Wrote default config -> {args.output}")
    return 0


def _cmd_estimate(args: argparse.Namespace) -> int:
    cfg = _load_config_from_args(args)
    captions = parse_vtt(args.input)
    chunks = split_into_chunks(
        captions,
        chunk_size=cfg.chunk_size,
        context_window=cfg.context_window,
    )
    total_chars = sum(len(c.text) for c in captions)
    print(f"File:            {Path(args.input).name}")
    print(f"Captions:        {len(captions)}")
    print(f"Total characters:{total_chars}")
    print(f"Chunk size:      {cfg.chunk_size}")
    print(f"Context window:  {cfg.context_window}")
    print(f"Chunks:          {len(chunks)} (= number of LLM calls, before fallbacks)")
    print(f"Concurrency:     {cfg.max_concurrent_chunks} chunk(s) in parallel")
    print(f"Resume enabled:  {cfg.enable_resume}")
    print(f"Model:           {cfg.provider}/{cfg.model_id}")
    print(f"Source -> Target:{cfg.source_language} -> {cfg.target_language}")
    return 0


_COMMANDS = {
    "translate": _cmd_translate,
    "batch": _cmd_batch,
    "config": _cmd_config,
    "estimate": _cmd_estimate,
}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return _COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
