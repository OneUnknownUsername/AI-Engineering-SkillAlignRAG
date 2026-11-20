"""Re-audit one course and level after an upload (run by the dashboard in its own process).

Loads the models, audits every skill at that course and level with audit_level, and writes
the new cells together with the course's document availability and CI-slide comparison.

  python -m src.dashboard.reaudit --output-dir WORKSPACE/outputs --course SAIA2143 --level Taught --result OUT.json
"""
import argparse
from pathlib import Path

from src.common import COURSES, LEVELS, write_json
from src.config import AuditConfig
from src.run_skill_audit_pipeline import audit_level, prepare_audit


def reaudit(output_dir: Path, course: str, level: str, result_path: Path, offline: bool) -> None:
    if course not in COURSES or level not in LEVELS.values():
        raise ValueError(f"Unsupported course or level: {course} / {level}")
    ctx, data = prepare_audit(output_dir, AuditConfig(offline=offline))
    cells = [{"course_code": course, "skill_id": skill["skill_id"], "level": level,
              "routed": audit_level(ctx, course, skill, level)}
             for skill in sorted(data["skills"], key=lambda s: s["skill_id"])]
    write_json(result_path, {"cells": cells, "availability": data["availability"][course],
                             "clo_slide_comparison": data["clo_slide_comparison"][course],
                             "code_version": data["code_version"], "hardware": data["hardware"]})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--course", required=True)
    parser.add_argument("--level", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    reaudit(args.output_dir, args.course, args.level, args.result, args.offline)


if __name__ == "__main__":
    main()
