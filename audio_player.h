#ifndef AUDIO_PLAYER_H
#define AUDIO_PLAYER_H

#include <stddef.h>
#include <stdint.h>

void audio_play_wav(uint32_t pin, const uint8_t *samples, size_t sample_count, uint32_t sample_rate_hz);

#endif
