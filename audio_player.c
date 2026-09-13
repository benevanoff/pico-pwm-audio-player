#include "audio_player.h"

#include "hardware/clocks.h"
#include "hardware/pwm.h"
#include "pico/stdlib.h"

#define PWM_WRAP 255u

void audio_play_wav(uint32_t pin, const uint8_t *samples, size_t sample_count, uint32_t sample_rate_hz) {
    uint slice = pwm_gpio_to_slice_num(pin);
    float clk_hz = (float)clock_get_hz(clk_sys);
    float clkdiv = clk_hz / ((float)sample_rate_hz * (PWM_WRAP + 1.0f));

    gpio_set_function(pin, GPIO_FUNC_PWM);

    pwm_config config = pwm_get_default_config();
    pwm_config_set_wrap(&config, PWM_WRAP);
    pwm_config_set_clkdiv(&config, clkdiv);
    pwm_init(slice, &config, true);

    for (size_t i = 0; i < sample_count; ++i) {
        pwm_set_gpio_level(pin, samples[i]);
        sleep_us(1000000u / sample_rate_hz);
    }

    pwm_set_enabled(slice, false);
}
