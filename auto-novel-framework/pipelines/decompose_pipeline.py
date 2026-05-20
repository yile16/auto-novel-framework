"""Full decomposition pipeline — chunk → extract (full concurrency) → merge → output."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config import DecomposeConfig
from utils.text import split_by_chapter
from utils.io import read_novel
from core.decomposer.extractor import ChapterExtractor
from core.decomposer.programmatic_merger import ProgrammaticMerger
from core.models.story import StoryDecomposition
from utils.markdown_writer_v3 import write_all

logger = logging.getLogger(__name__)


class DecomposePipeline:
    """
    Simplified novel decomposition pipeline:

    1. Read and chunk novel into chapters
    2. Extract ALL chapters in full concurrency (no batching, no context relay)
    3. Programmatic merge (no LLM, no data loss)
    4. Output 7 thematic markdown files + JSON
    """

    def __init__(self, config: DecomposeConfig):
        self.config = config
        self.extractor = ChapterExtractor(config)
        self.merger = ProgrammaticMerger()

    def run(self, filepath: str | Path, output_dir: str | Path | None = None) -> StoryDecomposition:
        filepath = Path(filepath)
        output_dir = Path(output_dir or self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Read and chunk
        logger.info("Step 1: Reading novel file...")
        novel = read_novel(filepath)
        logger.info(f"Loaded: {novel.title}, {len(novel.text)} chars")

        logger.info("Step 2: Splitting into chapters...")
        chunks = split_by_chapter(
            novel.text,
            max_tokens=self.config.max_chunk_tokens,
            overlap_tokens=self.config.chunk_overlap_tokens,
        )
        logger.info(f"Split into {len(chunks)} chapters")

        # Step 3: Extract all chapters in full concurrency
        logger.info("Step 3: Extracting all chapters (full concurrency)...")
        extractions = self.extractor.extract_all(
            chunks,
            max_workers=self.config.max_concurrent_extractions,
        )
        logger.info(f"Extracted {len(extractions)} chapters")

        # Save raw extractions
        raw_path = output_dir / "raw_extractions.json"
        raw_path.write_text(
            json.dumps(
                [e.model_dump(exclude_none=True) for e in extractions],
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(f"Raw extractions saved to {raw_path}")

        # Step 3: Programmatic merge
        logger.info("Step 4: Programmatic merge...")
        raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
        result = self.merger.merge(raw_data, title=novel.title, author=novel.author)

        # Step 4: Save outputs
        self._save_output(result, output_dir, raw_data)

        logger.info("Decomposition complete!")
        return result

    def _save_output(self, result: StoryDecomposition, output_dir: Path, raw_data: list[dict]):
        # JSON (machine-readable)
        data = result.model_dump(exclude_none=True)
        json_path = output_dir / "decomposition.json"
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 7 thematic markdown files (outline, characters, world, relationships, beats, rhythm, index)
        md_paths = write_all(result, output_dir, raw_extractions=raw_data)
        logger.info(f"Output saved: {json_path} + {len(md_paths)} markdown files")
