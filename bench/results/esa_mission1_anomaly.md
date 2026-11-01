# ESA Anomaly Dataset, Mission 1: anomaly detection from the flight codec's surprise

Data: ESA-AD Mission 1, CC BY 3.0 IGO, doi:10.5281/zenodo.12528696. Produced by `python3 bench/anomaly.py ESA-Mission1.zip` (all 58 target channels, full history). An event is one labelled (anomaly ID, channel) interval; detected if any of its samples exceeds the threshold. Thresholds: the 99.9% / 99.99% quantile of each detector's score on nominal samples (outside labels, after a 1% warm-up), i.e. calibrated with the labels to compare detectors at equal false-alarm rates. This is not ESA-ADB's official event-wise metric.

| Channel | Samples | Events | surprise 0.1% | z-score 0.1% | jump 0.1% | surprise 0.01% | z-score 0.01% | jump 0.01% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| channel_12 | 14,258,506 | 38 | 23 | 11 | 6 | 15 | 7 | 5 |
| channel_13 | 14,258,506 | 39 | 25 | 12 | 10 | 12 | 5 | 4 |
| channel_14 | 5,272,893 | 95 | 65 | 44 | 27 | 46 | 19 | 5 |
| channel_15 | 5,272,893 | 51 | 41 | 29 | 21 | 33 | 5 | 5 |
| channel_16 | 5,272,893 | 37 | 25 | 20 | 14 | 15 | 11 | 1 |
| channel_17 | 14,258,506 | 40 | 23 | 12 | 13 | 9 | 8 | 7 |
| channel_18 | 14,258,506 | 40 | 25 | 10 | 10 | 9 | 6 | 3 |
| channel_19 | 14,258,506 | 40 | 25 | 10 | 11 | 16 | 9 | 3 |
| channel_20 | 14,258,506 | 40 | 25 | 14 | 8 | 14 | 7 | 4 |
| channel_21 | 5,272,893 | 95 | 59 | 41 | 28 | 39 | 17 | 8 |
| channel_22 | 5,272,893 | 55 | 43 | 39 | 26 | 34 | 24 | 13 |
| channel_23 | 5,272,893 | 51 | 41 | 33 | 32 | 33 | 13 | 10 |
| channel_24 | 5,272,893 | 38 | 25 | 24 | 14 | 18 | 7 | 5 |
| channel_25 | 14,258,506 | 40 | 25 | 13 | 8 | 12 | 9 | 5 |
| channel_26 | 14,258,506 | 41 | 20 | 14 | 6 | 12 | 6 | 2 |
| channel_27 | 14,258,506 | 41 | 25 | 9 | 9 | 16 | 3 | 4 |
| channel_28 | 14,258,506 | 40 | 25 | 9 | 14 | 13 | 7 | 7 |
| channel_29 | 5,272,893 | 94 | 67 | 38 | 23 | 43 | 7 | 7 |
| channel_30 | 5,272,893 | 48 | 36 | 32 | 22 | 25 | 13 | 12 |
| channel_31 | 5,272,893 | 54 | 40 | 38 | 27 | 33 | 22 | 5 |
| channel_32 | 5,272,893 | 40 | 25 | 22 | 18 | 18 | 10 | 3 |
| channel_33 | 5,272,893 | 39 | 26 | 23 | 18 | 18 | 11 | 9 |
| channel_34 | 14,258,506 | 40 | 26 | 15 | 17 | 15 | 8 | 8 |
| channel_35 | 14,258,506 | 39 | 19 | 12 | 9 | 11 | 6 | 5 |
| channel_36 | 14,258,506 | 40 | 22 | 10 | 9 | 11 | 3 | 3 |
| channel_37 | 14,258,506 | 40 | 24 | 15 | 8 | 11 | 4 | 2 |
| channel_38 | 5,272,893 | 49 | 34 | 32 | 17 | 23 | 10 | 7 |
| channel_39 | 5,272,893 | 54 | 40 | 39 | 28 | 34 | 24 | 11 |
| channel_40 | 5,272,893 | 38 | 24 | 24 | 16 | 17 | 16 | 6 |
| channel_41 | 15,381,169 | 210 | 148 | 122 | 92 | 112 | 73 | 75 |
| channel_42 | 15,381,169 | 209 | 102 | 96 | 86 | 77 | 63 | 74 |
| channel_43 | 15,381,169 | 207 | 134 | 119 | 96 | 105 | 86 | 74 |
| channel_44 | 15,381,169 | 208 | 106 | 106 | 92 | 76 | 66 | 74 |
| channel_45 | 15,381,169 | 206 | 136 | 114 | 95 | 94 | 73 | 75 |
| channel_46 | 15,381,169 | 201 | 108 | 93 | 87 | 78 | 62 | 66 |
| channel_47 | 14,644,745 | 85 | 53 | 41 | 23 | 45 | 18 | 10 |
| channel_48 | 14,644,745 | 86 | 56 | 40 | 27 | 43 | 13 | 9 |
| channel_49 | 14,644,745 | 83 | 56 | 42 | 28 | 41 | 25 | 15 |
| channel_50 | 4,974,682 | 80 | 50 | 33 | 17 | 35 | 6 | 8 |
| channel_51 | 4,974,682 | 81 | 44 | 29 | 25 | 30 | 10 | 7 |
| channel_52 | 4,974,682 | 82 | 46 | 28 | 22 | 36 | 15 | 10 |
| channel_57 | 14,639,410 | 32 | 22 | 23 | 21 | 17 | 7 | 11 |
| channel_58 | 14,639,410 | 32 | 21 | 20 | 9 | 18 | 5 | 7 |
| channel_59 | 14,639,410 | 32 | 21 | 20 | 14 | 17 | 7 | 7 |
| channel_60 | 14,639,410 | 31 | 21 | 17 | 10 | 17 | 4 | 6 |
| channel_61 | 487,448 | 4 | 4 | 0 | 2 | 4 | 0 | 2 |
| channel_62 | 487,448 | 4 | 4 | 2 | 4 | 4 | 2 | 4 |
| channel_63 | 487,448 | 4 | 4 | 2 | 4 | 4 | 2 | 4 |
| channel_64 | 4,810,995 | 7 | 6 | 3 | 6 | 6 | 3 | 6 |
| channel_65 | 4,810,995 | 8 | 6 | 2 | 6 | 6 | 2 | 6 |
| channel_66 | 4,810,995 | 15 | 12 | 8 | 5 | 6 | 1 | 5 |
| channel_70 | 14,670,328 | 27 | 10 | 8 | 7 | 5 | 6 | 4 |
| channel_71 | 14,666,814 | 26 | 9 | 9 | 8 | 6 | 4 | 5 |
| channel_72 | 14,668,450 | 28 | 11 | 8 | 9 | 7 | 5 | 6 |
| channel_73 | 14,669,336 | 35 | 17 | 17 | 16 | 9 | 12 | 12 |
| channel_74 | 19,286,353 | 34 | 13 | 18 | 15 | 9 | 13 | 12 |
| channel_75 | 14,667,583 | 34 | 16 | 17 | 17 | 3 | 11 | 12 |
| channel_76 | 14,671,647 | 33 | 14 | 15 | 10 | 12 | 12 | 10 |

| Detector | Events found, 0.1% false alarms | at 0.01% | Channels where best (or tied) at 0.1% |
|---|---:|---:|---:|
| surprise | 2173/3520 | 1527/3520 | 54 |
| z-score | 1696/3520 | 903/3520 | 8 |
| jump | 1322/3520 | 785/3520 | 5 |
