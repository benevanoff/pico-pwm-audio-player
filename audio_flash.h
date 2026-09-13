#ifndef AUDIO_FLASH_H
#define AUDIO_FLASH_H

#include <stdbool.h>
#include <stdint.h>

#include "hardware/flash.h"

#define AUDIO_FLASH_MAX_FILES 255u
#define AUDIO_FLASH_SIZE (1800u * 1024u)
#define AUDIO_FLASH_DIRECTORY_SIZE FLASH_SECTOR_SIZE
#define AUDIO_FLASH_DATA_OFFSET AUDIO_FLASH_DIRECTORY_SIZE
#define AUDIO_FLASH_MAX_SAMPLES (AUDIO_FLASH_SIZE - AUDIO_FLASH_DATA_OFFSET)
#define AUDIO_UPLOAD_HEADER_SIZE 16u
#define AUDIO_DIRECTORY_VERSION 1u

typedef struct {
    uint8_t magic[4];
    uint32_t sample_rate_hz;
    uint32_t sample_count;
    uint32_t checksum;
} audio_flash_header_t;

_Static_assert(sizeof(audio_flash_header_t) == AUDIO_UPLOAD_HEADER_SIZE, "Unexpected audio header size");

typedef struct {
    uint32_t offset;
    uint32_t sample_count;
    uint32_t sample_rate_hz;
    uint32_t checksum;
} audio_flash_entry_t;

typedef struct {
    uint8_t magic[4];
    uint32_t version;
    uint32_t count;
    uint32_t next_free_offset;
    audio_flash_entry_t entries[AUDIO_FLASH_MAX_FILES];
} audio_flash_directory_t;

_Static_assert(sizeof(audio_flash_directory_t) == FLASH_SECTOR_SIZE, "Directory must fit in one flash sector");

bool audio_flash_entry_is_valid(const audio_flash_entry_t *entry);
bool audio_flash_get_directory(audio_flash_directory_t *directory);
void audio_flash_store_directory(const audio_flash_directory_t *directory);
void audio_flash_write_page(uint32_t data_offset, const uint8_t *page);
uint32_t audio_flash_file_count(const audio_flash_directory_t *directory);
const uint8_t *audio_flash_data(const audio_flash_entry_t *entry);
uint32_t audio_checksum_update(uint32_t checksum, uint8_t value);

#endif
