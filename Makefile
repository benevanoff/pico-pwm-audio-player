BUILD_DIR ?= build
CMAKE ?= cmake

CMAKE_ARGS := -S . -B $(BUILD_DIR)
ifneq ($(strip $(PICO_SDK_PATH)),)
CMAKE_ARGS += -DPICO_SDK_PATH=$(PICO_SDK_PATH)
else
CMAKE_ARGS += -DPICO_SDK_FETCH_FROM_GIT=ON
endif

.PHONY: all configure clean

all: configure
	$(CMAKE) --build $(BUILD_DIR)

configure:
	$(CMAKE) $(CMAKE_ARGS)

clean:
	$(CMAKE) -E rm -rf $(BUILD_DIR)