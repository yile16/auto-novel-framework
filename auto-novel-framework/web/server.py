"""FastAPI web server for the Auto-Novel Framework decomposition pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from config import Config, DecomposeConfig
from utils.text import split_by_chapter
from utils.io import read_novel
from core.decomposer.extractor import ChapterExtractor
from core.decomposer.merger import ArcMerger
from core.decomposer.finalizer import BookFinalizer
from utils.markdown_writer import decomposition_to_markdown

logger = logging.getLogger(__name__)

app = FastAPI(title="Auto-Novel Framework")

STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_BASE = Path("output")

# Global task registry
_tasks: dict[str, dict] = {}
_ws_clients: dict[str, list[WebSocket]] = {}


def _notify(task_id: str, event: dict):
    """Send event to all WebSocket clients listening to this task."""
    if task_id in _ws_clients:
        dead = []
        for ws in _ws_clients[task_id]:
            try:
                asyncio.run_coroutine_threadsafe(ws.send_json(event), asyncio.get_event_loop())
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients[task_id].remove(ws)


@app.post("/api/upload")
async def upload_novel(file: UploadFile = File(...)):
    """Upload a novel file, return text and metadata."""
    content = await file.read()
    # Save to temp
    tmp_path = Path("/tmp/novel_upload") / file.filename
    tmp_path.parent.mkdir(exist_ok=True)
    tmp_path.write_bytes(content)

    try:
        novel = read_novel(tmp_path)
        return {
            "ok": True,
            "title": novel.title,
            "author": novel.author,
            "text_length": len(novel.text),
            "text": novel.text,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/run")
async def run_decompose(
    text: str = Form(...),
    title: str = Form(""),
    api_key: str = Form(""),
    base_url: str = Form("https://api.deepseek.com"),
    model: str = Form("deepseek-chat"),
    chapters_per_chunk: int = Form(20),
    parallel: int = Form(3),
):
    """Start a decomposition task, returns task_id for WebSocket connection."""
    import uuid
    task_id = str(uuid.uuid4())[:8]

    _tasks[task_id] = {
        "id": task_id,
        "status": "starting",
        "progress": 0,
        "message": "初始化中...",
        "results": None,
        "report": None,
        "error": None,
        "cancel": False,
        "pause": False,
    }

    def run_pipeline():
        task = _tasks[task_id]
        try:
            task["status"] = "parsing"
            _notify(task_id, {"type": "status", "message": "解析文本...", "progress": 5})

            # Config
            config = Config()
            config.decompose = DecomposeConfig(
                model=model,
                max_chunk_tokens=8000,
                chapters_per_arc=chapters_per_chunk,
                max_parallel_extractions=parallel,
                base_url=base_url,
                api_key=api_key,
                output_dir=OUTPUT_BASE / task_id,
            )

            output_dir = OUTPUT_BASE / task_id
            output_dir.mkdir(parents=True, exist_ok=True)

            # Parse chapters
            _notify(task_id, {"type": "status", "message": "分割章节...", "progress": 10})

            chunks = split_by_chapter(
                text,
                max_tokens=config.decompose.max_chunk_tokens,
                overlap_tokens=config.decompose.chunk_overlap_tokens,
            )
            total_chunks = len(chunks)
            _notify(task_id, {"type": "status", "message": f"共 {total_chunks} 个分块", "progress": 15})

            # Extract in batches with context relay
            extractor = ChapterExtractor(config.decompose)
            merger = ArcMerger(config.decompose)
            finalizer = BookFinalizer(config.decompose)

            arc_size = config.decompose.chapters_per_arc
            chunk_batches = [chunks[i : i + arc_size] for i in range(0, len(chunks), arc_size)]

            all_extractions = []
            previous_context = ""

            for batch_idx, batch_chunks in enumerate(chunk_batches):
                if task["cancel"]:
                    task["status"] = "stopped"
                    _notify(task_id, {"type": "stopped"})
                    return

                while task["pause"]:
                    task["status"] = "paused"
                    _notify(task_id, {"type": "paused"})
                    time.sleep(1)
                    if task["cancel"]:
                        return

                task["status"] = "extracting"
                pct = 15 + int((batch_idx + 1) / len(chunk_batches) * 40)
                _notify(task_id, {
                    "type": "status",
                    "message": f"提取 {batch_idx + 1}/{len(chunk_batches)} 批次 ({batch_chunks[0].chapter_start}-{batch_chunks[-1].chapter_start}章)...",
                    "progress": pct,
                    "chunk_current": batch_idx + 1,
                    "chunk_total": len(chunk_batches),
                })

                extractions = extractor.extract_batch(batch_chunks, previous_context=previous_context)
                all_extractions.extend(extractions)
                previous_context = extractor.build_context_summary(extractions)

            # Save raw extractions
            raw_path = output_dir / "raw_extractions.json"
            raw_path.write_text(
                json.dumps(
                    [e.model_dump(exclude_none=True) for e in all_extractions],
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )

            # Merge into arcs
            if task["cancel"]:
                return

            task["status"] = "merging"
            _notify(task_id, {"type": "status", "message": "合并弧段状态...", "progress": 60})

            batch_extractions = [
                all_extractions[i : i + arc_size] for i in range(0, len(all_extractions), arc_size)
            ]
            arc_states = merger.merge_all_arcs_sequentially(batch_extractions)

            arc_path = output_dir / "arc_states.json"
            arc_path.write_text(json.dumps(arc_states, ensure_ascii=False, indent=2), encoding="utf-8")

            # Finalize
            if task["cancel"]:
                return

            task["status"] = "finalizing"
            _notify(task_id, {"type": "status", "message": "生成全书拆解文档...", "progress": 80})

            result = finalizer.finalize(
                arc_states,
                title=title,
                total_chapters=len(all_extractions),
            )

            # Save outputs
            data = result.model_dump(exclude_none=True)
            yaml_path = output_dir / "decomposition.yaml"
            yaml_path.write_text(
                __import__("yaml").dump(data, allow_unicode=True, sort_keys=False, width=200),
                encoding="utf-8",
            )
            json_path = output_dir / "decomposition.json"
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            md_path = decomposition_to_markdown(json_path, output_dir / "decomposition.md")

            # Read back results for frontend
            report = md_path.read_text(encoding="utf-8")

            task["status"] = "completed"
            task["progress"] = 100
            task["report"] = report
            task["results"] = data

            _notify(task_id, {
                "type": "completed",
                "message": "拆解完成！",
                "progress": 100,
                "report": report,
            })

        except Exception as e:
            traceback.print_exc()
            task["status"] = "error"
            task["error"] = str(e)
            _notify(task_id, {"type": "error", "message": str(e)})

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    return {"ok": True, "task_id": task_id}


@app.post("/api/pause/{task_id}")
async def pause_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    task["pause"] = not task.get("pause", False)
    return {"ok": True, "paused": task["pause"]}


@app.post("/api/stop/{task_id}")
async def stop_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    task["cancel"] = True
    return {"ok": True}


@app.get("/api/status/{task_id}")
async def task_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    return {
        "ok": True,
        "status": task["status"],
        "progress": task["progress"],
        "message": task["message"],
        "error": task["error"],
    }


@app.get("/api/report/{task_id}")
async def download_report(task_id: str):
    """Download the markdown report for a completed task."""
    task = _tasks.get(task_id)
    if not task or not task.get("report"):
        return {"ok": False, "error": "报告不存在"}
    return {"ok": True, "report": task["report"]}


@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    if task_id not in _ws_clients:
        _ws_clients[task_id] = []
    _ws_clients[task_id].append(websocket)
    try:
        # Send current state on connect
        task = _tasks.get(task_id)
        if task:
            await websocket.send_json({
                "type": "status",
                "message": task.get("message", ""),
                "progress": task.get("progress", 0),
                "status": task.get("status", "unknown"),
            })
            if task.get("report"):
                await websocket.send_json({
                    "type": "completed",
                    "report": task["report"],
                })
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        _ws_clients[task_id].remove(websocket)


@app.get("/")
async def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


def serve(host: str = "0.0.0.0", port: int = 8765):
    """Launch the web server."""
    uvicorn.run(app, host=host, port=port, log_level="info")
