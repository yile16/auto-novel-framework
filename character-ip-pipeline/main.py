#!/usr/bin/env python3
"""Character IP Pipeline — CLI entry point.

Usage:
  python main.py run 孙悟空                    # Full pipeline
  python main.py run 孙悟空 --stages research,angle,lyrics  # Specific stages
  python main.py web                           # Launch web UI
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from config import PipelineConfig
from orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def cmd_run(args):
    """Run the pipeline from CLI."""
    stages = None
    if args.stages:
        stages = [s.strip() for s in args.stages.split(",")]

    config = PipelineConfig(
        model=args.model,
        api_key=args.api_key or "",
        base_url=args.base_url,
        output_dir=Path(args.output),
        quality_threshold=args.quality,
        max_retries=args.max_retries,
    )

    orch = Orchestrator(config)
    project = orch.run(
        character_name=args.character,
        source=args.source,
        style=args.style,
        stages=stages,
    )

    print(f"\n✅ 项目完成: {args.character}")
    print(f"📂 输出目录: {config.output_dir / args.character}")
    return 0


def cmd_web(args):
    """Launch the web UI."""
    import uvicorn

    # Add the parent directory to path so the web server can import
    sys.path.insert(0, str(Path(__file__).parent))

    logger.info(f"🚀 启动 Web 界面: http://localhost:{args.port}")
    uvicorn.run(
        "web.server:app",
        host=args.host,
        port=args.port,
        reload=args.dev,
    )
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Character IP Pipeline — 角色IP全链路内容产线",
    )
    sub = parser.add_subparsers(dest="command")

    # Run command
    run_parser = sub.add_parser("run", help="运行角色IP管线")
    run_parser.add_argument("character", help="角色名称")
    run_parser.add_argument("--source", default="", help="来源 (如 '西游记原著')")
    run_parser.add_argument("--style", default="auto", help="视觉风格")
    run_parser.add_argument("--stages", default=None, help="执行的阶段 (逗号分隔)")
    run_parser.add_argument("--model", default="deepseek-chat", help="LLM 模型")
    run_parser.add_argument("--api-key", default="", help="API Key")
    run_parser.add_argument("--base-url", default="https://api.deepseek.com", help="API Base URL")
    run_parser.add_argument("--output", default="projects", help="输出目录")
    run_parser.add_argument("--quality", type=float, default=0.7, help="质量阈值")
    run_parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")
    run_parser.set_defaults(func=cmd_run)

    # Web command
    web_parser = sub.add_parser("web", help="启动 Web 界面")
    web_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    web_parser.add_argument("--port", type=int, default=8760, help="监听端口")
    web_parser.add_argument("--dev", action="store_true", help="开发模式 (热重载)")
    web_parser.set_defaults(func=cmd_web)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
