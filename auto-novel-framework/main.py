#!/usr/bin/env python3
"""Auto-Novel Framework CLI — decompose novels into reusable structured components."""

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from config import Config, DecomposeConfig
from pipelines.decompose_pipeline import DecomposePipeline


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=Console(stderr=True))],
    )


def cmd_decompose(args: argparse.Namespace):
    """Run the decompose pipeline."""
    config = Config()
    config.decompose = DecomposeConfig(
        model=args.model,
        max_chunk_tokens=args.max_chunk_tokens,
        chapters_per_arc=args.chapters_per_arc,
        max_parallel_extractions=args.parallel,
        output_dir=Path(args.output),
    )
    if args.api_key:
        config.decompose.api_key = args.api_key

    pipeline = DecomposePipeline(config.decompose)
    result = pipeline.run(args.file, output_dir=args.output)

    console = Console()
    console.print(f"\n[bold green]Decomposition complete![/]")
    console.print(f"  Title: {result.title}")
    console.print(f"  Characters extracted: {len(result.characters)}")
    console.print(f"  Chapter events: {len(result.plot.chapter_events)}")
    console.print(f"  Plot threads: {len(result.plot.threads)}")
    console.print(f"  Locations: {len(result.world_setting.locations)}")
    console.print(f"  Output: {args.output}/")


def main():
    parser = argparse.ArgumentParser(
        description="Auto-Novel Framework — decompose and generate novels",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # decompose command
    dec_parser = subparsers.add_parser(
        "decompose",
        help="Decompose a novel into structured components",
    )
    dec_parser.add_argument(
        "file",
        help="Path to the novel file (.txt or .epub)",
    )
    dec_parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory (default: output)",
    )
    dec_parser.add_argument(
        "--model", "-m",
        default="claude-sonnet-4-6",
        help="Claude model to use (default: claude-sonnet-4-6)",
    )
    dec_parser.add_argument(
        "--max-chunk-tokens",
        type=int,
        default=8000,
        help="Max tokens per chunk (default: 8000)",
    )
    dec_parser.add_argument(
        "--chapters-per-arc",
        type=int,
        default=15,
        help="Chapters per merge arc (default: 15)",
    )
    dec_parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=5,
        help="Max parallel LLM calls (default: 5)",
    )
    dec_parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    dec_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )
    dec_parser.set_defaults(func=cmd_decompose)

    # web command
    web_parser = subparsers.add_parser(
        "web",
        help="Launch the interactive web UI",
    )
    web_parser.add_argument(
        "--host", default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    web_parser.add_argument(
        "--port", "-p", type=int, default=8765,
        help="Port to bind (default: 8765)",
    )
    web_parser.set_defaults(func=cmd_web)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "web":
        setup_logging(True)
    else:
        setup_logging(args.verbose)
    args.func(args)


def cmd_web(args):
    """Launch the interactive web interface."""
    from web.server import serve
    console = Console()
    console.print(f"\n[bold]Auto-Novel Framework Web UI[/]")
    console.print(f"  Local:   [cyan]http://localhost:{args.port}[/]")
    console.print(f"  Network: [cyan]http://0.0.0.0:{args.port}[/]")
    console.print(f"\n  Press [bold]Ctrl+C[/] to stop\n")
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
