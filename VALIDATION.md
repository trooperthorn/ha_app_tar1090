# Validation record

## Local development, 2026-09-08

- Baseline: master `78bfa3f58f97c1694b190e66a400604e8b0f0b81`; clean checkout before work.
- Existing Node activity/date tests: 31 passed on Node v26.8.1.
- Python collector/exporter tests: 21 passed locally. Collector tests cover source freeze, rollback, unknown fields, metadata normalization, invalid data, retention, encoded/decompressed response limits, redirects, and one shared fetch schedule.
- Headless Chrome mock-data test: map loaded at zoom 9, orientation 150 degrees, extended labels 2, altitude filter 10,000 feet; no missing assets, browser exceptions or external requests in blank-basemap mode. Expiry cleared aircraft, recovery restored them, clock rollback recovered. Nested ingress paths and the dashboard card session flow were also exercised. This is a controlled rendered test, not an identical comparison against the installed Pi bundle.
- WSL amd64 container build and smoke tests: startup, Nginx configuration, source-outage health, ingress rejection for unauthorized source, and clean shutdown passed. WSL Docker does not expose AppArmor enforcement, so that check cannot qualify HA OS here.
- Receiver metadata and both JSON/binary endpoints were read successfully. Receiver advertises readsb, binary/Zstandard and one-second refresh. The app normalizes its own capabilities instead of copying these flags.
- Three sequential quiet-period measurements: plain JSON 676 bytes; gzip JSON 466–468 bytes; binary/Zstandard 150–154 bytes. Request duration 0.68–3.90 seconds. These are encoded body sizes only, sampled at different times; no busy-period or interface-level benchmark. Pacing can reduce requests, but JSON is not inherently smaller than the existing binary format.

## Required live acceptance before stable promotion

- Install the versioned image on the user's HA OS architecture; validate enforced AppArmor, boot/restart, settings and watchdog.
- Load the companion card through authenticated HA, including navigation away/back, session renewal, app restart, HTTPS remote access and relevant user roles/mobile devices.
- Compare the old and new map with identical receiver data, selected basemap and viewport. Current browser tests use a controlled blank basemap, not a screenshot of the production dashboard.
- Measure busy-period wireless interface counters and other feeder uploads, then choose the final interval and any Pi-side filters against the actual capacity budget.
- Test actual wireless interruption/recovery. No changes have been made to decoder, radio, feeder configuration, or Pi exporter service.

Release remains experimental until these checks pass. CI results must be recorded separately from live receiver/dashboard evidence.

## Remote CI evidence

Native amd64 and ARM64 container builds, ordinary smoke tests, and enforced AppArmor smoke tests passed in GitHub Actions. The complete suite (Python, Node 22, staged browser checks, both architectures) passed in runs 34198784679 and 34198930475. These validate the pre-release implementation; subsequent final-head/tag runs are authoritative for a published image. They do not replace HA OS acceptance.

## Controlled installed-Pi frontend comparison

The Pi's existing frontend and the app were rendered at 1440x900 with identical synthetic aircraft, receiver position, query parameters and blank-basemap request. Both reported zoom 9, orientation 150 degrees, extended labels 2 and altitude ceiling 10,000 feet; aircraft placement and labels matched visually with no browser errors. The blank background differed between implementations; this does not validate parity for the user's selected production basemap. The comparison caught the new status badge overlapping the scale bar; beta.2 moves it above the scale. Original screenshots and measurements are local research artifacts.

Beta.1 publishing run 34199210233 completed successfully, including validation on both architectures, signed image and prerelease creation. Anonymous registry inspection confirmed amd64/arm64 manifests. Beta.2 uses a new immutable version for the visual correction.
