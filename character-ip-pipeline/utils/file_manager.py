"""Project file manager — creates and manages project directory structure."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


PROJECT_STAGES = [
    "00_research",
    "01_angle",
    "02_lyrics",
    "03_voice",
    "04_song",
    "05_visual",
    "06_video",
]


class ProjectFileManager:
    """Manages the file structure for a character IP project."""

    def __init__(self, base_dir: Path, character_name: str):
        self.character_name = character_name
        # Sanitize character name for filesystem
        safe_name = character_name.replace("/", "_").replace(" ", "_")
        self.project_dir = Path(base_dir) / safe_name

    def setup(self) -> dict[str, Path]:
        """Create the standard project directory structure."""
        dirs = {}
        for stage in PROJECT_STAGES:
            stage_dir = self.project_dir / stage
            if stage == "06_video":
                (stage_dir / "storyboard").mkdir(parents=True, exist_ok=True)
                (stage_dir / "shots").mkdir(parents=True, exist_ok=True)
                (stage_dir / "clips").mkdir(parents=True, exist_ok=True)
                (stage_dir / "final").mkdir(parents=True, exist_ok=True)
            else:
                stage_dir.mkdir(parents=True, exist_ok=True)
            dirs[stage] = stage_dir
        return dirs

    def save_project_state(self, project: dict) -> Path:
        """Save project state to project.json."""
        project_path = self.project_dir / "project.json"
        project["updated_at"] = datetime.now().isoformat()
        project_path.write_text(
            json.dumps(project, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return project_path

    def load_project_state(self) -> dict:
        """Load project state from project.json."""
        project_path = self.project_dir / "project.json"
        if project_path.exists():
            return json.loads(project_path.read_text(encoding="utf-8"))
        return {}

    def get_stage_dir(self, stage: str) -> Path:
        """Get the directory for a specific stage."""
        if stage == "research":
            return self.project_dir / "00_research"
        elif stage == "angle":
            return self.project_dir / "01_angle"
        elif stage == "lyrics":
            return self.project_dir / "02_lyrics"
        elif stage == "voice":
            return self.project_dir / "03_voice"
        elif stage == "song":
            return self.project_dir / "04_song"
        elif stage == "visual":
            return self.project_dir / "05_visual"
        elif stage == "video":
            return self.project_dir / "06_video"
        else:
            return self.project_dir

    def list_all_outputs(self) -> dict[str, list[str]]:
        """List all output files organized by stage."""
        outputs = {}
        for stage in PROJECT_STAGES:
            stage_dir = self.project_dir / stage
            if stage_dir.exists():
                files = [str(p.relative_to(self.project_dir)) for p in stage_dir.rglob("*") if p.is_file()]
                if files:
                    outputs[stage] = files
        return outputs
