from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
# The model's output could not be read, so the cell has no answer and needs manual review.
GENERATION_ERROR = "Generation Error"
LEVELS = {
    "01_CI_CLO": "CLO",
    "02_Lecture_Slides_Taught": "Taught",
    "03_Assessments_Assessed": "Assessed",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_courses(config_dir: Path = CONFIG_DIR) -> dict[str, str]:
    """Course codes and titles: config/courses.json plus the optional courses_extension.json."""
    courses = dict(read_json(config_dir / "courses.json"))
    extension = config_dir / "courses_extension.json"
    if extension.is_file():
        added = read_json(extension)
        repeated = sorted(set(courses) & set(added))
        if repeated:
            raise ValueError(f"courses_extension.json repeats core courses: {repeated}")
        courses.update(added)
    if not courses or any(not isinstance(v, str) or not k.strip() or not v.strip() for k, v in courses.items()):
        raise ValueError("Course config must map course codes to course titles")
    return courses


def load_skill_definitions(config_dir: Path = CONFIG_DIR) -> list[dict]:
    """The locked core skills (benchmark_skills.json), then the optional extension set."""
    extension = config_dir / "benchmark_skills_extension.json"
    return read_json(config_dir / "benchmark_skills.json") + (read_json(extension) if extension.is_file() else [])


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


# Read once at import; on main there are no extension files, so this is the three V1 courses.
COURSES = load_courses()


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
