/**
 * Copyright (c) 2020 Raspberry Pi (Trading) Ltd.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

#include <stdio.h>
#include <string.h>

#include "audio_flash.h"
#include "audio_player.h"
#include "lcd1602.h"
#include "pico/stdlib.h"

#define PWM_PIN 12u
#define BUTTON_1_PIN 0u
#define BUTTON_LEFT_PIN 15u
#define BUTTON_RIGHT_PIN 16u

extern char __flash_binary_end;

static int read_usb_byte(uint timeout_us) {
    return getchar_timeout_us(timeout_us);
}

static void list_audio_flash(void) {
    audio_flash_directory_t directory;
    audio_flash_get_directory(&directory);
    uint count = 0;
    uint32_t total_size = 0;

    for (uint file_id = 0; file_id < AUDIO_FLASH_MAX_FILES; ++file_id) {
        const audio_flash_entry_t *entry = &directory.entries[file_id];
        if (!audio_flash_entry_is_valid(entry)) {
            continue;
        }

         uint32_t storage_size = (entry->sample_count + FLASH_PAGE_SIZE - 1u) &
                        ~(FLASH_PAGE_SIZE - 1u);
         printf("AUDIO %u SIZE %lu RATE %lu STORAGE %lu\n", file_id + 1u,
               (unsigned long)entry->sample_count,
             (unsigned long)entry->sample_rate_hz,
             (unsigned long)storage_size);
        ++count;
         total_size += entry->sample_count;
    }

    printf("AUDIO_LIST %u %lu\n", count, (unsigned long)total_size);
}

static void list_flash_stats(void) {
    audio_flash_directory_t directory;
    audio_flash_get_directory(&directory);
    uint32_t audio_payload = 0;

    for (uint file_id = 0; file_id < AUDIO_FLASH_MAX_FILES; ++file_id) {
        const audio_flash_entry_t *entry = &directory.entries[file_id];
        if (audio_flash_entry_is_valid(entry)) {
            audio_payload += entry->sample_count;
        }
    }

    uint32_t program_size = (uint32_t)((uintptr_t)&__flash_binary_end - XIP_BASE);
    uint32_t audio_used = directory.next_free_offset - AUDIO_FLASH_DATA_OFFSET;
    uint32_t audio_free = AUDIO_FLASH_SIZE - directory.next_free_offset;
    printf("FLASH_STATS %lu %lu %lu %lu %lu\n", (unsigned long)program_size,
           (unsigned long)audio_used, (unsigned long)audio_payload,
           (unsigned long)audio_free, (unsigned long)AUDIO_FLASH_SIZE);
}

static bool receive_audio_command(void) {
    int file_byte = read_usb_byte(100000);
    if (file_byte == PICO_ERROR_TIMEOUT) {
        return false;
    }
    if (file_byte == 'L') {
        list_audio_flash();
        return true;
    }
    if (file_byte == 'S') {
        list_flash_stats();
        return true;
    }
    if (file_byte < 1 || file_byte > AUDIO_FLASH_MAX_FILES) {
        puts("UPLOAD_ERR file");
        return true;
    }

    uint file_id = (uint)file_byte - 1u;
    uint8_t header_bytes[AUDIO_UPLOAD_HEADER_SIZE];
    for (uint i = 0; i < AUDIO_UPLOAD_HEADER_SIZE; ++i) {
        int value = read_usb_byte(5000000);
        if (value == PICO_ERROR_TIMEOUT) {
            puts("UPLOAD_ERR timeout");
            return true;
        }
        header_bytes[i] = (uint8_t)value;
    }

    audio_flash_header_t header;
    memcpy(&header, header_bytes, sizeof(header));
    if (header.magic[0] != 'A' || header.magic[1] != 'U' ||
        header.magic[2] != 'D' || header.magic[3] != '1' ||
        header.sample_rate_hz == 0 || header.sample_count == 0 ||
        header.sample_count > AUDIO_FLASH_MAX_SAMPLES) {
        puts("UPLOAD_ERR header");
        return true;
    }

    uint32_t checksum = 0xffffffffu;
    audio_flash_directory_t directory;
    audio_flash_get_directory(&directory);
    uint32_t data_offset = directory.next_free_offset;
    uint32_t data_end = data_offset + ((header.sample_count + FLASH_PAGE_SIZE - 1u) & ~(FLASH_PAGE_SIZE - 1u));
    if (data_end > AUDIO_FLASH_SIZE) {
        puts("UPLOAD_ERR full");
        return true;
    }

    directory.next_free_offset = data_end;
    audio_flash_store_directory(&directory);

    uint8_t page[FLASH_PAGE_SIZE];
    uint32_t remaining = header.sample_count;
    uint32_t page_offset = data_offset;

    while (remaining > 0) {
        uint32_t page_size = remaining < FLASH_PAGE_SIZE ? remaining : FLASH_PAGE_SIZE;
        memset(page, 0xff, sizeof(page));
        for (uint32_t i = 0; i < page_size; ++i) {
            int value = read_usb_byte(5000000);
            if (value == PICO_ERROR_TIMEOUT) {
                puts("UPLOAD_ERR timeout");
                return true;
            }
            page[i] = (uint8_t)value;
            checksum = audio_checksum_update(checksum, page[i]);
        }

        audio_flash_write_page(page_offset, page);
        page_offset += FLASH_PAGE_SIZE;
        remaining -= page_size;
    }

    if (checksum != header.checksum) {
        puts("UPLOAD_ERR checksum");
        return true;
    }

    audio_flash_entry_t *entry = &directory.entries[file_id];
    bool was_valid = audio_flash_entry_is_valid(entry);
    entry->offset = data_offset;
    entry->sample_count = header.sample_count;
    entry->sample_rate_hz = header.sample_rate_hz;
    entry->checksum = header.checksum;
    if (!was_valid) {
        ++directory.count;
    }
    audio_flash_store_directory(&directory);
    puts("UPLOAD_OK");
    return true;
}

static int wait_for_button(void) {
    uint status_counter = 0;

    while (true) {
        if (!gpio_get(BUTTON_1_PIN)) {
            sleep_ms(20);
            if (!gpio_get(BUTTON_1_PIN)) {
                puts("BUTTON 1");
                return 0;
            }
        }
        if (!gpio_get(BUTTON_LEFT_PIN)) {
            sleep_ms(20);
            if (!gpio_get(BUTTON_LEFT_PIN)) {
                puts("BUTTON 2");
                return 1;
            }
        }
        if (!gpio_get(BUTTON_RIGHT_PIN)) {
            sleep_ms(20);
            if (!gpio_get(BUTTON_RIGHT_PIN)) {
                puts("BUTTON 3");
                return 2;
            }
        }

        if (++status_counter >= 10) {
            puts("READY");
            status_counter = 0;
        }

        return -1;
    }
}

int main() {
    stdio_init_all();
    lcd1602_init();
    lcd1602_show_files(false, 0, 0);
    gpio_init(BUTTON_1_PIN);
    gpio_set_dir(BUTTON_1_PIN, GPIO_IN);
    gpio_pull_up(BUTTON_1_PIN);
    gpio_init(BUTTON_LEFT_PIN);
    gpio_set_dir(BUTTON_LEFT_PIN, GPIO_IN);
    gpio_pull_up(BUTTON_LEFT_PIN);
    gpio_init(BUTTON_RIGHT_PIN);
    gpio_set_dir(BUTTON_RIGHT_PIN, GPIO_IN);
    gpio_pull_up(BUTTON_RIGHT_PIN);

    uint8_t cur_file_idx = 0;
    uint8_t queued_file_idx = 0;
    bool has_playing_file = false;
    while (true) {
        puts("READY");

        // try recv audio files over usb
        if (receive_audio_command())
            continue;

        int button = wait_for_button();
        if (button < 0) {
            continue;
        }

        audio_flash_directory_t directory;
        audio_flash_get_directory(&directory);
        uint file_count = audio_flash_file_count(&directory);
        if (file_count == 0) {
            puts("NO AUDIO FOUND");
            lcd1602_show_files(false, 0, 0);
            continue;
        }

        queued_file_idx %= file_count;
        if (button == 1) {
            queued_file_idx = (uint8_t)((queued_file_idx + file_count - 1u) % file_count);
            lcd1602_show_files(has_playing_file, cur_file_idx, queued_file_idx);
            continue;
        }
        if (button == 2) {
            queued_file_idx = (uint8_t)((queued_file_idx + 1u) % file_count);
            lcd1602_show_files(has_playing_file, cur_file_idx, queued_file_idx);
            continue;
        }

        const uint8_t *samples = NULL;
        size_t sample_count = 0;
        uint32_t sample_rate_hz = 0;
        uint file_index = queued_file_idx;
        const audio_flash_entry_t *entry = NULL;
        for (uint file_id = 0; file_id < AUDIO_FLASH_MAX_FILES; ++file_id) {
            if (!audio_flash_entry_is_valid(&directory.entries[file_id])) {
                continue;
            }
            if (file_index == 0) {
                entry = &directory.entries[file_id];
                break;
            }
            --file_index;
        }

        if (entry) {
            samples = audio_flash_data(entry);
            sample_count = entry->sample_count;
            sample_rate_hz = entry->sample_rate_hz;
        }

        if (!samples || sample_count == 0 || sample_rate_hz == 0) {
            puts("NO AUDIO FOUND");
            continue;
        }

         cur_file_idx = queued_file_idx;
        has_playing_file = true;
         lcd1602_show_files(true, cur_file_idx, queued_file_idx);
        printf("PLAYING %lu samples at %lu Hz\n", (unsigned long)sample_count,
               (unsigned long)sample_rate_hz);
        audio_play_wav(PWM_PIN, samples, sample_count, sample_rate_hz);
    }

    return 0;
}