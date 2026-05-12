"""Component repository — stores and indexes decomposed novel components."""

import json
import yaml
from pathlib import Path

from core.models.story import StoryDecomposition


class Repository:
    """File-based storage for novel decompositions."""

    def __init__(self, base_dir: str | Path = "store"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, decomposition: StoryDecomposition, name: str | None = None):
        """Save a decomposition to the store."""
        name = name or decomposition.title or "untitled"
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
        dir_path = self.base_dir / safe_name
        dir_path.mkdir(parents=True, exist_ok=True)

        data = decomposition.model_dump(exclude_none=True)

        yaml_path = dir_path / "decomposition.yaml"
        yaml_path.write_text(
            yaml.dump(data, allow_unicode=True, sort_keys=False, width=200),
            encoding="utf-8",
        )

        json_path = dir_path / "decomposition.json"
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, name: str) -> StoryDecomposition:
        """Load a decomposition from the store."""
        json_path = self.base_dir / name / "decomposition.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Decomposition not found: {name}")
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return StoryDecomposition.model_validate(data)

    def list_all(self) -> list[str]:
        """List all stored decompositions."""
        if not self.base_dir.exists():
            return []
        return [
            d.name for d in self.base_dir.iterdir()
            if d.is_dir() and (d / "decomposition.json").exists()
        ]


class Indexer:
    """Search and index components across stored decompositions."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def search_characters(self, query: str) -> list[dict]:
        """Search characters across all stored decompositions."""
        results = []
        for name in self.repo.list_all():
            dec = self.repo.load(name)
            for char in dec.characters:
                if query.lower() in char.name.lower():
                    results.append({
                        "source": name,
                        "character": char.model_dump(exclude_none=True),
                    })
        return results

    def search_locations(self, query: str) -> list[dict]:
        """Search locations across all stored decompositions."""
        results = []
        for name in self.repo.list_all():
            dec = self.repo.load(name)
            for loc in dec.world_setting.locations:
                if query.lower() in loc.name.lower():
                    results.append({
                        "source": name,
                        "location": loc.model_dump(exclude_none=True),
                    })
        return results

    def search_plot_threads(self, query: str) -> list[dict]:
        """Search plot threads by type or name."""
        results = []
        for name in self.repo.list_all():
            dec = self.repo.load(name)
            for thread in dec.plot.threads:
                if query.lower() in thread.name.lower() or query.lower() in thread.type.lower():
                    results.append({
                        "source": name,
                        "thread": thread.model_dump(exclude_none=True),
                    })
        return results
