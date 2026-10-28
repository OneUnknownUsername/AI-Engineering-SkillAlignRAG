"""Normalize Office documents without modifying the supplied course materials."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf as fitz

from src.common import ROOT, base_parser, read_json, write_json


def valid_pdf(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with fitz.open(path) as doc:
            return bool(doc.page_count) and not doc.needs_pass
    except (fitz.FileDataError, RuntimeError):
        return False


def console_launcher(path: Path) -> str:
    console = path.with_suffix(".com")
    return str(console if os.name == "nt" and console.is_file() else path)


def find_soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return console_launcher(Path(found))
    for root in [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")]:
        candidate = Path(root) / "LibreOffice/program/soffice.exe"
        if candidate.is_file():
            return console_launcher(candidate)
    runtime = ROOT / "outputs/tools/libreoffice_runtime.json"
    if runtime.is_file():
        candidate = Path(read_json(runtime)["soffice_path"])
        if candidate.is_file():
            return console_launcher(candidate)
    return None


def office_convert(source: Path, destination: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("Install LibreOffice to convert Office files on this platform")
    if source.suffix.lower() == ".docx":
        try:
            from docx2pdf import convert
            import pywintypes
        except ImportError as error:
            raise RuntimeError("Install LibreOffice or requirements-windows.txt plus Microsoft Office") from error
        try:
            convert(str(source.resolve()), str(destination.resolve()))
        except pywintypes.com_error as error:
            raise RuntimeError("Microsoft Word conversion failed; verify Office is installed and licensed") from error
    else:
        try:
            import comtypes.client
            from _ctypes import COMError
        except ImportError as error:
            raise RuntimeError("Install LibreOffice or comtypes plus Microsoft PowerPoint") from error
        app = None
        presentation = None
        try:
            app = comtypes.client.CreateObject("Powerpoint.Application")
            presentation = app.Presentations.Open(str(source.resolve()), ReadOnly=True, WithWindow=False)
            presentation.SaveAs(str(destination.resolve()), 32)
        except (COMError, OSError) as error:
            raise RuntimeError("Microsoft PowerPoint conversion failed; verify Office is installed and licensed") from error
        finally:
            if presentation is not None:
                presentation.Close()
            if app is not None:
                app.Quit()


def normalize_formats(data_dir: Path, output_dir: Path) -> list[dict]:
    root = data_dir / "courses"
    records = []
    converter = find_soffice()
    for source in sorted(root.rglob("*")) if root.exists() else []:
        if not source.is_file() or source.suffix.lower() not in {".pdf", ".pptx", ".docx"}:
            continue
        record = {"source_path": str(source.resolve()), "source_relative_path": source.relative_to(root).as_posix(),
                  "original_format": source.suffix[1:].lower(), "status": "ready", "error": None}
        pdf = source
        if source.suffix.lower() != ".pdf":
            sibling = source.with_suffix(".pdf")
            # Include the source extension to avoid DOCX/PPTX same-stem cache collisions.
            pdf = output_dir / "normalized_pdf" / source.relative_to(root).parent / (source.name + ".pdf")
            if valid_pdf(sibling) and sibling.stat().st_mtime_ns >= source.stat().st_mtime_ns:
                pdf = sibling
            elif not valid_pdf(pdf) or pdf.stat().st_mtime_ns < source.stat().st_mtime_ns:
                pdf.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with tempfile.TemporaryDirectory(dir=pdf.parent) as temporary:
                        temporary = Path(temporary)
                        generated = temporary / (source.stem + ".pdf")
                        if converter:
                            profile = temporary / "profile"
                            result = subprocess.run(
                                [converter, f"-env:UserInstallation={profile.resolve().as_uri()}", "--headless",
                                 "--convert-to", "pdf", "--outdir", str(temporary.resolve()), str(source.resolve())],
                                capture_output=True, text=True, timeout=180, check=False,
                            )
                            if result.returncode:
                                raise RuntimeError(f"LibreOffice exited with code {result.returncode}")
                        else:
                            office_convert(source, generated)
                        if not valid_pdf(generated):
                            raise RuntimeError("Converter did not produce a valid PDF")
                        generated.replace(pdf)
                except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                    record.update(status="conversion_failed", error=str(error))
        if record["status"] == "ready" and not valid_pdf(pdf):
            record.update(status="invalid_pdf", error="Unreadable, empty or encrypted PDF")
        record["pdf_path"] = str(pdf.resolve())
        records.append(record)
    # A current sibling PDF is represented by its original Office source only once.
    office_targets = {str(Path(r["source_path"]).with_suffix(".pdf")) for r in records
                      if r["original_format"] != "pdf"}
    records = [r for r in records if r["original_format"] != "pdf" or r["pdf_path"] not in office_targets]
    write_json(output_dir / "normalization_manifest.json", records)
    return records


def main() -> None:
    parser = base_parser(__doc__)
    args = parser.parse_args()
    records = normalize_formats(args.data_dir, args.output_dir)
    failures = [r for r in records if r["status"] != "ready"]
    print(f"Normalization: {len(records)} documents; {len(failures)} failures. See normalization_manifest.json")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
