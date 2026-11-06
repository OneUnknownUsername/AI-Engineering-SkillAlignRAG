"""Shared deterministic PDF/OCR extraction; generated vision text stays separate."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import pymupdf as fitz
import numpy as np
import pdfplumber
from PIL import Image, ImageDraw

from src.common import fingerprint, normalize, read_json, write_json

BOILERPLATE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:fai\.)?utm\.my\S*|Innovating Solutions|"
    r"Faculty of Artificial Intelligence,?\s*UTM|utmfai|univteknologimalaysia|utmofficial",
    re.IGNORECASE,
)
PII = {
    "email": re.compile(r"[\w.+-]+@[\w.-]+(?:\.[A-Za-z]{2,})?"),
    "phone": re.compile(r"(?<!\w)(?:\+?60[- .]?|0)1\d(?:[- .]?\d){7,8}(?!\d)"),
    "office_room": re.compile(
        r"\b(?:(?:office(?:\s+room)?|room|bilik)(?:\s+(?:no\.?|number))?\s*[:#]\s*"
        r"(?:[A-Z]{1,12}\s+)?(?=[\w.-]*\d)[\w]+(?:[.-][\w]+)*|MJIIT\s*\d+)\b", re.IGNORECASE
    ),
}


def clean(text: str, *, boilerplate: bool = True) -> tuple[str, list[dict]]:
    text = text.replace("\x00", "").replace("\u00a7", "")
    lines = []
    for line in text.splitlines():
        compact = re.sub(r"\s+", "", line)
        if re.match(r"(?:[A-Za-z]\s+){3,}", line) and re.match(
            r"(?:e-?mail|whatsapp|phone|telephone|tel|mobile|office|room|bilik):", compact, re.I
        ):
            line = compact
        lines.append(line)
    text = "\n".join(lines)
    events = []
    for kind, pattern in PII.items():
        def replace(match):
            # Never copy sensitive values into the quality report.
            events.append({"kind": kind, "offset": match.start()})
            return "[REDACTED_PII]"
        text = pattern.sub(replace, text)
    if boilerplate:
        text = BOILERPLATE.sub("", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()), events


def unique_lines(text: str, existing: str = "") -> str:
    seen = {normalize(line).casefold() for line in existing.splitlines()}
    whole = normalize(existing).casefold()
    kept = []
    for line in text.splitlines():
        key = normalize(line).casefold()
        contained = bool(key) and re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", whole) is not None
        if key and key not in seen and not contained:
            kept.append(line.strip())
            seen.add(key)
    return "\n".join(kept)


def markdown_table(rows: list[list]) -> str:
    if not rows:
        return ""
    width = max(map(len, rows))
    normalized = [[normalize(str(cell or "")).replace("|", "\\|") for cell in row]
                  + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(row) + " |" for row in normalized]
    return "\n".join([lines[0], "| " + " | ".join(["---"] * width) + " |", *lines[1:]])


def ordered_text(page) -> str:
    blocks = [b for b in page.get_text("blocks", sort=True) if b[6] == 0]
    midpoint = page.rect.width / 2
    left = [b for b in blocks if b[2] <= midpoint + 10]
    right = [b for b in blocks if b[0] >= midpoint - 10]
    if not left or not right:
        return "\n".join(b[4].strip() for b in blocks)
    # Full-width blocks delimit horizontal bands; read each band's columns top-down.
    spanning = sorted([b for b in blocks if b not in left and b not in right], key=lambda b: b[1])
    remaining = [b for b in blocks if b not in spanning]
    result = []
    for boundary in [*spanning, None]:
        band = [b for b in remaining if boundary is None or b[1] < boundary[1]]
        result.extend(sorted(band, key=lambda b: (b[0] >= midpoint - 10, b[1], b[0])))
        remaining = [b for b in remaining if b not in band]
        if boundary is not None:
            result.append(boundary)
    return "\n".join(b[4].strip() for b in result)


def printed_number(page) -> str | None:
    candidates = []
    for block in page.get_text("blocks", sort=True):
        if block[6] == 0 and block[1] > page.rect.height * .82:
            value = block[4].strip()
            match = re.fullmatch(r"(?:slide\s*|page\s*)?(\d{1,3})(?:\s*/\s*\d{1,3})?", value, re.I)
            if match:
                candidates.append(match.group(1))
    return candidates[-1] if candidates else None


def page_title(page) -> str:
    lines = []
    for block in page.get_text("dict", sort=True)["blocks"]:
        for line in block.get("lines", []):
            text, _ = clean("".join(span["text"] for span in line["spans"]))
            if len(re.findall(r"[A-Za-z]", text)) < 5 or "[REDACTED_PII]" in text:
                continue
            if re.search(r"prepared by|lecturer|whatsapp|e-?mail|^room\b|^session\b", text, re.I):
                continue
            lines.append((max(span["size"] for span in line["spans"]), text))
    if not lines:
        return ""
    largest = max(size for size, _ in lines)
    return " ".join(text for size, text in lines if size >= largest * .8)[:400]


def mask_native_words(png: bytes, page, dpi: int) -> bytes:
    """Keep visible image text for OCR; native word pixels are already captured."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    drawing = ImageDraw.Draw(image)
    scale = dpi / 72
    for word in page.get_text("words"):
        rectangle = fitz.Rect(word[:4]) * page.rotation_matrix
        drawing.rectangle((int(rectangle.x0 * scale) - 1, int(rectangle.y0 * scale) - 1,
                           int(rectangle.x1 * scale) + 1, int(rectangle.y1 * scale) + 1), fill="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def covered_area(rectangles) -> float:
    """Union area, so overlapping image placements cannot inflate the VLM trigger."""
    xs = sorted({x for r in rectangles for x in (r.x0, r.x1)})
    area = 0.0
    for lo, hi in zip(xs, xs[1:]):
        intervals = sorted((r.y0, r.y1) for r in rectangles if r.x0 < hi and r.x1 > lo)
        end = float("-inf")
        height = 0.0
        for bottom, top in intervals:
            height += max(0, top - max(bottom, end))
            end = max(end, top)
        area += (hi - lo) * height
    return area


@dataclass
class ExtractionConfig:
    enable_ocr: bool = True
    enable_vision_llm: bool = False
    vision_model: str = "qwen2.5vl:3b"
    ollama_url: str = "http://localhost:11434/api/generate"
    render_dpi: int = 140
    vision_timeout: int = 90
    ocr_threads: int = 8


class PDFExtractor:
    def __init__(self, config: ExtractionConfig, cache_dir: Path | None = None):
        self.config = config
        self.cache_dir = cache_dir
        self.ocr = None
        self.ocr_results = {}
        self.vision_unavailable = None
        if config.enable_ocr:
            from rapidocr_onnxruntime import RapidOCR
            if config.ocr_threads < 1:
                raise ValueError("ocr_threads must be positive")
            self.ocr = RapidOCR(intra_op_num_threads=min(config.ocr_threads, os.cpu_count() or 1),
                                inter_op_num_threads=1)
        parsed = urlparse(config.ollama_url)
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.scheme != "http":
            raise ValueError("Vision inference must use a local HTTP Ollama endpoint")

    def vision(self, png: bytes) -> tuple[str, str | None]:
        if self.vision_unavailable:
            return "", self.vision_unavailable
        payload = {
            "model": self.config.vision_model, "stream": False,
            "prompt": "Briefly describe the technical workflow, components, or relationships shown "
                      "in this educational diagram in 2-3 factual sentences. Do not invent concepts not shown. "
                      "If no technical diagram is visible, return an empty response.",
            "images": [base64.b64encode(png).decode()], "options": {"temperature": 0},
        }
        request = urllib.request.Request(self.config.ollama_url, json.dumps(payload).encode(),
                                         {"Content-Type": "application/json"})
        try:
            # Ignore system proxies and redirects: page images must remain on loopback.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=self.config.vision_timeout) as response:
                result = json.load(response)
            if "error" in result or not isinstance(result.get("response"), str):
                raise ValueError("Ollama returned no usable response")
            return result["response"].strip(), None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            self.vision_unavailable = f"Ollama unavailable: {type(error).__name__}"
            return "", self.vision_unavailable

    def recognize(self, png: bytes, *, use_cache: bool = True):
        if not use_cache:
            result, _ = self.ocr(np.array(Image.open(io.BytesIO(png)).convert("RGB")))
            return result or []
        digest = hashlib.sha256(png).digest()
        if digest not in self.ocr_results:
            result, _ = self.ocr(np.array(Image.open(io.BytesIO(png)).convert("RGB")))
            self.ocr_results[digest] = result or []
        return self.ocr_results[digest]

    def extract(self, path, *, force_ocr: bool = False):
        path = Path(path)
        settings = asdict(self.config)
        settings.pop("ocr_threads")  # Thread count changes throughput, not the extraction contract.
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        key = fingerprint({"source_sha256": source_hash, "config": settings,
                           "extractor_revision": 4, "force_ocr": force_ocr})
        cache = self.cache_dir / (key + ".json") if self.cache_dir is not None else None
        legacy_key = fingerprint({"source_sha256": source_hash, "config": settings, "extractor_revision": 2})
        legacy = self.cache_dir / (legacy_key + ".json") if self.cache_dir is not None else None
        if cache is not None and cache.is_file():
            pages = read_json(cache)
            previous = fingerprint(pages)
        elif legacy is not None and legacy.is_file():
            pages = read_json(legacy)
            # Looser privacy rules cannot restore text from redacted strings. Reparse
            # affected source pages, and bypass every legacy CI page for full OCR.
            refresh = {p["pdf_page_no"] for p in pages if force_ocr or
                       any(e["kind"] == "office_room" for e in p["redaction_events"])}
            if refresh:
                replacements = {p["pdf_page_no"]: p for p in self._extract(
                    path, force_ocr=force_ocr, page_numbers=refresh)}
                pages = [replacements.get(p["pdf_page_no"], p) for p in pages]
            previous = None
        else:
            pages = list(self._extract(path, force_ocr=True)) if force_ocr else list(self._extract(path))
            previous = None
        for page in pages:
            for field in ("native_text", "ocr_extracted_text", "tables_markdown", "visual_diagram_summary",
                          "slide_or_section_title"):
                page[field], events = clean(page.get(field, ""))
                page["redaction_events"].extend(events)
            page["verbatim_text_span"] = normalize("\n".join(filter(None, [page["native_text"], page["ocr_extracted_text"]])))
            page.setdefault("table_extraction_status", "completed")
            page.setdefault("ocr_forced", False)
            yield page
        # A failed Ollama request must be retryable on the next ingestion run.
        if cache is not None and fingerprint(pages) != previous and not any(page["vision_error"] for page in pages):
            write_json(cache, pages)

    def _extract(self, path, *, force_ocr: bool = False, page_numbers: set[int] | None = None):
        with fitz.open(path) as document, pdfplumber.open(path) as tables_document:
            if document.needs_pass:
                raise ValueError(f"Encrypted PDF: {path}")
            for number, page in enumerate(document, 1):
                if page_numbers is not None and number not in page_numbers:
                    continue
                native_raw = ordered_text(page)
                native, events = clean(native_raw)
                table_text, table_events = clean("\n\n".join(
                    markdown_table(table) for table in tables_document.pages[number - 1].extract_tables()
                ))
                events.extend(table_events)
                images = page.get_image_info(xrefs=True)
                large_images = [fitz.Rect(info["bbox"]) & page.rect for info in images
                                if info["width"] >= 150 and info["height"] >= 150]
                image_fraction = covered_area(large_images) / page.rect.get_area()
                ocr_trigger = force_ocr or bool(large_images) or len(native_raw.split()) < 40
                vision_trigger = image_fraction > .25 and self.config.enable_vision_llm
                png = None
                ocr_text = ""
                printed = printed_number(page)
                methods = ["native_text"] if native else []
                sparse = len(native_raw.split()) < 40
                if (ocr_trigger and self.ocr is not None) or vision_trigger:
                    png = page.get_pixmap(dpi=self.config.render_dpi, alpha=False).tobytes("png")
                if ocr_trigger and self.ocr is not None:
                    result = self.recognize(png if force_ocr else mask_native_words(png, page, self.config.render_dpi),
                                            use_cache=not force_ocr)
                    ocr_raw = "\n".join(item[1] for item in result or [] if item[2] >= .5)
                    if sparse and printed is None:
                        for box, text, confidence in result:
                            match = re.fullmatch(r"(?:slide\s*|page\s*)?(\d{1,3})(?:\s*/\s*\d{1,3})?", text.strip(), re.I)
                            if box and confidence >= .5 and match and min(point[1] for point in box) > page.rect.height * self.config.render_dpi / 72 * .82:
                                printed = match.group(1)
                    ocr_text, ocr_events = clean(ocr_raw)
                    events.extend(ocr_events)
                    ocr_text = unique_lines(ocr_text, native)
                    methods.append("rapidocr")
                summary, vision_error = "", None
                if vision_trigger:
                    summary, vision_error = self.vision(png)
                    summary, summary_events = clean(summary)
                    events.extend(summary_events)
                    if summary:
                        methods.append("ollama_vision")
                yield {
                    "pdf_page_no": number, "printed_slide_no": printed,
                    "slide_or_section_title": page_title(page) or next(iter(ocr_text.splitlines()), ""),
                    "native_text": native, "ocr_extracted_text": ocr_text,
                    "verbatim_text_span": normalize("\n".join(filter(None, [native, ocr_text]))),
                    "tables_markdown": table_text, "visual_diagram_summary": summary,
                    "extraction_methods_used": methods, "redaction_events": events,
                    "ocr_triggered": ocr_trigger, "ocr_status": "completed" if ocr_trigger and self.ocr else
                        "disabled" if ocr_trigger else "not_needed",
                    "ocr_native_word_masking": ocr_trigger and self.ocr is not None and not force_ocr,
                    "ocr_forced": force_ocr, "table_extraction_status": "completed",
                    "vision_triggered": vision_trigger, "vision_error": vision_error,
                    "image_area_fraction": round(image_fraction, 4),
                }


def extractor_from_args(args) -> PDFExtractor:
    return PDFExtractor(ExtractionConfig(not args.disable_ocr, args.enable_vision_llm,
                                         args.vision_model, args.ollama_url, ocr_threads=args.ocr_threads),
                        args.output_dir / "extraction_cache")
