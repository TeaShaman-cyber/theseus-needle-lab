# Needle A/B/C permutation verbalizer-prior probe

Issue: #18. Base Needle 2.0.8 only; no training. Six bijective mappings permute `A/B/C` onto `PROBE/READY/UNKNOWN` while preserving the exact predecessor framing, tool, field, enum token set, dataset, and decode budget.

Primary diagnostic: whether raw `A/B/C` predictions remain stable while their declared semantics are permuted.
