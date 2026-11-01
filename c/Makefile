# sedge_fast: portable C99 fast packet profile.
#
#   make test        golden streams (bit-exact with Rust) + unit tests, then
#                    the same under -fsanitize=address,undefined
#   make warnings    -Werror builds with gcc and clang
#   make cross       golden test on 32-bit / big-endian CPUs under qemu-user
#                    (needs clang, ld.lld, qemu-riscv32/arm/i386/mips/ppc)
#   make size        object size at -Os for several targets
#   make bench DATA=packets.bin LEN=90
#   make crosscheck  build the Rust-vs-C payload comparator (see README.md)
#
# Builds go to $(BUILD). Variables: CC, SAN_CC (sanitizer compiler,
# default $(CC)), BUILD.

CC      ?= cc
SAN_CC  ?= $(CC)
BUILD   ?= build
STD      = -std=c99
WARN     = -Wall -Wextra -Wpedantic -Wconversion -Wshadow
CFLAGS  ?= -O2
ALL_CFLAGS = $(STD) $(WARN) $(CFLAGS)
SAN      = -g -O1 -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer

LIB = sedge_fast.c sedge_fast.h

.PHONY: all test warnings cross size bench crosscheck clean

all: $(BUILD)/test_golden $(BUILD)/test_fast $(BUILD)/bench $(BUILD)/crosscheck

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/sedge_fast.o: $(LIB) | $(BUILD)
	$(CC) $(ALL_CFLAGS) -c sedge_fast.c -o $@

$(BUILD)/test_golden: test_golden.c test_gen.h $(LIB) | $(BUILD)
	$(CC) $(ALL_CFLAGS) sedge_fast.c test_golden.c -o $@

$(BUILD)/test_fast: test_fast.c test_gen.h $(LIB) | $(BUILD)
	$(CC) $(ALL_CFLAGS) -DSEDGE_FAST_TEST_HOOKS sedge_fast.c test_fast.c -o $@

$(BUILD)/test_golden_san: test_golden.c test_gen.h $(LIB) | $(BUILD)
	$(SAN_CC) $(STD) $(WARN) $(SAN) sedge_fast.c test_golden.c -o $@

$(BUILD)/test_fast_san: test_fast.c test_gen.h $(LIB) | $(BUILD)
	$(SAN_CC) $(STD) $(WARN) $(SAN) -DSEDGE_FAST_TEST_HOOKS sedge_fast.c test_fast.c -o $@

$(BUILD)/bench: bench.c $(LIB) | $(BUILD)
	$(CC) $(ALL_CFLAGS) sedge_fast.c bench.c -o $@

$(BUILD)/crosscheck: crosscheck.c $(LIB) | $(BUILD)
	$(CC) $(ALL_CFLAGS) -DSEDGE_FAST_TEST_HOOKS sedge_fast.c crosscheck.c -o $@

test: $(BUILD)/test_golden $(BUILD)/test_fast $(BUILD)/test_golden_san $(BUILD)/test_fast_san
	$(BUILD)/test_golden
	$(BUILD)/test_fast
	@echo "--- under AddressSanitizer + UndefinedBehaviorSanitizer:"
	$(BUILD)/test_golden_san
	$(BUILD)/test_fast_san

crosscheck: $(BUILD)/crosscheck

bench: $(BUILD)/bench
	@test -n "$(DATA)" || (echo "usage: make bench DATA=packets.bin LEN=90"; exit 2)
	$(BUILD)/bench $(DATA) $(LEN) 3

warnings: | $(BUILD)
	for cc in gcc clang; do \
	  for f in sedge_fast.c test_golden.c test_fast.c bench.c crosscheck.c; do \
	    $$cc $(STD) $(WARN) -Werror -O2 -c $$f -o $(BUILD)/w.o || exit 1; \
	  done; \
	done
	@echo "no warnings (gcc, clang)"

# Freestanding golden test (no C library: cross/start.c) under qemu-user.
RESDIR  = $(shell clang -print-resource-dir 2>/dev/null)
XFLAGS  = $(STD) $(WARN) -Werror -O2 -ffreestanding -fno-builtin -nostdinc \
          -isystem $(RESDIR)/include -Icross/include -DSEDGE_FREESTANDING \
          -fno-pic -fno-stack-protector -fomit-frame-pointer -nostdlib -static \
          -fuse-ld=lld -Wl,--no-dynamic-linker -Wl,-e,_start
XSRC    = sedge_fast.c test_golden.c cross/start.c
XTARGETS = riscv32:qemu-riscv32:--target=riscv32-unknown-linux-gnu,-march=rv32imac,-mabi=ilp32,-mno-relax \
           cortex-m4:qemu-arm:--target=thumbv7em-none-eabi,-mcpu=cortex-m4,-mfloat-abi=soft \
           i386:qemu-i386:--target=i386-unknown-linux-gnu \
           mips-be:qemu-mips:--target=mips-unknown-linux-gnu,-mno-abicalls,-G0 \
           mipsel:qemu-mipsel:--target=mipsel-unknown-linux-gnu,-mno-abicalls,-G0 \
           ppc32-be:qemu-ppc:--target=powerpc-unknown-linux-gnu

cross: $(XSRC) $(LIB) cross/include/string.h | $(BUILD)
	@for t in $(XTARGETS); do \
	  name=$${t%%:*}; rest=$${t#*:}; qemu=$${rest%%:*}; flags=$$(echo $${rest#*:} | tr , ' '); \
	  echo "== $$name ($$qemu)"; \
	  clang $$flags $(XFLAGS) $(XSRC) -o $(BUILD)/golden-$$name || exit 1; \
	  $$qemu $(BUILD)/golden-$$name || exit 1; \
	done

# Code size of the codec object at -Os (text + data + bss, bytes).
SFLAGS  = $(STD) $(WARN) -Os -fno-asynchronous-unwind-tables -fno-stack-protector
FREE    = -ffreestanding -nostdinc -isystem $(RESDIR)/include -Icross/include
STARGETS = x86-64-$(CC):$(CC) \
           rv32imc:clang,--target=riscv32-unknown-elf,-march=rv32imc,-mabi=ilp32,FREE \
           cortex-m4:clang,--target=thumbv7em-none-eabi,-mcpu=cortex-m4,FREE \
           cortex-m0:clang,--target=thumbv6m-none-eabi,-mcpu=cortex-m0,FREE \
           msp430:clang,--target=msp430-unknown-elf,FREE

size: $(LIB) | $(BUILD)
	@printf "%-16s %10s %16s\n" target bytes "-DSEDGE_FAST_NO_LEARN"
	@for t in $(STARGETS); do \
	  name=$${t%%:*}; cmd=$$(echo $${t#*:} | tr , ' ' | sed 's|FREE|$(FREE)|'); \
	  $$cmd $(SFLAGS) -c sedge_fast.c -o $(BUILD)/s1.o || exit 1; \
	  $$cmd $(SFLAGS) -DSEDGE_FAST_NO_LEARN -c sedge_fast.c -o $(BUILD)/s2.o || exit 1; \
	  printf "%-16s %10s %16s\n" $$name \
	    $$(llvm-size $(BUILD)/s1.o | awk 'NR==2{print $$1+$$2+$$3}') \
	    $$(llvm-size $(BUILD)/s2.o | awk 'NR==2{print $$1+$$2+$$3}'); \
	done

clean:
	rm -rf $(BUILD)
