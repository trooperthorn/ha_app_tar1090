/* Source freshness is wall-clock based, independent of receiver time. */
"use strict";
window.haBridgeExpired = false;
let haBridgeEpoch = null;
let haBridgeStatusReceived = 0;
let haBridgeLastStatus = null;
const haBridgeBanner = document.createElement('div');
haBridgeBanner.id = 'ha-bridge-status';
haBridgeBanner.setAttribute('role', 'status');
document.body.appendChild(haBridgeBanner);
function haBridgeApply(status) {
    haBridgeLastStatus = status;
    haBridgeStatusReceived = performance.now();
    if (haBridgeEpoch && haBridgeEpoch !== status.epoch) {
        // Clear incompatible traces without inventing receiver timestamps.
        reaper(true);
        now = 0;
        last = 0;
    }
    haBridgeEpoch = status.epoch;
    if (status.receiver_ready && loadFinished && receiverJson && receiverJson.lat == null) {
        // Metadata may arrive after an initial radio outage. Reinitialize the site once.
        location.reload();
        return;
    }
    const expired = ['expired', 'waiting'].includes(status.state);
    if (expired && !window.haBridgeExpired && loadFinished) reaper(true);
    if (!expired && window.haBridgeExpired) { now = 0; last = 0; }
    window.haBridgeExpired = expired;
    const age = status.age_seconds === null ? 'no data' : `${Math.round(status.age_seconds)}s old`;
    haBridgeBanner.textContent = `${status.state.toUpperCase()} · ${age}`;
    haBridgeBanner.dataset.state = status.state;
    haBridgeBanner.title = `Upstream: ${status.upstream_encoding}, ${status.average_body_bits_per_second} bit/s body average. Click for diagnostics.`;
}
haBridgeBanner.addEventListener('click', () => window.open('status.json', '_blank', 'noopener'));
async function haBridgePoll() {
    try {
        const response = await fetch('status.json', {cache: 'no-store', signal: AbortSignal.timeout(4000)});
        if (!response.ok) throw new Error('status unavailable');
        haBridgeApply(await response.json());
    } catch (_) {
        haBridgeBanner.textContent = 'APP CONNECTION LOST';
        haBridgeBanner.dataset.state = 'stale';
        // Browser-to-app outages also age out displayed aircraft.
        const age = haBridgeLastStatus?.age_seconds;
        const elapsed = (performance.now() - haBridgeStatusReceived) / 1000;
        if (!haBridgeLastStatus || age === null || age + elapsed >= haBridgeLastStatus.expire_seconds) {
            if (loadFinished) reaper(true);
            window.haBridgeExpired = true;
        }
    } finally {
        setTimeout(haBridgePoll, 2000);
    }
}
haBridgePoll();
