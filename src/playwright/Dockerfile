ARG BASE_REGISTRY=registry1.dso.mil
ARG BASE_IMAGE=ironbank/opensource/nodejs/debian/nodejs
ARG BASE_TAG=22.15.0

FROM ${BASE_REGISTRY}/${BASE_IMAGE}:${BASE_TAG}

ARG PLAYWRIGHT_VERSION=1.52.0
ARG UNLIGHTHOUSE_VERSION=v0.16.3

ENV CI=1

USER root

WORKDIR /src

COPY package.json package-lock.json ./
RUN npm ci && \
    npx playwright@${PLAYWRIGHT_VERSION} install chromium msedge firefox webkit --with-deps --no-shell && \
    npx puppeteer browsers install chrome-headless-shell && \
    npm install -g @unlighthouse/cli@${UNLIGHTHOUSE_VERSION} && \
    cp -R /root/.cache /home/node/.cache && \
    chown -R node:node /home/node/.cache && \
    echo "export CHROME_PATH=$(find /home/node/.cache/puppeteer -name chrome-headless-shell -executable -type f)" >> /etc/profile && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER 1000
