Validation (2006-10-01 to 2007-01-01, 3 events): F0.5 per rule q=1.0: 0.909, Kraft b+26 bits (no training): 0.055; chosen: q=1.0

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=1.0 (chosen on validation) | 0 | 28 | 19 | 2 | 46 | 0.905 | 0.292 | **0.638** | 0.760 |
| Kraft b+26 bits (no training) | 0 | 1090 | 40 | 1017 | 25 | 0.038 | 0.615 | **0.047** | 0.615 |

ESA-ADB's own metric code, rule chosen on validation (q=1.0), 65 test events:

| Metric | Value |
|---|---:|
| ESA alarming_precision | 0.905 |
| ESA EW_precision | 0.905 |
| ESA EW_recall | 0.292 |
| ESA EW_F_0.50 | 0.638 |
| ESA AFF_precision | 0.642 |
| ESA AFF_recall | 0.294 |
| ESA AFF_F_0.50 | 0.519 |
| ChannelAware channel_precision | 0.292 |
| ChannelAware channel_recall | 0.077 |
| ChannelAware channel_F0.50 | 0.179 |
| ChannelAware subsystem_precision | 0.292 |
| ChannelAware subsystem_recall | 0.292 |
| ChannelAware subsystem_F0.50 | 0.292 |
| ADTQC Nb_Before | 0 |
| ADTQC Nb_After | 19 |
| ADTQC AfterRate | 1.000 |
| ADTQC Total | 0.893 |
