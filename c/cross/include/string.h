/* Stand-in <string.h> for freestanding cross builds that have no C library
 * (make cross): the three standard functions the codec uses, implemented in
 * cross/start.c. A real toolchain's <string.h> (newlib, picolibc, ...)
 * replaces it. */
#ifndef SEDGE_CROSS_STRING_H
#define SEDGE_CROSS_STRING_H
#include <stddef.h>
void *memcpy(void *dst, const void *src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);
#endif
