# Optional Pi-side filtering

Use only when measured compressed snapshots still exceed the link budget. This exporter reads the decoder's files; it does not alter them or the existing aggregator feeds. Unknown altitude/position and all other aircraft fields are retained. Radius is nautical miles; altitude is feet using barometric altitude when present.

First identify the actual host/container directory containing `aircraft.json` and `receiver.json`. Do not guess the adsb.im bind mount. Run as a dedicated user with read access only:

```sh
python3 exporter.py --source-dir /verified/decoder/json --bind PI_LAN_IP --allow-client HA_SOURCE_IP --max-altitude 10000
```

Point the HA App source URL to `http://PI_LAN_IP:8097`. Restrict that port to the HA-side source IP at the firewall too. A containerized HA app may appear as its host's NAT address. TLS can be supplied by an existing trusted local proxy if required. The service has no internet authentication layer and should remain on the private receiver network.

Test without filters first. Verify compressed response size, aircraft count, and MLAT preservation before enabling filters. Stop the exporter and restore the original source URL to roll back. No exporter is installed automatically by the HA app.
