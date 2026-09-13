#include "audio_flash.h"

#include <string.h>

#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"

#define AUDIO_FLASH_OFFSET (PICO_FLASH_SIZE_BYTES - AUDIO_FLASH_SIZE)

static const audio_flash_directory_t *audio_flash_directory_in_flash(void) {
    return (const audio_flash_directory_t *)(XIP_BASE + AUDIO_FLASH_OFFSET);
}

static bool audio_flash_directory_is_valid(const audio_flash_directory_t *directory) {
    if (directory->magic[0] != 'A' || directory->magic[1] != 'U' ||
        directory->magic[2] != 'D' || directory->magic[3] != '2' ||
        directory->version != AUDIO_DIRECTORY_VERSION ||
        directory->count > AUDIO_FLASH_MAX_FILES ||
        directory->next_free_offset < AUDIO_FLASH_DATA_OFFSET ||
        directory->next_free_offset > AUDIO_FLASH_SIZE) {
        return false;
    }

    return audio_flash_file_count(directory) == directory->count;
}

bool audio_flash_entry_is_valid(const audio_flash_entry_t *entry) {
    return entry->sample_rate_hz > 0 && entry->sample_count > 0 &&
           entry->offset >= AUDIO_FLASH_DATA_OFFSET &&
           entry->offset + entry->sample_count <= AUDIO_FLASH_SIZE;
}

uint32_t audio_flash_file_count(const audio_flash_directory_t *directory) {
    uint32_t count = 0;
    for (uint32_t file_id = 0; file_id < AUDIO_FLASH_MAX_FILES; ++file_id) {
        if (audio_flash_entry_is_valid(&directory->entries[file_id])) {
            ++count;
        }
    }
    return count;
}

bool audio_flash_get_directory(audio_flash_directory_t *directory) {
    memcpy(directory, audio_flash_directory_in_flash(), sizeof(*directory));
    if (audio_flash_directory_is_valid(directory)) {
        return true;
    }

    memset(directory, 0, sizeof(*directory));
    memcpy(directory->magic, "AUD2", 4);
    directory->version = AUDIO_DIRECTORY_VERSION;
    directory->next_free_offset = AUDIO_FLASH_DATA_OFFSET;
    return false;
}

void audio_flash_store_directory(const audio_flash_directory_t *directory) {
    uint8_t page[FLASH_PAGE_SIZE];

    uint32_t interrupts = save_and_disable_interrupts();
    flash_range_erase(AUDIO_FLASH_OFFSET, AUDIO_FLASH_DIRECTORY_SIZE);
    for (uint32_t offset = 0; offset < sizeof(*directory); offset += FLASH_PAGE_SIZE) {
        memset(page, 0x00, sizeof(page));
        memcpy(page, (const uint8_t *)directory + offset, FLASH_PAGE_SIZE);
        flash_range_program(AUDIO_FLASH_OFFSET + offset, page, FLASH_PAGE_SIZE);
    }
    restore_interrupts(interrupts);
}

void audio_flash_write_page(uint32_t data_offset, const uint8_t *page) {
    uint32_t interrupts = save_and_disable_interrupts();
    flash_range_program(AUDIO_FLASH_OFFSET + data_offset, page, FLASH_PAGE_SIZE);
    restore_interrupts(interrupts);
}

const uint8_t *audio_flash_data(const audio_flash_entry_t *entry) {
    return (const uint8_t *)(XIP_BASE + AUDIO_FLASH_OFFSET + entry->offset);
}

uint32_t audio_checksum_update(uint32_t checksum, uint8_t value) {
    checksum ^= value;
    for (uint32_t i = 0; i < 8; ++i) {
        checksum = (checksum >> 1) ^ (0xedb88320u & (-(checksum & 1u)));
    }
    return checksum;
}
