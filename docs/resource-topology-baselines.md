# Resource/topology baseline fixture

This fixture is a deterministic synthetic systems test for issue #64. It is not
a hardware benchmark and it is not model-quality evidence.

The fixture keeps one hard fast-tier budget fixed across static, LRU, and
aggressive-prefetch policies. The receipt reports component metrics rather than a
single score: bytes moved, misses and miss penalty, controller overhead, cache
churn, latency, mean TTFT, decode throughput, occupancy/headroom, and quality
deviation.

The aggressive-prefetch policy is a deliberate negative control. The fixture is
constructed so it can obtain a higher demand hit rate than LRU while still paying
more total system cost. This protects downstream work from treating cache hit rate
as the optimization authority.

Unavailable native runtime/router behavior is recorded as NOT_EXPOSED rather than
simulated and mislabeled as a native baseline. A future real-runtime fixture can
add that policy while preserving this synthetic receipt as a deterministic
regression case.

The committed receipt is byte-stable. The canonical repository check verifies
that the manifest, trace, simulator, and receipt still agree.
