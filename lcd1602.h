#ifndef LCD1602_H
#define LCD1602_H

#include <stdbool.h>
#include <stdint.h>

void lcd1602_init(void);
void lcd1602_show_files(bool has_playing_file, uint8_t playing_file_index,
						uint8_t queued_file_index);

#endif