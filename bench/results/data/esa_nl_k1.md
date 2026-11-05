Validation (2006-10-01 to 2007-01-01, 3 events): F0.5 per rule q=1.0: 0.909, Kraft b+26 bits (no training): 0.909; chosen: Kraft b+26 bits (no training)

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=1.0 | 0 | 38 | 26 | 4 | 39 | 0.867 | 0.400 | **0.703** | 0.788 |
| Kraft b+26 bits (no training) (chosen on validation) | 0 | 23 | 19 | 0 | 46 | 1.000 | 0.292 | **0.674** | 0.864 |

ESA-ADB's own metric code, rule chosen on validation (Kraft b+26 bits (no training)), 65 test events:

| Metric | Value |
|---|---:|
| ESA alarming_precision | 0.950 |
| ESA EW_precision | 1.000 |
| ESA EW_recall | 0.292 |
| ESA EW_F_0.50 | 0.674 |
| ESA AFF_precision | 0.650 |
| ESA AFF_recall | 0.297 |
| ESA AFF_F_0.50 | 0.525 |
| ChannelAware channel_precision | 0.292 |
| ChannelAware channel_recall | 0.095 |
| ChannelAware channel_F0.50 | 0.192 |
| ChannelAware subsystem_precision | 0.292 |
| ChannelAware subsystem_recall | 0.292 |
| ChannelAware subsystem_F0.50 | 0.292 |
| ADTQC Nb_Before | 0 |
| ADTQC Nb_After | 19 |
| ADTQC AfterRate | 1.000 |
| ADTQC Total | 0.947 |
