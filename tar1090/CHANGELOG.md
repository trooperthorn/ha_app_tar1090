# 0.1.0-beta.2

- Move the status badge above the scale bar, preserving both controls in the embedded map.
- Add controlled visual comparison evidence from the installed Pi frontend.

# 0.1.0-beta.1

- Local-receiver frontend derived from ADSBexchange/tar1090, with hosted advertising, identity, challenge, and flight-activity dependencies removed from the deployed entry page.
- Shared gzip HTTP collector with validation, bounded responses, retry backoff, truthful source timestamps, and diagnostics.
- Bounded in-memory sampled history; restart resets history. Stale/expired source indication and aircraft expiry.
- HA ingress packaging and companion dashboard card using HA-managed ingress sessions.
- Reproducible asset/database staging, immutable base digest, amd64/aarch64 build and smoke-test workflow.
- Optional Pi-side filtered exporter and read-only payload measurement tool.

Experimental: HA OS ingress/AppArmor and exact installed-dashboard acceptance still require live validation. No claim of peak-load wireless savings or full historical replay support.
