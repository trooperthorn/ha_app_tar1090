# Install and operate

Add `https://github.com/trooperthorn/ha_app_tar1090` as an App repository after the app commit is merged and its image is published. For a reviewed feature-branch trial, append `#feat/home-assistant-app`. Install Local Aircraft, configure the receiver base URL, then start and open its web UI. Prebuilt images are required for store installs; the Docker build context for development is the repository root.

## Source

The URL is the receiver webpage base, for example `http://192.168.30.57:1090`. The collector appends `/data/aircraft.json` and `/data/receiver.json`. Both endpoints were reachable on the development receiver on 2026-09-08. Other receivers must be checked. A path such as `http://pi/tar1090` is supported. Redirects and URL-embedded credentials are deliberately rejected. TLS uses normal certificate validation.

Metadata is refreshed hourly after success, or once per minute until receiver coordinates are available. Aircraft collection is shared by all displays. A configured five-second interval is a minimum idle delay between completed requests; latency and timeout/backoff can make the actual interval longer.

## Embed in a dashboard

Download `tar1090-card.js` from the release and copy it to `/config/www/tar1090-card.js`. Add `/local/tar1090-card.js` as a JavaScript module under dashboard resources. This manual copy avoids giving the app write access to HA configuration.

Find the full installed app slug in its HA settings URL (repository prefix plus `_tar1090`). Add a manual card:

```yaml
type: custom:tar1090-card
addon: REPOSITORYPREFIX_tar1090
height: 600
query: zoom=9&hideButtons&hideSideBar&centerReceiver&mapDim=0.4&iconScale=0.7&labelScale=0.75&extendedLabels=2&rangeRings=0&filterAltMax=10000&mapOrientation=150&enableLabels
```

The card obtains the current ingress URL and session using HA's authenticated websocket API. It does not store an HA token or hardcode an ingress session URL. It validates/renews the session periodically. The HA user needs permission to query/access this app; administrator access is the initial supported setup. HA non-admin policy and mobile reconnect behavior must be verified on your version. Ingress expiry, app stop/restart, remote HTTPS access, and dashboard navigation are live acceptance checks.

## Settings and behavior

- `poll_seconds`: 2–60; default 5. Fewer requests lower link load but reduce update detail.
- `timeout_seconds`: 1–30; default 4. Increase if measured link latency requires it.
- `stale_seconds`: default 20; at least twice the poll interval.
- `expire_seconds`: default 60; greater than stale threshold. Expired aircraft are removed from the display.
- `history_minutes`: 1–480; default 60. Sealed chunks expire at chunk granularity (up to roughly 12 samples beyond individual-record age).
- `history_mb`: 1–256; default 32. Budget for retained compressed chunks plus the current uncompressed group. Runtime also needs memory for the latest decoded response and frontend services.
- `max_response_mb`: 1–32; default 8. Encoded and decoded response limits.
- `site_name`: display label. Coordinates come from receiver metadata.
- `map_type`: `osm`, `carto_dark_all`, `carto_light_all`, `esri`, or `blank`.

Status badge: LIVE, STALE, EXPIRED, or waiting. Click for JSON diagnostics: received body bytes, request count, negotiated encoding, source age, source epoch, and last error category. Counters reset with the app. HTTP success without a changing source timestamp becomes stale; clock rollback starts a new history epoch. Data is never re-dated to appear live. Health reports app-process health, not radio availability, so an outage does not provoke watchdog restart loops.

History lives in memory, not `/data`, and resets on restart/upgrade/rollback. No persistent history is promised or backed up. No per-snapshot disk writes are required. HA backs up app options through its normal app backup mechanism.

## Compatibility boundaries

MLAT fields are preserved when present in the Pi snapshot. No independent MLAT or UAT stream is opened; combined UAT present in the source is preserved. Missing sources cannot be reconstructed. Receiver-wide globe replay, heatmaps, commercial flight history, and hosted account features are not supported. Locally accumulated trails are sampled at the collector rate.

The altitude query filters the display only. To reduce wireless payload by altitude or radius, use the optional Pi exporter; do not filter HA-side and assume link savings. Unknown altitude remains unknown.

OSM/CARTO/Esri basemaps use their providers over the display's network connection and retain attribution. Blank mode makes no basemap requests and works offline. Photos and route enrichment are disabled in v1. Full offline map tiles and historical replay are separate future features.

## Troubleshooting and rollback

1. Check app logs and `/health`. A configuration error stops startup; a radio outage leaves the app running.
2. Open status diagnostics. `receiver_ready=false` indicates metadata/coordinate discovery failed. `last_error` identifies the error category without logging sensitive response text.
3. On the HA side run `python tools/measure_source.py URL` to compare encoded payloads. Packet/interface counters are needed to include wireless retransmissions and other feeder traffic.
4. In browser developer tools verify aircraft, history, scripts, and database requests all go to HA; no aircraft request should go directly to the Pi.
5. Test at a busy traffic period. The initial quiet sample is not a capacity benchmark.

For rollback, restore your original Pi iframe URL and stop the app. It has not changed the decoder or feeder configuration. Reinstall an earlier immutable app version if available; history resets. Stop any separately installed Pi exporter and restore the original source URL. Keep protected mode enabled; do not disable AppArmor to mask a startup problem—collect the denial and correct the profile.

## Security and updates

Ingress listener accepts only Supervisor's documented ingress address; no LAN port is published. No HA Core, Supervisor, Docker, host-network, USB or SDR access is requested. The custom AppArmor profile must be checked under enforcing HA OS before stable promotion. Source URL is administrator-configured and can reach the private receiver network; it is not a public proxy endpoint.

Releases bundle pinned frontend/database inputs and a pinned base-image digest. No runtime self-updater. GPL v2-or-later source and notices remain in the repository; built images contain LICENSE.txt. Update app and frontend/database versions independently and rerun the documented tests before releasing.
