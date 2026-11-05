/* Minimal no-libc runtime to run test_golden.c under qemu-user on 32-bit
 * and big-endian CPUs (make cross): _start, write/exit system calls, and
 * memcpy/memmove/memset. Test infrastructure only, not part of the codec. */
#include <stddef.h>
#include <stdint.h>

int test_golden_main(void);
void test_write(const char *s);
void _start(void);
void *memcpy(void *dst, const void *src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);

#if defined(__riscv)
#define SYS_WRITE 64
#define SYS_EXIT 93
static long sys3(long n, long a, long b, long c)
{
    register long a7 __asm__("a7") = n;
    register long a0 __asm__("a0") = a;
    register long a1 __asm__("a1") = b;
    register long a2 __asm__("a2") = c;
    __asm__ volatile("ecall" : "+r"(a0) : "r"(a7), "r"(a1), "r"(a2) : "memory");
    return a0;
}
#elif defined(__arm__)
#define SYS_WRITE 4
#define SYS_EXIT 1
static long sys3(long n, long a, long b, long c)
{
    register long r7 __asm__("r7") = n;
    register long r0 __asm__("r0") = a;
    register long r1 __asm__("r1") = b;
    register long r2 __asm__("r2") = c;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r7), "r"(r1), "r"(r2) : "memory");
    return r0;
}
#elif defined(__i386__)
#define SYS_WRITE 4
#define SYS_EXIT 1
static long sys3(long n, long a, long b, long c)
{
    long r;
    __asm__ volatile("int $0x80" : "=a"(r) : "a"(n), "b"(a), "c"(b), "d"(c) : "memory");
    return r;
}
#elif defined(__mips__)
#define SYS_WRITE 4004
#define SYS_EXIT 4001
static long sys3(long n, long a, long b, long c)
{
    register long v0 __asm__("$2") = n;
    register long a0 __asm__("$4") = a;
    register long a1 __asm__("$5") = b;
    register long a2 __asm__("$6") = c;
    register long a3 __asm__("$7");
    __asm__ volatile("syscall"
                     : "+r"(v0), "=r"(a3)
                     : "r"(a0), "r"(a1), "r"(a2)
                     : "$1", "$3", "$8", "$9", "$10", "$11", "$12", "$13", "$14", "$15", "$24",
                       "$25", "hi", "lo", "memory");
    return v0;
}
#elif defined(__powerpc__)
#define SYS_WRITE 4
#define SYS_EXIT 1
static long sys3(long n, long a, long b, long c)
{
    register long r0 __asm__("r0") = n;
    register long r3 __asm__("r3") = a;
    register long r4 __asm__("r4") = b;
    register long r5 __asm__("r5") = c;
    __asm__ volatile("sc"
                     : "+r"(r0), "+r"(r3), "+r"(r4), "+r"(r5)
                     :
                     : "r6", "r7", "r8", "r9", "r10", "r11", "r12", "cr0", "ctr", "xer", "memory");
    return r3;
}
#else
#error "unsupported architecture for the freestanding test runtime"
#endif

void test_write(const char *s)
{
    size_t n = 0;
    while (s[n] != 0) {
        n++;
    }
    (void)sys3(SYS_WRITE, 1, (long)(uintptr_t)s, (long)n);
}

void _start(void)
{
    int r = test_golden_main();
    for (;;) {
        (void)sys3(SYS_EXIT, r, 0, 0);
    }
}

void *memcpy(void *dst, const void *src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    while (n--) {
        *d++ = *s++;
    }
    return dst;
}

void *memmove(void *dst, const void *src, size_t n)
{
    unsigned char *d = dst;
    const unsigned char *s = src;
    if (d < s) {
        while (n--) {
            *d++ = *s++;
        }
    } else {
        while (n--) {
            d[n] = s[n];
        }
    }
    return dst;
}

void *memset(void *dst, int c, size_t n)
{
    unsigned char *d = dst;
    while (n--) {
        *d++ = (unsigned char)c;
    }
    return dst;
}
