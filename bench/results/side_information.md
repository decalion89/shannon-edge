# Side information the receiver already has: telecommands

Shannon's limit cannot be beaten, but it is a limit *given what the
receiver knows*: the conditional entropy H(X | Y) can be far below H(X).
Lossless compressors of spacecraft telemetry, CCSDS 121/124 and ours,
use only the telemetry's own past. Yet both ends of a link also know the
**telecommands**: the ground sent them and the spacecraft executed them.
If commanded actions (heaters, mode changes, pointing) caused the costly
surprises in telemetry, a compressor that knew the command timeline could
stop paying for them, at no transmission cost. We know of no telemetry
compressor that does this.

## Test (ESA-AD Mission 1, `bench/analysis/cmd_effect.py`)

698 telecommands, 1,588,758 distinct execution times over 14 years. For 8
channels (12, 14, 21, 30, 41, 46, 58, 64; 79 million samples), the flight
profile's per-sample cost in bits (`examples/flight_surprise`), after a
1% warm-up, inside and outside windows following any command execution:

| Window after a command | Share of samples | Share of bits | Bits/sample inside | outside |
|---:|---:|---:|---:|---:|
| 60 s | 1.93% | 1.89% | 2.110 | 2.156 |
| 10 min | 8.48% | 8.34% | 2.120 | 2.158 |
| 1 h | 27.90% | 27.64% | 2.135 | 2.163 |

Per channel the shares agree within a few hundredths of a percentage point
(channel 64, the most affected: 8.56% of samples, 9.19% of bits within
10 min).

## Reading: a negative result

Telemetry is no more surprising after commands than elsewhere on these
channels, so the command timeline, used as "time since the last command",
cannot buy anything here: the upper bound of what it could remove is the
excess cost after commands, and there is none. Commands are frequent (one
every ~5 minutes on average) and mostly routine; their effects are either
too small or already predicted from the telemetry's own past. Not tried:
modelling specific commands against specific channels, which could still
matter for rare mode changes but is bounded by the tiny share of bits
involved.
