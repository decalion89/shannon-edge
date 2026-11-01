#!/bin/bash
# sedge's general context-mixing model as an archival compressor of the whole
# file: one block (-b 0), one thread, record length given (-r L), verified by
# `sedge bench`. Usage: bash run_cm.sh GENERAL_DIR [name ...]
set -euo pipefail
G=$1; shift
S=$G/build/target/release/sedge
for n in ${*:-power_uci can_aegis metropt_codes ecg_incart metropt ais_tracks ais_feed}; do
  L=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['record_len'])" $G/data/$n.json)
  echo "== $n L=$L" | tee $G/results/$n.cm.log
  nice -n 10 $S bench $G/data/$n.bin -b 0 -t 1 -r $L 2>&1 | tee -a $G/results/$n.cm.log
done
