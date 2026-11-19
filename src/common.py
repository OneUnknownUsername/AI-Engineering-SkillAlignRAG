from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COURSES = {
    "SAIA1013": "Responsible AI and Ethics",
    "SAIA2113": "Machine Learning",
    "SAIA2143": "Data Wrangling and Visualization",
}
LEVELS = {
    "01_CI_CLO": "CLO",
    "02_Lecture_Slides_Taught": "Taught",
    "03_Assessments_Assessed": "Assessed",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def code_version(root: Path = ROOT) -> dict:
    """The commit that produced an output, and any uncommitted edits to code or configuration."""
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout if result.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    if commit is None:
        return {"commit": "not recorded", "uncommitted_code_changes": None, "changed_paths": []}
    changed = sorted(line[3:] for line in (git("status", "--porcelain", "--", "src", "config") or "").splitlines() if line.strip())
    return {"commit": commit.strip(), "uncommitted_code_changes": bool(changed), "changed_paths": changed}


def normalize(text: str) -> str:
    return " ".join(text.split())


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z0-9]+", text.lower())


def evidence_levels(chunk: dict) -> list[str]:
    # A page is evidence only for the folder it was supplied in. Slides that restate the
    # CLOs stay Taught: the Course Information document alone decides CLO coverage (FR3).
    return [chunk.get("source_evidence_level", chunk["evidence_level"])]


def base_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    return parser


def extraction_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--disable-ocr", action="store_true", help="Explicit native-only diagnostic mode")
    parser.add_argument("--enable-vision-llm", action="store_true", help="Use local Ollama for large visuals")
    parser.add_argument("--vision-model", default="qwen2.5vl:3b")
    parser.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    parser.add_argument("--ocr-threads", type=int, default=8, help="ONNX intra-op threads per extraction worker")


def md(text: str) -> str:
    return normalize(str(text)).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
