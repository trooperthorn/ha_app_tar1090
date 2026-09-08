# Working on the Home Assistant App

Preserve the upstream frontend sources where possible; `tools/build_frontend.py` stages and patches the local edition. Do not run the legacy `install.sh` on HA OS or at container startup. Build context is repository root.

Run `python -m unittest discover -s tests -v`, `node --test`, frontend staging and `node tools/browser_check.cjs`, then `docker build -f tar1090/Dockerfile -t ha-tar1090:test .` and `python tools/container_smoke.py`. Browser tests require Playwright; `CHROME` can select a local browser and `PYTHON` a Python executable. Work files belong in ignored `work/`.

On upstream updates, review exact patch anchors, third-party requests, script order, capabilities, and licenses. Do not accept unresolved templates or make the frontend proxy arbitrary requests to the Pi. Keep one upstream collector, bounded storage/requests, and original source timestamps.

Never treat unit tests or CI as live HA OS/ingress/AppArmor/wireless evidence. Record each boundary in validation notes. Publish new version tags rather than overwrite images. No automatic receiver configuration changes.
