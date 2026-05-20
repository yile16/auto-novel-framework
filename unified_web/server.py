"""
统一 Web Server — 整合小说拆解管线 + 角色 IP 管线
单端口 8765，WebSocket 实时进度推送

工作流：
  上传小说 → 全并发拆解 → 角色列表 → 选择角色 → 7 Agent IP 管线 → 下载全部产物
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Add parent paths for imports (order matters — each thread reorders as needed)
_BASE = Path(__file__).parent.parent
_AUTO_NOVEL_PATH = str(_BASE / "auto-novel-framework")
_CHAR_IP_PATH = str(_BASE / "character-ip-pipeline")
sys.path.insert(0, _AUTO_NOVEL_PATH)
sys.path.insert(0, _CHAR_IP_PATH)

logger = logging.getLogger(__name__)

app = FastAPI(title="Auto-Novel → Character IP 统一平台")

STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_BASE = Path("output")

# ── Global task registry ──
_tasks: dict[str, dict] = {}
_ws_clients: dict[str, list[WebSocket]] = {}
_main_loop: asyncio.AbstractEventLoop | None = None

def _notify(task_id: str, event: dict):
    """Send event to all WebSocket clients listening to this task."""
    if task_id in _ws_clients:
        dead = []
        for ws in _ws_clients[task_id]:
            try:
                asyncio.run_coroutine_threadsafe(ws.send_json(event), _main_loop)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients[task_id].remove(ws)

# ═══════════════════════════════════════════
# 小说拆解 API（来自 auto-novel-framework）
# ═══════════════════════════════════════════

class DecomposeRequest(BaseModel):
    text: str
    title: str = ""
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    parallel: int = 15


class CharacterIPRequest(BaseModel):
    character_name: str
    source: str = ""
    style: str = "auto"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    stages: str = "research,angle,lyrics,voice,song,visual,video"
    prefill_profile: str = ""  # JSON string from decompose output


@app.post("/api/upload")
async def upload_novel(file: UploadFile = File(...)):
    """上传小说文件，返回文本和元数据。"""
    content = await file.read()
    # Decode and parse the uploaded text file
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except Exception:
            return {"ok": False, "error": "无法解码文件，请使用 UTF-8 或 GBK 编码"}

    # Extract title/author from first lines
    title = file.filename.rsplit(".", 1)[0] if file.filename else "未命名"
    author = ""
    lines = text.strip().split("\n")
    for line in lines[:5]:
        line_s = line.strip()
        if line_s.startswith("书名") or line_s.startswith("《"):
            title = line_s.replace("书名：", "").replace("书名:", "").strip()
        if line_s.startswith("作者"):
            author = line_s.replace("作者：", "").replace("作者:", "").strip()

    return {
        "ok": True,
        "title": title,
        "author": author,
        "text_length": len(text),
        "text": text,
    }


@app.post("/api/decompose/start")
async def start_decompose(req: DecomposeRequest):
    """启动小说拆解任务。"""
    global _main_loop
    _main_loop = asyncio.get_event_loop()

    text = req.text
    title = req.title
    api_key = req.api_key
    base_url = req.base_url
    model = req.model
    parallel = req.parallel

    task_id = str(uuid.uuid4())[:8]

    _tasks[task_id] = {
        "id": task_id,
        "type": "decompose",
        "status": "starting",
        "progress": 0,
        "message": "初始化中...",
        "characters": None,
        "report": None,
        "output_dir": None,
        "error": None,
        "cancel": False,
    }

    def run_decompose():
        task = _tasks[task_id]
        # Ensure auto-novel-framework is searched first for imports,
        # and clear any cached modules that might have been loaded from the other package
        if _AUTO_NOVEL_PATH in sys.path:
            sys.path.remove(_AUTO_NOVEL_PATH)
        sys.path.insert(0, _AUTO_NOVEL_PATH)
        # Clear cached modules that conflict between the two packages
        for mod_name in list(sys.modules.keys()):
            if mod_name in ('config', 'utils', 'models', 'llm') or mod_name.startswith(('config.', 'utils.', 'models.', 'llm.')):
                del sys.modules[mod_name]
        try:
            from config import Config, DecomposeConfig
            from utils.text import split_by_chapter
            from core.decomposer.extractor import ChapterExtractor
            from core.decomposer.programmatic_merger import ProgrammaticMerger
            from utils.markdown_writer_v3 import write_all

            task["status"] = "parsing"
            task["message"] = "解析文本，分割章节..."
            task["progress"] = 5
            _notify(task_id, {"type": "status", "stage": "parse", "message": task["message"], "progress": 5})

            config = DecomposeConfig(
                model=model,
                max_chunk_tokens=8000,
                max_concurrent_extractions=parallel,
                base_url=base_url,
                api_key=api_key,
                output_dir=OUTPUT_BASE / task_id,
            )

            output_dir = OUTPUT_BASE / task_id
            output_dir.mkdir(parents=True, exist_ok=True)
            task["output_dir"] = str(output_dir)

            task["message"] = "分割章节..."
            task["progress"] = 10
            _notify(task_id, {"type": "status", "stage": "split", "message": task["message"], "progress": 10})

            chunks = split_by_chapter(
                text,
                max_tokens=config.max_chunk_tokens,
                overlap_tokens=config.chunk_overlap_tokens,
            )
            total = len(chunks)
            task["message"] = f"共 {total} 个章节"
            task["progress"] = 15
            _notify(task_id, {"type": "status", "stage": "split", "message": task["message"], "progress": 15})

            extractor = ChapterExtractor(config)
            merger = ProgrammaticMerger()

            def progress_cb(done, _total):
                if task["cancel"]:
                    return
                if _total == 0:
                    return
                pct = 15 + int(done / _total * 60)
                task["status"] = "extracting"
                task["message"] = f"LLM 提取中 {done}/{_total} 章..."
                task["progress"] = pct
                _notify(task_id, {
                    "type": "status", "stage": "extract",
                    "message": task["message"],
                    "progress": pct,
                    "chunk_current": done,
                    "chunk_total": _total,
                })

            task["message"] = f"全并发提取 {total} 章（{parallel} 线程）..."
            task["progress"] = 15
            _notify(task_id, {"type": "status", "stage": "extract", "message": task["message"], "progress": 15})

            extractions = extractor.extract_all(
                chunks,
                max_workers=config.max_concurrent_extractions,
                progress_callback=progress_cb,
            )

            if task["cancel"]:
                task["status"] = "cancelled"
                _notify(task_id, {"type": "cancelled", "message": "任务已取消"})
                return

            raw_path = output_dir / "raw_extractions.json"
            raw_path.write_text(
                json.dumps([e.model_dump(exclude_none=True) for e in extractions], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            task["status"] = "merging"
            task["message"] = "程序化合并中..."
            task["progress"] = 80
            _notify(task_id, {"type": "status", "stage": "merge", "message": task["message"], "progress": 80})

            raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
            result = merger.merge(raw_data, title=title, author="")

            # Save outputs
            data = result.model_dump(exclude_none=True)
            json_path = output_dir / "decomposition.json"
            json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            md_paths = write_all(result, output_dir, raw_extractions=raw_data)

            # Extract character names for downstream pipeline
            char_list = []
            for c in result.characters:
                if c.role in ("主角", "反派", "配角"):
                    char_list.append({
                        "name": c.name,
                        "role": c.role,
                        "aliases": c.aliases,
                        "intro_chapter": c.introduction_chapter or 0,
                        "personality": c.static_traits.personality if c.static_traits else "",
                        "appearance": c.static_traits.appearance if c.static_traits else "",
                        "background": c.identity.background if c.identity else "",
                    })

            task["characters"] = sorted(char_list, key=lambda c: {"主角": 0, "反派": 1, "配角": 2}.get(c["role"], 9))

            report = (output_dir / "index.md").read_text(encoding="utf-8")
            task["report"] = report
            task["status"] = "completed"
            task["progress"] = 100
            task["message"] = f"拆解完成！识别 {len(char_list)} 个角色，生成 {len(md_paths)} 个专题文件"

            _notify(task_id, {
                "type": "completed",
                "message": task["message"],
                "progress": 100,
                "characters": task["characters"],
                "report": report,
            })

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Decompose task {task_id} failed:\n{tb}")
            task["status"] = "error"
            task["error"] = f"{type(e).__name__}: {e}"
            _notify(task_id, {"type": "error", "message": str(e)})

    thread = threading.Thread(target=run_decompose, daemon=True)
    thread.start()

    return {"ok": True, "task_id": task_id}


@app.post("/api/decompose/cancel/{task_id}")
async def cancel_decompose(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    task["cancel"] = True
    return {"ok": True}


@app.get("/api/decompose/status/{task_id}")
async def decompose_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    return {
        "ok": True,
        "status": task["status"],
        "progress": task["progress"],
        "message": task.get("message", ""),
        "error": task.get("error"),
        "characters": task.get("characters"),
        "report": task.get("report"),
        "output_dir": task.get("output_dir"),
    }


@app.get("/api/decompose/download/{task_id}/{file_name}")
async def download_decompose_file(task_id: str, file_name: str):
    """Download a specific output file from the decomposition."""
    task = _tasks.get(task_id)
    if not task or not task.get("output_dir"):
        return {"ok": False, "error": "文件不存在"}
    file_path = Path(task["output_dir"]) / file_name
    if not file_path.exists():
        return {"ok": False, "error": f"文件 {file_name} 不存在"}
    return FileResponse(file_path, filename=file_name)


# ═══════════════════════════════════════════
# 角色信息搜索（DuckDuckGo，免费无需 Key）
# ═══════════════════════════════════════════

@app.get("/api/character/search")
async def search_character(name: str = Query(...)):
    """搜索角色信息，使用 DuckDuckGo 免费搜索，返回摘要文本。"""
    try:
        # Try the newer ddgs package first, fall back to duckduckgo_search
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = []
        queries = [
            f"{name} 角色 人物 性格",
            f"{name} 原著 故事 背景",
        ]

        with DDGS() as ddgs:
            for query in queries:
                try:
                    for r in ddgs.text(query, max_results=5, region="cn-zh"):
                        body = (r.get("body") or "").strip()
                        title = (r.get("title") or "").strip()
                        if body and len(body) > 30:
                            results.append({
                                "title": title,
                                "snippet": body[:500],
                                "url": r.get("href", ""),
                            })
                except Exception:
                    pass

        if not results:
            return {"ok": True, "results": [], "summary": f"未搜索到「{name}」的详细资料。\n\n建议：输入更多角色信息帮助 AI 理解，如\"孙悟空，出自《西游记》，齐天大圣，性格桀骜不驯但重情重义...\""}

        # Build a combined text from search snippets
        text_parts = [f"以下是通过网络自动搜集的「{name}」相关信息（{len(results)} 条），可直接用于角色 IP 生成：", ""]
        for i, r in enumerate(results[:8]):
            text_parts.append(f"{i+1}. [{r['title']}]\n   {r['snippet']}")

        combined = "\n\n".join(text_parts)
        return {"ok": True, "results": results, "summary": combined}

    except ImportError:
        return {"ok": False, "error": "搜索模块未安装，请运行: pip install ddgs"}
    except Exception as e:
        return {"ok": False, "error": f"搜索失败: {str(e)}"}


# ═══════════════════════════════════════════
# 角色 IP 管线 API（来自 character-ip-pipeline）
# ═══════════════════════════════════════════

@app.post("/api/character-ip/run")
async def run_character_ip(req: CharacterIPRequest):
    """启动角色 IP 管线。"""
    global _main_loop
    _main_loop = asyncio.get_event_loop()

    character_name = req.character_name
    source = req.source
    style = req.style
    api_key = req.api_key
    base_url = req.base_url
    model = req.model
    stages = req.stages
    prefill_profile = req.prefill_profile

    task_id = str(uuid.uuid4())[:8]
    stage_list = [s.strip() for s in stages.split(",") if s.strip()]

    _tasks[task_id] = {
        "id": task_id,
        "type": "character_ip",
        "character_name": character_name,
        "status": "running",
        "progress": 0,
        "message": "初始化角色 IP 管线...",
        "stage_current": "",
        "stage_label": "",
        "stage_results": {},
        "error": None,
    }

    def run_pipeline():
        task = _tasks[task_id]
        # Ensure character-ip-pipeline is searched first for imports,
        # and clear any cached modules that might have been loaded from the other package
        if _CHAR_IP_PATH in sys.path:
            sys.path.remove(_CHAR_IP_PATH)
        sys.path.insert(0, _CHAR_IP_PATH)
        # Clear cached modules that conflict between the two packages
        for mod_name in list(sys.modules.keys()):
            if mod_name in ('config', 'utils', 'models', 'llm') or mod_name.startswith(('config.', 'utils.', 'models.', 'llm.')):
                del sys.modules[mod_name]
        try:
            from config import PipelineConfig
            from orchestrator import Orchestrator
            from models.project import AgentStatus

            config = PipelineConfig(
                model=model,
                api_key=api_key,
                base_url=base_url,
                output_dir=Path("projects"),
                quality_threshold=0.7,
                max_retries=2,
            )

            orch = Orchestrator(config)

            total_stages = len(stage_list)
            completed_count = [0]

            def on_stage_start(stage: str, label: str):
                task["stage_current"] = stage
                task["stage_label"] = label
                task["message"] = f"正在执行: {label}..."
                _notify(task_id, {
                    "type": "status",
                    "stage": stage,
                    "stage_label": label,
                    "message": task["message"],
                    "progress": int(completed_count[0] / total_stages * 100),
                })

            def on_stage_complete(stage: str, result):
                completed_count[0] += 1
                task["stage_results"][stage] = {
                    "status": "done",
                    "score": result.quality_score if hasattr(result, 'quality_score') else 0,
                    "retries": result.retry_count if hasattr(result, 'retry_count') else 0,
                }
                task["message"] = f"✅ {stage} 完成 ({task['stage_results'][stage]['score']:.0%})"
                task["progress"] = int(completed_count[0] / total_stages * 100)
                _notify(task_id, {
                    "type": "stage_complete",
                    "stage": stage,
                    "score": result.quality_score if hasattr(result, 'quality_score') else 0,
                    "message": task["message"],
                    "progress": task["progress"],
                })

            def on_error(stage: str, error: str):
                task["stage_results"][stage] = {"status": "failed", "error": error}
                task["message"] = f"❌ {stage}: {error[:60]}"
                _notify(task_id, {
                    "type": "stage_error",
                    "stage": stage,
                    "message": task["message"],
                })

            orch.on_stage_start(on_stage_start)
            orch.on_stage_complete(on_stage_complete)
            orch.on_error(on_error)

            # Parse prefill data if provided
            prefill = None
            if prefill_profile:
                try:
                    prefill = json.loads(prefill_profile)
                except json.JSONDecodeError:
                    pass

            _notify(task_id, {"type": "status", "stage": "init", "message": f"开始角色 IP 管线: {character_name}", "progress": 0})

            project = orch.run(
                character_name=character_name,
                source=source,
                style=style,
                stages=stage_list,
                prefill_profile=prefill,
            )

            # Collect all outputs
            outputs = {}
            if project.character_profile:
                outputs["research"] = project.character_profile.model_dump()
            if project.song_brief:
                outputs["angle"] = project.song_brief.model_dump()
            if project.lyrics:
                outputs["lyrics"] = project.lyrics.model_dump()
                outputs["lyrics_md"] = _lyrics_to_markdown(project)
            if project.voice_design:
                outputs["voice"] = project.voice_design.model_dump()
            if project.song_production:
                outputs["song"] = project.song_production.model_dump()
            if project.visual_design:
                outputs["visual"] = project.visual_design.model_dump()
            if project.storyboard:
                outputs["video"] = project.storyboard.model_dump()

            task["outputs"] = outputs
            task["status"] = "completed"
            task["progress"] = 100
            task["message"] = "角色 IP 管线全部完成！"

            _notify(task_id, {
                "type": "completed",
                "message": f"🎉 {character_name} IP 内容生成完成！",
                "progress": 100,
                "outputs": outputs,
            })

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"IP pipeline task {task_id} failed:\n{tb}")
            task["status"] = "error"
            task["error"] = f"{type(e).__name__}: {e}"
            _notify(task_id, {"type": "error", "message": str(e)})

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()

    return {"ok": True, "task_id": task_id}


def _lyrics_to_markdown(project) -> str:
    """Convert lyrics to markdown format."""
    if not project.lyrics:
        return ""
    lines = [f"# {project.lyrics.title}", "", f"**角色**: {project.lyrics.character_name}",
             f"**选题**: {project.lyrics.angle}", f"**语言风格**: {project.lyrics.language_style}",
             f"**韵脚方案**: {project.lyrics.rhyme_scheme}", "", "## 歌词", ""]
    for section in project.lyrics.sections:
        lines.append(f"### [{section.section_type}] — {section.emotion}")
        for line in section.lines:
            lines.append(line)
        lines.append("")
    return "\n".join(lines)


@app.get("/api/character-ip/status/{task_id}")
async def character_ip_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    return {
        "ok": True,
        "status": task["status"],
        "progress": task["progress"],
        "message": task.get("message", ""),
        "stage_current": task.get("stage_current", ""),
        "stage_label": task.get("stage_label", ""),
        "stage_results": task.get("stage_results", {}),
        "outputs": task.get("outputs"),
        "error": task.get("error"),
    }


@app.get("/api/character-ip/output/{task_id}/{stage}")
async def character_ip_output(task_id: str, stage: str):
    task = _tasks.get(task_id)
    if not task:
        return {"ok": False, "error": "任务不存在"}
    outputs = task.get("outputs", {})
    if stage not in outputs:
        return {"ok": False, "error": f"阶段 {stage} 未完成"}
    return {"ok": True, "data": outputs[stage]}


# ═══════════════════════════════════════════
# WebSocket — 统一实时推送
# ═══════════════════════════════════════════

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
                "stage": task.get("stage_current", ""),
                "stage_label": task.get("stage_label", ""),
                "characters": task.get("characters"),
                "report": task.get("report"),
                "outputs": task.get("outputs"),
            })

        while True:
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        if task_id in _ws_clients and websocket in _ws_clients[task_id]:
            _ws_clients[task_id].remove(websocket)


# ═══════════════════════════════════════════
# 前端页面
# ═══════════════════════════════════════════

@app.get("/")
async def index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Loading...</h1>")


def serve(host: str = "0.0.0.0", port: int = 8765):
    """启动统一 Web Server。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info(f"🚀 统一平台启动: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()
