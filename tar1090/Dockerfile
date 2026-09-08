# Build context is the repository root. Releases ship a prebuilt multi-arch image.
FROM ghcr.io/home-assistant/base@sha256:93ef607824e3f27e868f11b10938283a98bf880ed57bcf8eaa81c6c2d521f6f5 AS builder
RUN apk add --no-cache python3
WORKDIR /src
COPY html ./html
COPY LICENSE ./LICENSE
COPY tools/build_frontend.py tools/fetch_database.py ./tools/
COPY tar1090/frontend ./tar1090/frontend
COPY tar1090/versions.json ./tar1090/versions.json
RUN python3 tools/fetch_database.py /tmp/database && \
    python3 tools/build_frontend.py --database /tmp/database --output /web

FROM ghcr.io/home-assistant/base@sha256:93ef607824e3f27e868f11b10938283a98bf880ed57bcf8eaa81c6c2d521f6f5
RUN apk add --no-cache nginx python3 && \
    mkdir -p /run/nginx /etc/services.d/collector /etc/services.d/nginx
COPY --from=builder /web /opt/tar1090/web
COPY tar1090/app /opt/tar1090/app
COPY tar1090/rootfs /
RUN chmod +x /etc/services.d/*/run /etc/services.d/*/finish
LABEL io.hass.type="app" org.opencontainers.image.source="https://github.com/trooperthorn/ha_app_tar1090"
HEALTHCHECK --interval=30s --timeout=5s CMD wget -q -O /dev/null http://127.0.0.1:8098/health || exit 1
