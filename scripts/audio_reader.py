#!/usr/bin/env python3
"""Unified audio file decoder for WAV and MP3 files.

All audio files are decoded to unsigned 8-bit PCM mono samples at their
native sample rate, matching the format the Pico firmware expects.
"""

import struct
import wave
from pathlib import Path

try:
    import miniaudio
except ImportError as error:  # pragma: no cover
    raise SystemExit(
        "This tool requires miniaudio: python3 -m pip install miniaudio"
    ) from error


def _convert_float_to_8bit_unsigned(value: float) -> int:
    """Convert a float32 PCM sample (range -1.0 to 1.0) to unsigned 8-bit."""
    clamped = max(-1.0, min(1.0, value))
    return max(0, min(255, int(clamped * 127.0) + 128))


def _read_wav(path: str) -> tuple[int, bytes]:
    """Read a mono WAV file and return (sample_rate, unsigned 8-bit PCM)."""
    with wave.open(path, "rb") as wav_file:
        if wav_file.getnchannels() != 1:
            raise ValueError(f"{Path(path).name}: only mono WAV files are supported")
        if wav_file.getsampwidth() not in (1, 2):
            raise ValueError(
                f"{Path(path).name}: only 8-bit and 16-bit PCM WAV files are supported"
            )
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        raw = wav_file.readframes(wav_file.getnframes())

    if sample_width == 1:
        samples = raw
    else:
        samples = bytearray()
        for (sample,) in struct.iter_unpack("<h", raw):
            samples.append(max(0, min(255, int(sample / 32768.0 * 127.0) + 128)))

    return sample_rate, bytes(samples)


def _read_mp3(path: str) -> tuple[int, bytes]:
    """Read an MP3 file and return (sample_rate, unsigned 8-bit PCM).

    The MP3 is decoded to 32-bit float PCM at its native sample rate, then
    downmixed to mono (if stereo) and converted to unsigned 8-bit PCM.
    """
    try:
        sound = miniaudio.mp3_read_file_f32(path)
    except Exception as error:
        raise ValueError(
            f"{Path(path).name}: failed to decode MP3 file: {error}"
        ) from error

    sample_rate = sound.sample_rate
    nchannels = sound.nchannels
    num_frames = sound.num_frames
    float_samples = sound.samples  # array.array('f')

    result = bytearray()
    if nchannels == 1:
        for value in float_samples:
            result.append(_convert_float_to_8bit_unsigned(value))
    else:
        for i in range(num_frames):
            left = float_samples[i * nchannels]
            right = float_samples[i * nchannels + 1]
            result.append(_convert_float_to_8bit_unsigned((left + right) / 2.0))

    return sample_rate, bytes(result)


def read_audio(path: str) -> tuple[int, bytes]:
    """Read a WAV or MP3 file and return (sample_rate, unsigned 8-bit PCM).

    The file type is determined by the extension.  Both formats are decoded
    to unsigned 8-bit mono PCM at the file's native sample rate.
    """
    ext = Path(path).suffix.lower()
    if ext == ".wav":
        return _read_wav(path)
    if ext == ".mp3":
        return _read_mp3(path)
    raise ValueError(
        f"{Path(path).name}: unsupported file extension '{ext}', "
        "only .wav and .mp3 are supported"
    )
