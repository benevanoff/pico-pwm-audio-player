# USB audio upload

## Build from source

This repository contains the application source and build configuration. Build
outputs, generated files, and the Pico SDK are intentionally excluded from Git.

Install the Raspberry Pi Pico SDK and ARM GCC toolchain using the official Pico
SDK setup instructions, then point CMake at the SDK:

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
cmake -S . -B build
cmake --build build
```

The SDK can also be downloaded automatically by CMake (requires Git and network
access):

```sh
cmake -S . -B build -DPICO_SDK_FETCH_FROM_GIT=ON
cmake --build build
```

The resulting `pwm_audio_player.uf2` is written to `build/`. The same commands
are available through `make` and do not depend on the checkout location:

```sh
make PICO_SDK_PATH=/path/to/pico-sdk
```

The Pico accepts mono 8-bit or 16-bit PCM WAV files over its USB CDC serial
connection. Uploaded audio is converted to unsigned 8-bit PCM and packed into
a shared 1 MiB flash area. The directory supports up to 255 file IDs; the
current demo plays file IDs 1 and 2 from GPIO 0 and GPIO 15 respectively.
Wire each button between its GPIO pin and ground.

## 1602 LCD display

This firmware supports a 1602 LCD with a common PCF8574 I2C backpack. Connect
the backpack to 3.3V, GND, GP4 (SDA), and GP5 (SCL). The firmware uses I2C0 at
100 kHz and the common backpack address `0x27`; change `LCD_I2C_ADDRESS` in
`lcd1602.c` if the backpack is configured differently. The first LCD row shows
the current zero-based `cur_file_idx` value, for example `FILE 0`.

The I2C setup follows the Raspberry Pi Pico SDK `hardware_i2c` API:
[Pico C SDK hardware I2C documentation](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_i2c).
GP4 and GP5 are the I2C0 SDA/SCL GPIO functions listed in the
[RP2040 datasheet GPIO function table](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf).

Install the desktop dependency once:

```sh
python3 -m pip install pyserial PySide6
```

The Qt audio manager provides a device picker, an advanced baud-rate option,
the current flash listing and storage usage, and indexed uploads. Select multiple WAV files to
write them into consecutive 1-based Pico slots starting at the chosen slot;
writing an occupied slot replaces that slot's directory entry and consumes
additional flash space just like the command-line uploader.

Launch it with:

```sh
python3 scripts/audio_manager.py
```

The original command-line tools remain available for scripted use.

The storage display reports firmware size, page-aligned audio allocation,
decoded audio payload, and free space in the reserved 1 MiB audio region.
The first 4 KiB of that region stores the audio directory, so usable audio
capacity is 1,044,480 bytes; firmware storage is outside this reserved region.
Reflash the firmware after updating it so the GUI's `S` storage query is
available.

Build and flash the firmware, then upload a clip:

```sh
python3 scripts/upload_audio.py /dev/ttyACM0 1 audio/clip-one.wav
python3 scripts/upload_audio.py /dev/ttyACM0 42 audio/clip-two.wav
python3 scripts/list_audio.py /dev/ttyACM0
```

Replace `/dev/ttyACM0` with the serial device assigned by the operating system.
Each upload replaces only the selected file ID. Replacements append their new
payload, so repeated replacements reserve additional space. Once the shared
area is full, erase it by reflashing before uploading more clips.
The listing command reports the number of valid audio clips and the sample
payload size used by each clip.
