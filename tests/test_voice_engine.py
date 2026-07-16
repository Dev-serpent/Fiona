"""Tests for FionaCore.voice_engine — Whisper-based voice transcription.

All heavy dependencies (faster-whisper, sounddevice, numpy) are mocked.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock heavy voice deps before importing voice_engine
# IMPORTANT: Save and restore real modules to prevent cross-test corruption.
_saved_modules = {}

class _MockNDArray:
    """Mock numpy array that supports .tobytes() for wave writing."""
    def tobytes(self):
        return b"mock audio bytes"

mock_numpy = MagicMock()
mock_numpy.ndarray = _MockNDArray
mock_numpy.int16 = MagicMock()
_saved_modules["numpy"] = sys.modules.get("numpy")
sys.modules["numpy"] = mock_numpy

mock_sd = MagicMock()
_saved_modules["sounddevice"] = sys.modules.get("sounddevice")
sys.modules["sounddevice"] = mock_sd

mock_faster_whisper = MagicMock()
_saved_modules["faster_whisper"] = sys.modules.get("faster_whisper")
sys.modules["faster_whisper"] = mock_faster_whisper
_saved_modules["faster_whisper.WhisperModel"] = sys.modules.get("faster_whisper.WhisperModel")
sys.modules["faster_whisper.WhisperModel"] = MagicMock()

# Avoid triggering actual imports that check deps
import importlib
import FionaCore.voice_engine
importlib.reload(FionaCore.voice_engine)

from FionaCore.voice_engine import WhisperEngine, quick_transcribe

# ---------------------------------------------------------------------------
# Restore original modules IMMEDIATELY so other tests in the same process
# are not affected by the mocks.
# ---------------------------------------------------------------------------
for _name, _mod in _saved_modules.items():
    if _mod is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _mod
del _name, _mod, _saved_modules


class WhisperEngineInitTests(unittest.TestCase):
    def test_default_model_size(self):
        engine = WhisperEngine()
        self.assertEqual(engine.model_size, "tiny")

    def test_default_device(self):
        engine = WhisperEngine()
        self.assertEqual(engine.device, "cpu")

    def test_default_compute_type(self):
        engine = WhisperEngine()
        self.assertEqual(engine.compute_type, "int8")

    def test_default_cpu_threads(self):
        engine = WhisperEngine()
        self.assertEqual(engine.cpu_threads, 4)

    def test_initial_model_is_none(self):
        engine = WhisperEngine()
        self.assertIsNone(engine._model)


class WhisperEngineEnsureModelTests(unittest.TestCase):
    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", True)
    @patch("FionaCore.voice_engine.WhisperModel")
    def test_ensure_model_creates_model(self, mock_whisper_model):
        engine = WhisperEngine()
        model = engine._ensure_model()
        self.assertIsNotNone(model)
        mock_whisper_model.assert_called_once_with(
            "tiny", device="cpu", compute_type="int8", cpu_threads=4
        )

    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", True)
    @patch("FionaCore.voice_engine.WhisperModel")
    def test_ensure_model_caches_model(self, mock_whisper_model):
        engine = WhisperEngine()
        model1 = engine._ensure_model()
        model2 = engine._ensure_model()
        self.assertIs(model1, model2)
        mock_whisper_model.assert_called_once()

    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", False)
    def test_ensure_model_raises_without_deps(self):
        engine = WhisperEngine()
        with self.assertRaises(RuntimeError) as ctx:
            engine._ensure_model()
        self.assertIn("not installed", str(ctx.exception))


class WhisperEngineTranscribeTests(unittest.TestCase):
    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", True)
    @patch("FionaCore.voice_engine.WhisperModel")
    def test_transcribe_audio_buffer(self, mock_whisper_model):
        mock_model = MagicMock()
        mock_whisper_model.return_value = mock_model

        mock_segment = MagicMock()
        mock_segment.text = "hello world"
        mock_model.transcribe.return_value = ([mock_segment], None)

        engine = WhisperEngine()
        result = engine.transcribe_audio_buffer(_MockNDArray(), sample_rate=16000)

        self.assertEqual(result, "hello world")
        mock_model.transcribe.assert_called_once()

    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", True)
    @patch("FionaCore.voice_engine.WhisperModel")
    def test_transcribe_audio_buffer_multiple_segments(self, mock_whisper_model):
        mock_model = MagicMock()
        mock_whisper_model.return_value = mock_model

        seg1 = MagicMock()
        seg1.text = "first"
        seg2 = MagicMock()
        seg2.text = "second"
        mock_model.transcribe.return_value = ([seg1, seg2], None)

        engine = WhisperEngine()
        result = engine.transcribe_audio_buffer(_MockNDArray())
        self.assertEqual(result, "first second")

    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", True)
    @patch("FionaCore.voice_engine.WhisperModel")
    def test_transcribe_empty_result(self, mock_whisper_model):
        mock_model = MagicMock()
        mock_whisper_model.return_value = mock_model
        mock_model.transcribe.return_value = ([], None)

        engine = WhisperEngine()
        result = engine.transcribe_audio_buffer(_MockNDArray())
        self.assertEqual(result, "")


class WhisperEngineListenAndTranscribeTests(unittest.TestCase):
    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", True)
    @patch("FionaCore.voice_engine.WhisperModel")
    @patch("FionaCore.voice_engine.sd")
    def test_listen_and_transcribe(self, mock_sd, mock_whisper_model):
        mock_model = MagicMock()
        mock_whisper_model.return_value = mock_model
        mock_segment = MagicMock()
        mock_segment.text = "test transcription"
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_sd.rec.return_value = _MockNDArray()

        engine = WhisperEngine()
        result = engine.listen_and_transcribe(duration_seconds=2.0)

        self.assertEqual(result, "test transcription")
        mock_sd.rec.assert_called_once()
        mock_sd.wait.assert_called_once()

    @patch("FionaCore.voice_engine.HAS_VOICE_DEPS", False)
    def test_listen_and_transcribe_raises_without_deps(self):
        engine = WhisperEngine()
        with self.assertRaises(RuntimeError) as ctx:
            engine.listen_and_transcribe()
        self.assertIn("not installed", str(ctx.exception))


class QuickTranscribeTests(unittest.TestCase):
    @patch("FionaCore.voice_engine.WhisperEngine")
    def test_quick_transcribe_calls_listen(self, mock_engine_cls):
        mock_instance = MagicMock()
        mock_instance.listen_and_transcribe.return_value = "quick result"
        mock_engine_cls.return_value = mock_instance

        result = quick_transcribe(phrase_seconds=3.0)
        self.assertEqual(result, "quick result")
        mock_instance.listen_and_transcribe.assert_called_once_with(duration_seconds=3.0)

    @patch("FionaCore.voice_engine.WhisperEngine")
    def test_quick_transcribe_default_seconds(self, mock_engine_cls):
        mock_instance = MagicMock()
        mock_instance.listen_and_transcribe.return_value = ""
        mock_engine_cls.return_value = mock_instance

        quick_transcribe()
        mock_instance.listen_and_transcribe.assert_called_once_with(duration_seconds=3.0)


if __name__ == "__main__":
    unittest.main()
