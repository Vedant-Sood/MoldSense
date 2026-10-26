# BME688 dataset deviation report

- Dataset 1 original rows: 2743
- Dataset 1 matched rows: 216
- Dataset 2 rows: 216
- Matching method: first contiguous Dataset 1 rows, preserving acquisition order
- Gas-profile deviation rate: **33.14%**

The gas-profile rate is the mean symmetric percentage difference between the median gas resistance at each of the 10 heater steps. It measures separation, not proof of mold.

## Environmental comparison

| Signal | Dataset 1 median | Dataset 2 median | Difference (2-1) | Symmetric deviation |
|---|---:|---:|---:|---:|
| Temperature | 35.4159 | 35.9529 | 0.5370 | 1.50% |
| Humidity | 54.0955 | 53.0902 | -1.0052 | 1.88% |
| Pressure | 1003.8492 | 1008.5824 | 4.7332 | 0.47% |

## Gas profile by heater step

| Heater step | Rows D1 | Rows D2 | D1 median ohms | D2 median ohms | Deviation |
|---:|---:|---:|---:|---:|---:|
| 0 | 22 | 22 | 131350.105 | 166938.375 | 23.86% |
| 1 | 21 | 21 | 11690332.000 | 17799022.000 | 41.43% |
| 2 | 20 | 21 | 11193524.000 | 17035612.000 | 41.39% |
| 3 | 22 | 21 | 10277117.000 | 15803231.000 | 42.38% |
| 4 | 22 | 22 | 847352.281 | 1195743.562 | 34.10% |
| 5 | 22 | 22 | 812795.250 | 1166619.250 | 35.75% |
| 6 | 22 | 21 | 787259.344 | 1135569.750 | 36.23% |
| 7 | 22 | 22 | 114018.496 | 148233.938 | 26.09% |
| 8 | 21 | 22 | 120244.250 | 155457.750 | 25.54% |
| 9 | 22 | 22 | 126201.902 | 161641.703 | 24.62% |
