Validation (2006-10-01 to 2007-01-01, 3 events): F0.5 per rule q=1.0: 0.909, Kraft b+26 bits (no training): 0.714; chosen: q=1.0

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=1.0 (chosen on validation) | 0 | 26 | 20 | 0 | 45 | 1.000 | 0.308 | **0.690** | 0.800 |
| Kraft b+26 bits (no training) | 0 | 21 | 21 | 0 | 44 | 1.000 | 0.323 | **0.705** | 1.000 |

ESA-ADB's own metric code, rule chosen on validation (q=1.0), 65 test events:

| Metric | Value |
|---|---:|
| ESA alarming_precision | 0.833 |
| ESA EW_precision | 1.000 |
| ESA EW_recall | 0.308 |
| ESA EW_F_0.50 | 0.690 |
| ESA AFF_precision | 0.650 |
| ESA AFF_recall | 0.297 |
| ESA AFF_F_0.50 | 0.525 |
| ChannelAware channel_precision | 0.308 |
| ChannelAware channel_recall | 0.103 |
| ChannelAware channel_F0.50 | 0.205 |
| ChannelAware subsystem_precision | 0.308 |
| ChannelAware subsystem_recall | 0.308 |
| ChannelAware subsystem_F0.50 | 0.308 |
| ADTQC Nb_Before | 0 |
| ADTQC Nb_After | 20 |
| ADTQC AfterRate | 1.000 |
| ADTQC Total | 0.949 |
