"""FastAPI web server for the Character IP Pipeline."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from config import PipelineConfig
from orchestrator import Orchestrator
from models.project import Project, AgentResult, AgentStatus


app = FastAPI(title="Character IP Pipeline")

# Global state
orchestrator: Optional[Orchestrator] = None
active_tasks: dict[str, dict] = {}
projects: dict[str, Project] = {}

# ── Models ──

class RunRequest(BaseModel):
    character_name: str
    source: str = ""
    style: str = "auto"
    stages: list[str] = ["research", "angle", "lyrics", "voice", "song", "visual", "video"]
    model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"

class TaskStatus(BaseModel):
    task_id: str
    character_name: str
    stage: str
    stage_label: str
    status: str  # running / done / failed
    progress: float  # 0-1
    message: str


# ── Routes ──

@app.get("/")
async def index():
    static_dir = Path(__file__).parent / "static"
    return HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))


@app.post("/api/run")
async def run_pipeline(req: RunRequest):
    """Start the pipeline for a character."""
    global orchestrator, active_tasks

    config = PipelineConfig(
        model=req.model,
        api_key=req.api_key,
        base_url=req.base_url,
        output_dir=Path("projects"),
    )

    orchestrator = Orchestrator(config)
    task_id = f"{req.character_name}_{datetime.now().strftime('%H%M%S')}"

    active_tasks[task_id] = {
        "character_name": req.character_name,
        "stage": "initializing",
        "stage_label": "初始化",
        "status": "running",
        "progress": 0.0,
        "message": "正在启动...",
    }

    # Set up callbacks
    total_stages = len(req.stages)
    completed = [0]

    def on_stage_start(stage: str, label: str):
        active_tasks[task_id].update({
            "stage": stage,
            "stage_label": label,
            "message": f"正在执行: {label}...",
        })

    def on_stage_complete(stage: str, result: AgentResult):
        completed[0] += 1
        active_tasks[task_id].update({
            "progress": completed[0] / total_stages,
            "message": f"✅ {stage} 完成 (得分: {result.quality_score:.2f})",
        })

    def on_error(stage: str, error: str):
        active_tasks[task_id].update({
            "status": "failed",
            "message": f"❌ {stage} 失败: {error}",
        })

    orchestrator.on_stage_start(on_stage_start)
    orchestrator.on_stage_complete(on_stage_complete)
    orchestrator.on_error(on_error)

    def run_thread():
        try:
            project = orchestrator.run(
                req.character_name,
                source=req.source,
                style=req.style,
                stages=req.stages,
            )
            projects[task_id] = project
            active_tasks[task_id].update({
                "status": "done",
                "progress": 1.0,
                "message": "全部完成！",
            })
        except Exception as e:
            active_tasks[task_id].update({
                "status": "failed",
                "message": str(e),
            })

    thread = threading.Thread(target=run_thread, daemon=True)
    thread.start()

    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """Get the status of a running task."""
    task = active_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@app.get("/api/project/{task_id}")
async def get_project(task_id: str):
    """Get the full project result."""
    project = projects.get(task_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Serialize project to dict
    return {
        "project_id": project.project_id,
        "character_name": project.character_name,
        "current_stage": project.current_stage,
        "agent_results": {
            name: r.model_dump() for name, r in project.agent_results.items()
        },
        "has_character_profile": project.character_profile is not None,
        "has_song_brief": project.song_brief is not None,
        "has_lyrics": project.lyrics is not None,
        "has_voice_design": project.voice_design is not None,
        "has_song_production": project.song_production is not None,
        "has_visual_design": project.visual_design is not None,
        "has_storyboard": project.storyboard is not None,
        "character_narrative_preview": (
            project.character_narrative[:500] if project.character_narrative else ""
        ),
    }


@app.get("/api/output/{task_id}/{stage}")
async def get_output(task_id: str, stage: str):
    """Get a specific agent's output."""
    project = projects.get(task_id)
    if not project:
        raise HTTPException(404, "Project not found")

    output = None
    if stage == "research" and project.character_profile:
        output = project.character_profile.model_dump()
    elif stage == "angle" and project.song_brief:
        output = project.song_brief.model_dump()
    elif stage == "lyrics" and project.lyrics:
        output = project.lyrics.model_dump()
    elif stage == "voice" and project.voice_design:
        output = project.voice_design.model_dump()
    elif stage == "song" and project.song_production:
        output = project.song_production.model_dump()
    elif stage == "visual" and project.visual_design:
        output = project.visual_design.model_dump()
    elif stage == "video" and project.storyboard:
        output = project.storyboard.model_dump()

    if output is None:
        raise HTTPException(404, f"No output for stage: {stage}")

    return output


@app.get("/api/output/{task_id}/{stage}/narrative")
async def get_narrative(task_id: str):
    """Get the character narrative."""
    project = projects.get(task_id)
    if not project or not project.character_narrative:
        raise HTTPException(404, "Narrative not found")
    return {"narrative": project.character_narrative}


@app.get("/api/output/{task_id}/{stage}/lyrics_md")
async def get_lyrics_md(task_id: str):
    """Get lyrics as markdown."""
    project = projects.get(task_id)
    if not project or not project.lyrics:
        raise HTTPException(404, "Lyrics not found")

    md_lines = [f"# {project.lyrics.title}", ""]
    for section in project.lyrics.sections:
        md_lines.append(f"### [{section.section_type}] — {section.emotion}")
        for line in section.lines:
            md_lines.append(line)
        md_lines.append("")
    return {"markdown": "\n".join(md_lines)}


# ── WebSocket for real-time updates ──

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            task = active_tasks.get(task_id, {})
            await websocket.send_json(task)
            if task.get("status") in ("done", "failed"):
                break
            await websocket.receive_text()  # Wait for client ping
    except WebSocketDisconnect:
        pass
