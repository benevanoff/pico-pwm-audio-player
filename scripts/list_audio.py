#!/usr/bin/env python3
import argparse
import sys
import time


FLASH_PAGE_SIZE = 256


def format_duration(samples, sample_rate):
    total_seconds = samples // sample_rate
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


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
    parser = argparse.ArgumentParser(description="List audio clips stored in Pico flash")
    parser.add_argument("port", help="USB serial device, for example /dev/ttyACM0")
    args = parser.parse_args()

    try:
        import serial
    except ImportError:
        raise SystemExit("This tool requires pyserial. Install it with: python3 -m pip install pyserial")

    with serial.Serial(args.port, 115200, timeout=0.25, write_timeout=10) as serial_port:
        wait_for_ready(serial_port)
        serial_port.write(b"L")
        serial_port.flush()

        deadline = time.monotonic() + 5
        audio_count = None
        total_size = None
        while time.monotonic() < deadline:
            line = serial_port.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            if line.startswith("AUDIO "):
                fields = line.split()
                if (len(fields) not in (6, 8) or fields[0] != "AUDIO" or
                        fields[2] != "SIZE" or fields[4] != "RATE"):
                    raise RuntimeError(f"Unexpected response: {line}")
                samples = int(fields[3])
                storage_bytes = (
                    int(fields[7]) if len(fields) == 8 and fields[6] == "STORAGE"
                    else (samples + FLASH_PAGE_SIZE - 1) // FLASH_PAGE_SIZE * FLASH_PAGE_SIZE
                )
                storage_kb = storage_bytes / 1024
                print(f"Slot {fields[1]}: {fields[3]} samples at {fields[5]} Hz, "
                        f"{format_duration(samples, int(fields[5]))}, {storage_kb:.2f} KB")
            elif line.startswith("AUDIO_LIST "):
                fields = line.split()
                if len(fields) != 3:
                    raise RuntimeError(f"Unexpected response: {line}")
                audio_count = int(fields[1])
                total_size = int(fields[2])
                break

        if audio_count is None:
            raise TimeoutError("Timed out waiting for flash listing")
        print(f"Total: {audio_count} audio file(s), {total_size} bytes")


if __name__ == "__main__":
    try:
        main()
    except (OSError, TimeoutError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)