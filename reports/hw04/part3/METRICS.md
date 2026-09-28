# HW4 Part 3 measured results

Run: `20260928T003859.945761Z-cd277c20`  
Measured revision: `9860a20342072168ed68a8d41eb16d9bfecf7729`; dirty: `false`.  
Selected requests: **180** (30 per endpoint and page size).

Percentiles: R7 linear interpolation: rank=(n-1)*p, interpolate adjacent sorted values. All latencies are end-to-end HTTP milliseconds.

| Page size | Version | Requests | Total SQL/request (min–max) | Data SQL/request (min–max) | p50 ms | p95 ms | p99 ms |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | naive | 30 | 13–13 | 11–11 | 11.514 | 21.160 | 23.194 |
| 10 | fixed | 30 | 3–3 | 1–1 | 7.557 | 12.575 | 85.671 |
| 50 | naive | 30 | 53–53 | 51–51 | 26.380 | 42.758 | 53.385 |
| 50 | fixed | 30 | 3–3 | 1–1 | 8.630 | 12.088 | 15.529 |
| 200 | naive | 30 | 203–203 | 201–201 | 74.496 | 175.151 | 205.407 |
| 200 | fixed | 30 | 3–3 | 1–1 | 14.202 | 25.722 | 29.632 |

SQL counts come from response instrumentation, including authentication and session activity in the total. The JSON summary preserves every observed counter value and frequency.

| Page size | p50 speed-up | p95 speed-up | p99 speed-up |
| ---: | ---: | ---: | ---: |
| 10 | 1.524× | 1.683× | 0.271× |
| 50 | 3.057× | 3.537× | 3.438× |
| 200 | 5.245× | 6.809× | 6.932× |

Each speed-up divides the naive percentile by the corresponding fixed percentile. Values above 1 mean the fixed version was faster; values below 1 mean it was slower. These are ratios of percentiles, not percentiles of paired ratios.

With only 30 requests in each group, p95 and p99 depend strongly on the slowest observations. These observations do not establish performance outside this recorded environment.
