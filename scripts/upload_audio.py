#!/usr/bin/env python3
import argparse
import struct
import sys
import time
import wave


HEADER = struct.Struct("<4sIII")
MAX_SAMPLES = (1800 * 1024) - 4096


def checksum(data):
    value = 0xffffffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xedb88320 & -(value & 1))
    return value


def read_wav(path):
    with wave.open(path, "rb") as wav_file:
        if wav_file.getnchannels() != 1:
            raise ValueError("Only mono WAV files are supported")
        if wav_file.getsampwidth() not in (1, 2):
            raise ValueError("Only 8-bit and 16-bit PCM WAV files are supported")

        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        raw = wav_file.readframes(wav_file.getnframes())

    if sample_width == 1:
        return sample_rate, raw

    samples = bytearray()
    for (sample,) in struct.iter_unpack("<h", raw):
        samples.append(max(0, min(255, int(sample / 32768.0 * 127.0) + 128)))
    return sample_rate, bytes(samples)


def wait_for_ready(serial_port):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        line = serial_port.readline().decode("ascii", errors="replace").strip()
        if line:
            print(f"Pico: {line}")
        if line == "READY":
            return
    raise TimeoutError("Timed out waiting for READY from the Pico")


def main():
    parser = argparse.ArgumentParser(description="Upload a mono WAV clip to Pico flash")
    parser.add_argument("port", help="USB serial device, for example /dev/ttyACM0")
    parser.add_argument("file_id", type=int, choices=range(1, 256), help="audio file ID: 1 to 255")
    parser.add_argument("wav_file")
    args = parser.parse_args()

    try:
        import serial
    except ImportError:
        raise SystemExit("This tool requires pyserial. Install it with: python3 -m pip install pyserial")

    sample_rate, samples = read_wav(args.wav_file)
    if not samples or len(samples) > MAX_SAMPLES:
        raise ValueError(f"Audio must contain 1 to {MAX_SAMPLES} samples")

    with serial.Serial(args.port, 115200, timeout=0.25, write_timeout=10) as serial_port:
        wait_for_ready(serial_port)
        serial_port.write(bytes((args.file_id,)))
        header = HEADER.pack(b"AUD1", sample_rate, len(samples), checksum(samples))
        serial_port.write(header)
        for offset in range(0, len(samples), 256):
            serial_port.write(samples[offset:offset + 256])
        serial_port.flush()

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            line = serial_port.readline().decode("ascii", errors="replace").strip()
            if line:
                print(f"Pico: {line}")
            if line == "UPLOAD_OK":
                print(f"Uploaded {len(samples)} samples at {sample_rate} Hz")
                return
            if line.startswith("UPLOAD_ERR"):
                raise RuntimeError(line)
        raise TimeoutError("Timed out waiting for upload result")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TimeoutError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
