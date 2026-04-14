"""Unit tests for Transcriber class."""
import tempfile
import numpy as np
from pathlib import Path
from transcriptions import Transcriber


def test_transcriber_init():
    t = Transcriber()
    assert t.output_file == "transcription.txt"
    assert t.sample_rate == 16000
    assert t.transcript_context == ""


def test_transcriber_custom_init():
    t = Transcriber(output_file="custom.txt", sample_rate=8000)
    assert t.output_file == "custom.txt"
    assert t.sample_rate == 8000


def test_passes_energy_gate():
    t = Transcriber()
    # silence
    silent = np.zeros(1000, dtype=np.int16)
    assert not t.passes_energy_gate(silent, threshold=100)
    
    # loud noise
    loud = np.full(1000, 1000, dtype=np.int16)
    assert t.passes_energy_gate(loud, threshold=100)
    
    # threshold disabled
    assert t.passes_energy_gate(silent, threshold=0)


def test_is_hallucination():
    t = Transcriber()
    # short text
    assert not t.is_hallucination("hello world")
    
    # repeated 4-gram
    text = "the cat sat the cat sat the cat sat the cat sat"
    assert t.is_hallucination(text)
    
    # normal text
    normal = "the quick brown fox jumps over the lazy dog"
    assert not t.is_hallucination(normal)


def test_push_context():
    t = Transcriber()
    t.push_context("hello")
    assert "hello" in t.transcript_context
    
    t.push_context("world")
    assert "hello world" in t.transcript_context


def test_write_line():
    t = Transcriber()
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        temp_file = Path(f.name)
    
    t.output_file = str(temp_file)
    t.write_line("test transcript")
    
    content = temp_file.read_text()
    assert "test transcript" in content
    
    temp_file.unlink()


if __name__ == "__main__":
    test_transcriber_init()
    test_transcriber_custom_init()
    test_passes_energy_gate()
    test_is_hallucination()
    test_push_context()
    test_write_line()
    print("All tests passed!")
