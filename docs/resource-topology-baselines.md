# Resource/topology baseline fixture

This fixture is a deterministic synthetic systems test for issue #64. It is not
a hardware benchmark and it is not model-quality evidence.

The fixture keeps one hard fast-tier budget fixed across static, LRU, and
aggressive-prefetch policies. The receipt reports component metrics rather than a
single score: bytes moved, misses and miss penalty, controller overhead, cache
churn, latency, mean TTFT, decode throughput, and occupancy/headroom. Quality is
not evaluated by this synthetic fixture, so quality deviation is explicitly null
with status NOT_MEASURED rather than reported as zero.

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

Metrics whose required phase is absent are emitted as null with an explicit
NOT_OBSERVED status instead of synthesizing zero or dividing by zero. Simulator
cost parameters must be finite and nonnegative; malformed manifests fail closed
before simulation.

The static fixed-set baseline is only valid when the configured fixed working
sets are unique, known, and fit together inside the hard fast-tier budget.
Otherwise fixture validation fails closed instead of silently evicting a member
of the purported fixed set.

A decode phase that is present but has zero modeled duration is distinguished
from an absent decode phase: throughput is null with status
OBSERVED_ZERO_DURATION, not NOT_OBSERVED.
