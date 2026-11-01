#!/bin/bash
# Run sedge (fast profile, fast + ground-learned recipes on held-out 90%,
# v2 2^16 and 2^12) and the general baselines on every dataset, one core at
# a time, nice 10. Logs go to results/<name>.log.
# Usage: bash run_all.sh GENERAL_DIR [name ...]
set -euo pipefail
G=$1; shift
B=$G/build/target/release/examples
names=${*:-"power_uci can_aegis ecg_incart metropt ais_tracks ais_feed"}
mkdir -p $G/results $G/work
for n in $names; do
  f=$G/data/$n.bin
  L=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['record_len'])" $G/data/$n.json)
  log=$G/results/$n.log
  {
    echo "== $n  L=$L  $(date -u +%FT%TZ)"
    echo "-- sedge fast"; nice -n 10 $B/packet_fast_bench $f $L
    echo "-- sedge fast, recipes/classes learned on first 10%, test 90%"; SEDGE_FAST_RECIPES=1 nice -n 10 $B/packet_fast_bench $f $L
    echo "-- sedge v2 2^16"; SEDGE_PACKET_V2=1 nice -n 10 $B/packet_bench $f $L 16
    echo "-- sedge v2 2^12"; SEDGE_PACKET_V2=1 nice -n 10 $B/packet_bench $f $L 12
    echo "-- baselines"; nice -n 10 python3 -I $G/scripts/baselines.py $f $G/work; cp $G/work/$n.baselines.json $G/results/
  } 2>&1 | tee $log
done
