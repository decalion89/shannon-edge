# Usage: qemu-riscv64 -d in_asm,exec,nochain -D log.txt PROGRAM ARGS; awk -f qemu_count.awk log.txt
# Prints the number of guest instructions executed and the number of
# executed blocks whose translation was not found (should be 0). Needs no
# QEMU plugin support: it sums, over every executed translation block, the
# number of instructions QEMU listed when translating it.
# Count guest instructions from a QEMU "-d in_asm,exec,nochain" log.
function norm(h) { sub(/^0x/, "", h); sub(/^0+/, "", h); return h }
/^IN:/ { inblk=1; start=""; n=0; next }
inblk && /^0x[0-9a-f]+:/ { a=$1; sub(":","",a); if (start=="") start=norm(a); n++; next }
inblk && /^$/ { if (start!="") size[start]=n; inblk=0; next }
/^Trace / { split($0, f, "/"); pc=norm(f[2]); if (!(pc in size)) miss++; total += size[pc]; tbs++ }
END { printf "%d %d\n", total, miss }
