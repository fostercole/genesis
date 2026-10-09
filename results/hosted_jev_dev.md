# Hosted Jev on the dev BM25 top 50

Same 50-tool candidate lists as the original and tuned 2B.
Those two rows are copied from `results/dev_bm25_top50.json` and were not rescored.
Locked k is 10. Hosted Jev did not move that lock.

| model | nDCG@10 | recall@3 | recall@5 | recall@10 | completeness@3 | completeness@5 | completeness@10 | top-1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| original 2B | 0.4985 | 0.3971 | 0.5243 | 0.7080 | 0.2375 | 0.3495 | 0.5550 | 0.3155 |
| tuned 2B | 0.6878 | 0.6008 | 0.7229 | 0.8414 | 0.4105 | 0.5525 | 0.7225 | 0.5400 |
| hosted Jev | 0.6313 | 0.5582 | 0.6815 | 0.7849 | 0.3610 | 0.4995 | 0.6415 | 0.4785 |

Rows scored: 2000 of 2000.
Rows failed: 0.
API spend: $0.218315.
Prefix because of the $5 cap: no.

Top-1 is the fraction of rows whose rank-1 tool is a labeled positive.
Hosted ranks are the API probabilities, highest first. Ties keep menu order.
A response with no probability map uses the single chosen tool as rank 1 and leaves every lower rank empty.
Tools the response does not score stay unranked.
The API's own choice was probability rank 1 on 0.9940 of scored rows.
Treating that choice as the top-1 tool, whether or not it was the highest probability, the hit rate is 0.4795.

Pre-run estimate: $0.220540 for 2000 rows
at $0.042 per million input tokens. Output tokens are free.
The token rate comes from 90 earlier hosted calls on this same client.
Reported model: jev-1.13.0.

Exact values are in `results/hosted_jev_dev.json`. The table rounds to four decimals.
