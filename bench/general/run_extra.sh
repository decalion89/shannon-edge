#!/bin/bash
# Extra measurements, one core, nice 10:
#  1. MetroPT codebook variant + its full benchmark (run_all.sh)
#  2. build2 (scratch copy with one coder across all packets, NOT the repo)
#     and stream_measure on every dataset -> results/<name>.stream.log
# Usage: bash run_extra.sh GENERAL_DIR
set -euo pipefail
G=$1
nice -n 10 python3 -I $G/scripts/conv_metropt_codes.py $G/data/metropt.bin $G/data/metropt_codes.bin
bash $G/scripts/run_all.sh $G metropt_codes
(cd $G/build2 && nice -n 10 cargo build --release -j1 --example stream_measure 2>&1 | tail -1)
for n in power_uci can_aegis ecg_incart metropt metropt_codes ais_tracks ais_feed; do
  L=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['record_len'])" $G/data/$n.json)
  nice -n 10 $G/build2/target/release/examples/stream_measure $G/data/$n.bin $L 2>&1 | tee $G/results/$n.stream.log
done
