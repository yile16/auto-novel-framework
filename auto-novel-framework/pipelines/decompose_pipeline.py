"""Full decomposition pipeline — orchestrates chunk → extract → merge → finalize."""

from __future__ import annotations

import json
import logging
import yaml
from pathlib import Path

from config import DecomposeConfig
from utils.text import split_by_chapter
from utils.io import read_novel
from core.decomposer.extractor import ChapterExtractor
from core.decomposer.merger import ArcMerger
from core.decomposer.finalizer import BookFinalizer
from core.models.story import StoryDecomposition
from utils.markdown_writer import decomposition_to_markdown

logger = logging.getLogger(__name__)


class DecomposePipeline:
    """
    Full novel decomposition pipeline:

    1. Chunk novel into chapters
    2. Extract raw data from each chapter (parallel)
    3. Merge chapters into arc states (sequential, 15 chapters per arc)
    4. Finalize all arc states into complete book decomposition
    5. Save output YAML + JSON
    """

    def __init__(self, config: DecomposeConfig):
        self.config = config
        self.extractor = ChapterExtractor(config)
        self.merger = ArcMerger(config)
        self.finalizer = BookFinalizer(config)

    def run(self, filepath: str | Path, output_dir: str | Path | None = None) -> StoryDecomposition:
        """
        Run the full decomposition pipeline on a novel file.

        Args:
            filepath: Path to the novel file (.txt or .epub)
            output_dir: Directory to save output files (default from config)

        Returns:
            Complete StoryDecomposition
        """
        filepath = Path(filepath)
        output_dir = Path(output_dir or self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Read and chunk
        logger.info("Step 1: Reading novel file...")
        novel = read_novel(filepath)
        logger.info(f"Loaded: {novel.title}, {len(novel.text)} characters")

        logger.info("Step 2: Chunking into chapters...")
        chunks = split_by_chapter(
            novel.text,
            max_tokens=self.config.max_chunk_tokens,
            overlap_tokens=self.config.chunk_overlap_tokens,
        )
        logger.info(f"Split into {len(chunks)} chunks")

        # Step 2: Extract per chapter (parallel)
        logger.info("Step 3: Extracting per-chapter data (parallel)...")
        extractions = self.extractor.extract_batch(chunks)
        logger.info(f"Extracted {len(extractions)} chapters")

        # Save raw extractions for debugging
        raw_path = output_dir / "raw_extractions.json"
        raw_path.write_text(
            json.dumps(
                [e.model_dump(exclude_none=True) for e in extractions],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(f"Raw extractions saved to {raw_path}")

        # Step 3: Merge into arcs
        logger.info("Step 4: Merging chapters into arcs...")
        arc_size = self.config.chapters_per_arc
        batches = [
            extractions[i : i + arc_size]
            for i in range(0, len(extractions), arc_size)
        ]
        arc_states = self.merger.merge_all_arcs_sequentially(batches)
        logger.info(f"Merged into {len(arc_states)} arc states")

        # Save arc states
        arc_path = output_dir / "arc_states.json"
        arc_path.write_text(
            json.dumps(arc_states, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Step 4: Finalize book
        logger.info("Step 5: Finalizing book decomposition...")
        result = self.finalizer.finalize(
            arc_states,
            title=novel.title,
            author=novel.author,
            total_chapters=len(extractions),
        )

        # Step 5: Save output
        self._save_output(result, output_dir)

        logger.info("Decomposition complete!")
        return result

    def _save_output(self, result: StoryDecomposition, output_dir: Path):
        """Save the decomposition in both YAML and JSON formats."""
        data = result.model_dump(exclude_none=True)

        # YAML output
        yaml_path = output_dir / "decomposition.yaml"
        yaml_path.write_text(
            yaml.dump(data, allow_unicode=True, sort_keys=False, width=200),
            encoding="utf-8",
        )

        # JSON output
        json_path = output_dir / "decomposition.json"
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Markdown output
        md_path = decomposition_to_markdown(json_path, output_dir / "decomposition.md")
        logger.info(f"Output saved to:\n  {yaml_path}\n  {json_path}\n  {md_path}")
