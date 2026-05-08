# DSP Native Library Makefile
# Supports Linux x86_64 and ARM/Termux builds

CC = gcc
CFLAGS = -O3 -fPIC -Wall -Wextra -shared
LDFLAGS = -lm

# Detect architecture
UNAME_M := $(shell uname -m)

ifeq ($(UNAME_M),aarch64)
    CFLAGS += -march=armv8-a -D__ARM_NEON
endif

ifeq ($(UNAME_M),armv7l)
    CFLAGS += -march=armv7-a -mfpu=neon -D__ARM_NEON
endif

# Target library
TARGET = libdsp_native.so

# Source files
SRCS = dsp_core.c
OBJS = $(SRCS:.c=.o)

.PHONY: all clean install

all: $(TARGET)

$(TARGET): $(SRCS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(OBJS)

install: $(TARGET)
	cp $(TARGET) ../repair/repair_v2_2/

# Debug build
debug: CFLAGS = -g -O0 -fPIC -Wall -Wextra -shared
debug: $(TARGET)
