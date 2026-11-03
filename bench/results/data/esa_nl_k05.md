Validation (2006-10-01 to 2007-01-01, 3 events): F0.5 per rule q=1.0: 0.909, Kraft b+26 bits (no training): 0.909; chosen: Kraft b+26 bits (no training)

| Rule | Muted channels | Detections | TP | FP | FN | Corrected precision | Recall | **Corrected event-wise F0.5** | Alarming precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q=1.0 | 0 | 36 | 23 | 4 | 42 | 0.852 | 0.354 | **0.665** | 0.742 |
| Kraft b+26 bits (no training) (chosen on validation) | 0 | 23 | 18 | 0 | 47 | 1.000 | 0.277 | **0.657** | 0.818 |

ESA-ADB's own metric code, rule chosen on validation (Kraft b+26 bits (no training)), 65 test events:

| Metric | Value |
|---|---:|
| ESA alarming_precision | 1.000 |
| ESA EW_precision | 1.000 |
| ESA EW_recall | 0.277 |
| ESA EW_F_0.50 | 0.657 |
| ESA AFF_precision | 0.642 |
| ESA AFF_recall | 0.281 |
| ESA AFF_F_0.50 | 0.511 |
| ChannelAware channel_precision | 0.277 |
| ChannelAware channel_recall | 0.108 |
| ChannelAware channel_F0.50 | 0.199 |
| ChannelAware subsystem_precision | 0.277 |
| ChannelAware subsystem_recall | 0.277 |
| ChannelAware subsystem_F0.50 | 0.277 |
| ADTQC Nb_Before | 0 |
| ADTQC Nb_After | 18 |
| ADTQC AfterRate | 1.000 |
| ADTQC Total | 0.999 |
