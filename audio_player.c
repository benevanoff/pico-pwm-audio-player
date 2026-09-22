#include "audio_player.h"

#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "pico/stdlib.h"

#define PWM_WRAP 255u

void audio_play_wav(
    uint32_t pin,
    const uint8_t *samples,
    size_t sample_count,
    uint32_t sample_rate_hz
) {
    uint slice = pwm_gpio_to_slice_num(pin);

    gpio_set_function(pin, GPIO_FUNC_PWM);

    pwm_config config = pwm_get_default_config();

    // 8-bit PWM
    pwm_config_set_wrap(&config, PWM_WRAP);

    // Run PWM carrier at the highest practical frequency.
    // At 125 MHz:
    //
    // 125 MHz / 256 = ~488 kHz
    //
    pwm_config_set_clkdiv(&config, 1.0f);

    pwm_init(slice, &config, true);

    absolute_time_t start = get_absolute_time();

    for (size_t i = 0; i < sample_count; ++i) {
        pwm_set_gpio_level(pin, samples[i]);

        // Calculate timing from the original start time instead
        // of repeatedly sleeping an integer number of microseconds.
        uint64_t target_us =
            ((uint64_t)(i + 1) * 1000000ULL) / sample_rate_hz;

        sleep_until(delayed_by_us(start, target_us));
    }

    pwm_set_gpio_level(pin, 128);
    sleep_ms(1);

    pwm_set_enabled(slice, false);
}