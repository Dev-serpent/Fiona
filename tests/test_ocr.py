"""Tests for SeeOnDesk/ocr.py — OCR engine."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import SeeOnDesk.ocr as ocr_module
from SeeOnDesk.ocr import (
    OcrResult,
    list_supported_languages,
    parse_region_string,
    read_image,
    read_image_pil,
    read_screen_region,
    read_window_region,
    tesseract_available,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_OCR_RESULT = OcrResult(
    text="Hello world",
    confidence=92.5,
    boxes=[{"x": 10, "y": 5, "w": 80, "h": 20, "text": "Hello", "conf": 92.5}],
    language="eng",
    error=None,
)

FAKE_EMPTY_RESULT = OcrResult(text="", confidence=0.0, boxes=[], language="eng", error="OCR failed")


def _reset_cache() -> None:
    ocr_module._TESSERACT_AVAILABLE = None


# ---------------------------------------------------------------------------
# OcrResult tests
# ---------------------------------------------------------------------------


class OcrResultTests(unittest.TestCase):
    def test_success_true_when_no_error(self) -> None:
        r = OcrResult(text="hello", confidence=95.0, boxes=[], language="eng", error=None)
        self.assertTrue(r.success)

    def test_success_false_when_error(self) -> None:
        r = OcrResult(
            text="", confidence=0.0, boxes=[], language="eng", error="tesseract not found"
        )
        self.assertFalse(r.success)

    def test_default_confidence_zero(self) -> None:
        r = OcrResult(text="", boxes=[], language="eng")
        self.assertEqual(r.confidence, 0.0)
        self.assertIsNone(r.error)


# ---------------------------------------------------------------------------
# tesseract_available tests
# ---------------------------------------------------------------------------


class TesseractAvailableTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def test_available_when_binary_and_pytesseract_work(self) -> None:
        with (
            patch("SeeOnDesk.ocr.shutil.which", return_value="/usr/bin/tesseract"),
            patch("pytesseract.get_tesseract_version", return_value="5.5.2"),
        ):
            self.assertTrue(tesseract_available())

    def test_not_available_when_no_binary(self) -> None:
        with patch("SeeOnDesk.ocr.shutil.which", return_value=None):
            self.assertFalse(tesseract_available())

    def test_not_available_when_pytesseract_import_fails(self) -> None:
        # Simulate ImportError by making pytesseract not importable
        import builtins

        real_import = builtins.__import__

        def broken_import(name, *args, **kwargs):
            if name == "pytesseract":
                raise ImportError("no pytesseract")
            return real_import(name, *args, **kwargs)

        with (
            patch("SeeOnDesk.ocr.shutil.which", return_value="/usr/bin/tesseract"),
            patch("builtins.__import__", side_effect=broken_import),
        ):
            self.assertFalse(tesseract_available())

    def test_cache_used_on_second_call(self) -> None:
        with (
            patch("SeeOnDesk.ocr.shutil.which", return_value="/usr/bin/tesseract") as mock_which,
            patch("pytesseract.get_tesseract_version", return_value="5.5.2"),
        ):
            tesseract_available()  # first call — populates cache
            mock_which.reset_mock()
            tesseract_available()  # second call — uses cache
            mock_which.assert_not_called()

    def test_cache_respects_false(self) -> None:
        ocr_module._TESSERACT_AVAILABLE = False
        self.assertFalse(tesseract_available())

    def test_cache_respects_true(self) -> None:
        ocr_module._TESSERACT_AVAILABLE = True
        self.assertTrue(tesseract_available())

    def tearDown(self) -> None:
        _reset_cache()


# ---------------------------------------------------------------------------
# list_supported_languages tests
# ---------------------------------------------------------------------------


class ListSupportedLanguagesTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_cache()

    def test_returns_languages_when_available(self) -> None:
        with (
            patch("SeeOnDesk.ocr.tesseract_available", return_value=True),
            patch("pytesseract.get_languages", return_value=["eng", "osd"]),
        ):
            self.assertEqual(list_supported_languages(), ["eng", "osd"])

    def test_returns_empty_when_not_available(self) -> None:
        with patch("SeeOnDesk.ocr.tesseract_available", return_value=False):
            self.assertEqual(list_supported_languages(), [])

    def test_returns_empty_on_exception(self) -> None:
        with (
            patch("SeeOnDesk.ocr.tesseract_available", return_value=True),
            patch("pytesseract.get_languages", side_effect=RuntimeError("broken")),
        ):
            self.assertEqual(list_supported_languages(), [])

    def tearDown(self) -> None:
        _reset_cache()


# ---------------------------------------------------------------------------
# parse_region_string tests
# ---------------------------------------------------------------------------


class ParseRegionStringTests(unittest.TestCase):
    def test_valid_format(self) -> None:
        self.assertEqual(parse_region_string("100,200,300,400"), (100, 200, 300, 400))

    def test_valid_with_spaces(self) -> None:
        self.assertEqual(parse_region_string(" 10, 20, 30, 40 "), (10, 20, 30, 40))

    def test_invalid_format_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_region_string("abc,def,ghi,jkl")

    def test_too_few_values_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_region_string("100,200,300")

    def test_too_many_values_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_region_string("1,2,3,4,5")

    def test_negative_coordinates_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_region_string("-1,0,100,100")

    def test_zero_or_negative_dimensions_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_region_string("0,0,0,100")
        with self.assertRaises(ValueError):
            parse_region_string("0,0,100,-1")

    def test_empty_string_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_region_string("")


# ---------------------------------------------------------------------------
# read_image_pil tests
# ---------------------------------------------------------------------------


class ReadImagePilTests(unittest.TestCase):
    def test_returns_text_and_boxes_on_success(self) -> None:
        with patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT):
            from PIL import Image

            img = Image.new("RGB", (100, 30), "white")
            result = read_image_pil(img)

        self.assertTrue(result.success)
        self.assertEqual(result.text, "Hello world")
        self.assertEqual(len(result.boxes), 1)

    def test_returns_error_result(self) -> None:
        with patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_EMPTY_RESULT):
            from PIL import Image

            img = Image.new("RGB", (100, 30), "white")
            result = read_image_pil(img)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_converts_non_rgb_image(self) -> None:
        with patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT) as mock_run:
            from PIL import Image

            img = Image.new("RGBA", (100, 30), (255, 0, 0, 128))
            result = read_image_pil(img)

        self.assertTrue(result.success)
        call_img = mock_run.call_args[0][0]
        self.assertEqual(call_img.mode, "RGB")

    def test_with_lang_and_psm_parameters(self) -> None:
        with patch("SeeOnDesk.ocr._run_pytesseract") as mock_run:
            mock_run.return_value = FAKE_OCR_RESULT
            from PIL import Image

            img = Image.new("RGB", (100, 30), "white")
            result = read_image_pil(img, lang="fra", psm=6)

        self.assertTrue(result.success)
        _, kwargs = mock_run.call_args
        self.assertEqual(kwargs.get("lang"), "fra")
        self.assertEqual(kwargs.get("psm"), 6)


# ---------------------------------------------------------------------------
# read_image tests
# ---------------------------------------------------------------------------


class ReadImageTests(unittest.TestCase):
    def test_reads_from_file_path(self) -> None:
        with patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT):
            import tempfile
            from PIL import Image

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            Image.new("RGB", (100, 30), "white").save(tmp.name)
            tmp.close()
            try:
                result = read_image(tmp.name)
            finally:
                Path(tmp.name).unlink()

        self.assertTrue(result.success)
        self.assertEqual(result.text, "Hello world")

    def test_returns_error_for_nonexistent_file(self) -> None:
        result = read_image("/nonexistent/image.png")
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_returns_error_on_ocr_failure(self) -> None:
        with patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_EMPTY_RESULT):
            import tempfile
            from PIL import Image

            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            Image.new("RGB", (100, 30), "white").save(tmp.name)
            tmp.close()
            try:
                result = read_image(tmp.name)
            finally:
                Path(tmp.name).unlink()

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)


# ---------------------------------------------------------------------------
# read_screen_region tests
# ---------------------------------------------------------------------------


def _fake_capture_screen(path: str | Path) -> bool:
    """Write a minimal valid PNG as a fake screenshot."""
    from PIL import Image

    img = Image.new("RGB", (200, 100), "white")
    img.save(str(path))
    return True


class ReadScreenRegionTests(unittest.TestCase):
    def test_captures_screen_and_ocrs(self) -> None:
        with (
            patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT),
            patch("SeeOnDesk.vision.capture_screen", side_effect=_fake_capture_screen) as mock_cap,
        ):
            result = read_screen_region()

        self.assertTrue(result.success)
        mock_cap.assert_called_once()

    def test_returns_error_on_capture_failure(self) -> None:
        with patch("SeeOnDesk.vision.capture_screen", return_value=False):
            result = read_screen_region()

        self.assertFalse(result.success)
        self.assertIn("Failed to capture", result.error or "")

    def test_crops_to_region(self) -> None:
        with (
            patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT),
            patch("SeeOnDesk.vision.capture_screen", side_effect=_fake_capture_screen),
        ):
            result = read_screen_region(region=(10, 20, 100, 50))

        self.assertTrue(result.success)

    def test_saves_debug_output(self) -> None:
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            with (
                patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT),
                patch("SeeOnDesk.vision.capture_screen", side_effect=_fake_capture_screen),
            ):
                result = read_screen_region(output_path=tmp.name)

            self.assertTrue(result.success)
            self.assertTrue(Path(tmp.name).exists())
        finally:
            if Path(tmp.name).exists():
                Path(tmp.name).unlink()


# ---------------------------------------------------------------------------
# read_window_region tests
# ---------------------------------------------------------------------------


def _fake_capture_window(window_id: str, path: str | Path) -> bool:
    """Write a minimal valid PNG as a fake window capture."""
    from PIL import Image

    img = Image.new("RGB", (200, 100), "white")
    img.save(str(path))
    return True


class ReadWindowRegionTests(unittest.TestCase):
    def test_captures_window_and_ocrs(self) -> None:
        with (
            patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT),
            patch("SeeOnDesk.vision.capture_window", side_effect=_fake_capture_window) as mock_cap,
        ):
            result = read_window_region(window_id="abc123")

        self.assertTrue(result.success)
        mock_cap.assert_called_once()

    def test_returns_error_on_capture_failure(self) -> None:
        with patch("SeeOnDesk.vision.capture_window", return_value=False):
            result = read_window_region(window_id="abc123")

        self.assertFalse(result.success)
        self.assertIn("Failed to capture", result.error or "")

    def test_crops_to_region(self) -> None:
        with (
            patch("SeeOnDesk.ocr._run_pytesseract", return_value=FAKE_OCR_RESULT),
            patch("SeeOnDesk.vision.capture_window", side_effect=_fake_capture_window),
        ):
            result = read_window_region(window_id="abc123", region=(10, 20, 100, 50))

        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
