"""Optical Character Recognition module for Fiona.

Provides Tesseract-based OCR on images, screen regions, and window regions.
All public functions handle missing dependencies gracefully by returning
OcrResult with error information instead of raising.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache for tesseract availability
# ---------------------------------------------------------------------------
_TESSERACT_AVAILABLE: bool | None = None


def tesseract_available() -> bool:
    """Check whether the Tesseract OCR engine is installed and usable.

    Results are cached in a module-level variable after the first call.
    The check verifies that the ``tesseract`` binary is on ``PATH`` **and**
    that ``pytesseract`` can successfully query its version.

    Returns:
        True if tesseract is available, False otherwise.
    """
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is not None:
        return _TESSERACT_AVAILABLE

    if not shutil.which("tesseract"):
        logger.debug("tesseract binary not found on PATH")
        _TESSERACT_AVAILABLE = False
        return False

    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        _TESSERACT_AVAILABLE = True
    except (OSError, ImportError, Exception) as exc:
        logger.debug("pytesseract could not contact tesseract: %s", exc)
        _TESSERACT_AVAILABLE = False

    return _TESSERACT_AVAILABLE


def list_supported_languages() -> list[str]:
    """Return the list of language codes supported by the installed Tesseract.

    Returns:
        A list of language codes (e.g. ``["eng", "osd"]``).  Returns an empty
        list if Tesseract is not available or the language list cannot be
        queried.
    """
    if not tesseract_available():
        return []

    try:
        import pytesseract

        return pytesseract.get_languages() or []
    except Exception as exc:
        logger.debug("failed to list tesseract languages: %s", exc)
        return []


# ---------------------------------------------------------------------------
# OcrResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class OcrResult:
    """Structured result from an OCR operation.

    Attributes:
        text: The full extracted text (concatenated).
        confidence: Average confidence across all detected items (0.0–100.0).
            Returns 0.0 if confidence data is unavailable.
        boxes: A list of per-word/block dictionaries, each containing
            ``x``, ``y``, ``w``, ``h``, ``text``, and ``conf`` keys.
        language: The language code used for OCR.
        error: Human-readable error message if the operation failed,
            otherwise ``None``.
        success: ``True`` when *error* is ``None``.
    """

    text: str = ""
    confidence: float = 0.0
    boxes: list[dict[str, Any]] = field(default_factory=list)
    language: str = "eng"
    error: str | None = None

    @property
    def success(self) -> bool:
        """Return ``True`` if the OCR operation finished without error."""
        return self.error is None


# ---------------------------------------------------------------------------
# Core OCR helpers (internal)
# ---------------------------------------------------------------------------

def _run_pytesseract(
    image: Any,
    *,
    lang: str = "eng",
    psm: int = 3,
    timeout: int = 30,
) -> OcrResult:
    """Run ``pytesseract.image_to_data`` and parse the result.

    This function does the actual OCR dispatch.  It is called by the
    public ``read_image*`` wrappers.

    Args:
        image: A PIL ``Image`` instance ready for OCR.
        lang: Tesseract language code(s).  Multiple languages can be
            specified with ``+`` (e.g. ``"eng+fra"``).
        psm: Tesseract page segmentation mode (default 3 = fully automatic).
        timeout: Maximum seconds to wait for the tesseract subprocess.

    Returns:
        An :class:`OcrResult` with extracted data or error details.
    """
    if not tesseract_available():
        return OcrResult(
            language=lang,
            error="Tesseract is not available. Install tesseract-ocr and pytesseract.",
        )

    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        return OcrResult(
            language=lang,
            error=f"pytesseract package is not installed: {exc}",
        )

    try:
        data: dict[str, list[Any]] = pytesseract.image_to_data(
            image,
            lang=lang,
            config=f"--psm {psm}",
            output_type=Output.DICT,
            timeout=timeout,
        )
    except Exception as exc:
        logger.debug("pytesseract.image_to_data failed: %s", exc)
        return OcrResult(
            language=lang,
            error=f"OCR processing failed: {exc}",
        )

    # Extract per-word boxes and build the full text
    boxes: list[dict[str, Any]] = []
    text_parts: list[str] = []
    conf_values: list[float] = []

    n = len(data.get("text", []))
    for i in range(n):
        word = (data.get("text") or [""] * n)[i] or ""
        conf_raw = (data.get("conf") or [-1] * n)[i]
        conf = float(conf_raw) if conf_raw != -1 else 0.0

        # Skip empty words (Tesseract often returns blank entries for
        # spacing/block-level separators)
        if not word.strip():
            continue

        # Only include items with valid bounding-box data
        x = int((data.get("left") or [0] * n)[i])
        y = int((data.get("top") or [0] * n)[i])
        w = int((data.get("width") or [0] * n)[i])
        h = int((data.get("height") or [0] * n)[i])

        if w == 0 and h == 0:
            # Tesseract may return -1 / 0 for bounding-box fields on block
            # separators; keep them in text but don't include as boxes
            text_parts.append(word)
            if conf > 0:
                conf_values.append(conf)
            continue

        boxes.append({
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "text": word,
            "conf": conf,
        })
        text_parts.append(word)
        if conf > 0:
            conf_values.append(conf)

    # Average confidence across all non-zero entries
    avg_conf: float = 0.0
    if conf_values:
        avg_conf = sum(conf_values) / len(conf_values)

    return OcrResult(
        text=" ".join(text_parts),
        confidence=round(avg_conf, 2),
        boxes=boxes,
        language=lang,
        error=None,
    )


def _crop_and_ocr(
    image: Any,
    region: tuple[int, int, int, int] | None,
    *,
    lang: str = "eng",
    psm: int = 3,
    timeout: int = 30,
) -> OcrResult:
    """Crop the PIL *image* to *region* if provided, then OCR it.

    Region format: ``(left, top, width, height)``.
    """
    if region is not None:
        left, top, width, height = region
        image = image.crop((left, top, left + width, top + height))

    return _run_pytesseract(image, lang=lang, psm=psm, timeout=timeout)


# ---------------------------------------------------------------------------
# Public OCR API
# ---------------------------------------------------------------------------

def read_image(
    image_path: str | Path,
    *,
    lang: str = "eng",
    psm: int = 3,
    timeout: int = 30,
) -> OcrResult:
    """OCR text from an image file on disk.

    Args:
        image_path: Path to the image file (PNG, JPEG, etc.).
        lang: Tesseract language code(s).
        psm: Page segmentation mode (default 3 = auto).
        timeout: Max seconds to wait for tesseract.

    Returns:
        An :class:`OcrResult` with extracted text and metadata.
    """
    try:
        from PIL import Image as PILImage

        image = PILImage.open(str(image_path))
    except Exception as exc:
        return OcrResult(
            language=lang,
            error=f"Failed to open image file {image_path}: {exc}",
        )

    return _run_pytesseract(image, lang=lang, psm=psm, timeout=timeout)


def read_image_pil(
    image: Any,
    *,
    lang: str = "eng",
    psm: int = 3,
    timeout: int = 30,
) -> OcrResult:
    """OCR text from a PIL ``Image`` object directly.

    Args:
        image: A PIL ``Image`` instance.
        lang: Tesseract language code(s).
        psm: Page segmentation mode (default 3 = auto).
        timeout: Max seconds to wait for tesseract.

    Returns:
        An :class:`OcrResult` with extracted text and metadata.
    """
    try:
        # Ensure the image is in a mode Tesseract can handle (RGB / grayscale)
        if image.mode not in ("RGB", "L", "1"):
            image = image.convert("RGB")
    except Exception as exc:
        return OcrResult(
            language=lang,
            error=f"Failed to process PIL image: {exc}",
        )

    return _run_pytesseract(image, lang=lang, psm=psm, timeout=timeout)


def read_screen_region(
    region: tuple[int, int, int, int] | None = None,
    *,
    lang: str = "eng",
    psm: int = 3,
    output_path: str | Path | None = None,
) -> OcrResult:
    """Capture the screen (or a region of it) and perform OCR.

    The screen is captured via :func:`vision.capture_screen`, then
    optionally cropped to *region* and OCRed.

    Args:
        region: Optional ``(left, top, width, height)`` crop region.
            If ``None``, the full screen is OCRed.
        lang: Tesseract language code(s).
        psm: Page segmentation mode (default 3 = auto).
        output_path: If provided, the (potentially cropped) captured
            image is saved to this path for debugging or later inspection.

    Returns:
        An :class:`OcrResult` with extracted text and metadata.
    """
    from .vision import capture_screen

    # Capture screen to a temporary file
    suffix = ".png"
    try:
        tmp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        if not capture_screen(tmp_path):
            return OcrResult(
                language=lang,
                error="Failed to capture screen for OCR.",
            )
    except Exception as exc:
        return OcrResult(
            language=lang,
            error=f"Screen capture failed: {exc}",
        )

    try:
        from PIL import Image as PILImage

        image = PILImage.open(tmp_path)
        result = _crop_and_ocr(image, region, lang=lang, psm=psm)

        # Save the captured (and cropped) image if requested
        if output_path is not None:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            if region is not None:
                left, top, width, height = region
                image.crop((left, top, left + width, top + height)).save(
                    str(output)
                )
            else:
                image.save(str(output))

    except Exception as exc:
        return OcrResult(
            language=lang,
            error=f"Screen region OCR failed: {exc}",
        )
    finally:
        # Clean up the temporary screenshot
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return result


def read_window_region(
    window_id: str,
    region: tuple[int, int, int, int] | None = None,
    *,
    lang: str = "eng",
    psm: int = 3,
) -> OcrResult:
    """Capture a specific desktop window and perform OCR on it (or a region).

    Args:
        window_id: The X11/Wayland window ID (string) to capture.
        region: Optional ``(left, top, width, height)`` crop region
            within the window.  If ``None``, the full window is OCRed.
        lang: Tesseract language code(s).
        psm: Page segmentation mode (default 3 = auto).

    Returns:
        An :class:`OcrResult` with extracted text and metadata.
    """
    from .vision import capture_window

    suffix = ".png"
    try:
        tmp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        if not capture_window(window_id, tmp_path):
            return OcrResult(
                language=lang,
                error=f"Failed to capture window {window_id!r} for OCR.",
            )
    except Exception as exc:
        return OcrResult(
            language=lang,
            error=f"Window capture failed: {exc}",
        )

    try:
        from PIL import Image as PILImage

        image = PILImage.open(tmp_path)
        result = _crop_and_ocr(image, region, lang=lang, psm=psm)
    except Exception as exc:
        return OcrResult(
            language=lang,
            error=f"Window region OCR failed: {exc}",
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return result


# ---------------------------------------------------------------------------
# Region-string parsing
# ---------------------------------------------------------------------------

def parse_region_string(region_str: str) -> tuple[int, int, int, int]:
    """Parse a ``"x,y,w,h"`` formatted string into integer coordinates.

    Args:
        region_str: A string like ``"100,200,300,400"``.

    Returns:
        A tuple of ``(left, top, width, height)``.

    Raises:
        ValueError: If the string cannot be parsed or any component is
            not a positive integer.
    """
    parts = region_str.split(",")
    if len(parts) != 4:
        raise ValueError(
            f"Region string must have exactly 4 comma-separated values "
            f"(left,top,width,height), got {len(parts)}: {region_str!r}"
        )

    try:
        values = [int(p.strip()) for p in parts]
    except ValueError as exc:
        raise ValueError(
            f"Region string must contain only integers, "
            f"got {region_str!r}: {exc}"
        ) from exc

    left, top, width, height = values

    if left < 0 or top < 0:
        raise ValueError(
            f"Region coordinates must be non-negative, "
            f"got left={left}, top={top}"
        )
    if width <= 0 or height <= 0:
        raise ValueError(
            f"Region dimensions must be positive, "
            f"got width={width}, height={height}"
        )

    return (left, top, width, height)
