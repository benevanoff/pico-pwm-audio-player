#include "lcd1602.h"

#include <stdio.h>

#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "pico/stdlib.h"

#define LCD_I2C i2c0
#define LCD_SDA_PIN 4u
#define LCD_SCL_PIN 5u
#define LCD_I2C_ADDRESS 0x27u
#define LCD_I2C_BAUDRATE 100000u

#define LCD_RS 0x01u
#define LCD_EN 0x04u
#define LCD_BACKLIGHT 0x08u

static void lcd1602_write_nibble(uint8_t nibble, bool register_select) {
    uint8_t value = (uint8_t)((nibble & 0xf0u) | LCD_BACKLIGHT);
    if (register_select) {
        value |= LCD_RS;
    }

    uint8_t bytes[] = { (uint8_t)(value | LCD_EN), value };
    i2c_write_blocking(LCD_I2C, LCD_I2C_ADDRESS, bytes, sizeof(bytes), false);
}

static void lcd1602_write_byte(uint8_t value, bool register_select) {
    lcd1602_write_nibble(value, register_select);
    lcd1602_write_nibble((uint8_t)(value << 4), register_select);
}

static void lcd1602_command(uint8_t command) {
    lcd1602_write_byte(command, false);
    if (command == 0x01u || command == 0x02u) {
        sleep_ms(2);
    }
}

static void lcd1602_write_line(const char *text) {
    uint length = 0;
    while (*text != '\0') {
        lcd1602_write_byte((uint8_t)*text++, true);
        ++length;
    }
    while (length++ < 16) {
        lcd1602_write_byte(' ', true);
    }
}

static void lcd1602_set_cursor(uint8_t row) {
    lcd1602_command((uint8_t)(0x80u | (row == 0 ? 0x00u : 0x40u)));
}

void lcd1602_init(void) {
    i2c_init(LCD_I2C, LCD_I2C_BAUDRATE);
    gpio_set_function(LCD_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(LCD_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(LCD_SDA_PIN);
    gpio_pull_up(LCD_SCL_PIN);

    sleep_ms(50);
    lcd1602_write_nibble(0x30u, false);
    sleep_ms(5);
    lcd1602_write_nibble(0x30u, false);
    sleep_us(150);
    lcd1602_write_nibble(0x30u, false);
    lcd1602_write_nibble(0x20u, false);

    lcd1602_command(0x28u);
    lcd1602_command(0x0cu);
    lcd1602_command(0x06u);
    lcd1602_command(0x01u);
}

void lcd1602_show_files(bool has_playing_file, uint8_t playing_file_index,
                        uint8_t queued_file_index) {
    char playing_line[17];
    char queued_line[17];

    if (has_playing_file) {
        snprintf(playing_line, sizeof(playing_line), "PLAY %u",
                 (unsigned)playing_file_index);
    } else {
        snprintf(playing_line, sizeof(playing_line), "PLAY --");
    }
    snprintf(queued_line, sizeof(queued_line), "QUEUE %u",
             (unsigned)queued_file_index);

    lcd1602_command(0x01u);
    lcd1602_set_cursor(0);
    lcd1602_write_line(playing_line);
    lcd1602_set_cursor(1);
    lcd1602_write_line(queued_line);
}