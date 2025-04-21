ARG NODEJS_VERSION=20.18.2-slim

FROM registry1.dso.mil/ironbank/opensource/nodejs/nodejs20:${NODEJS_VERSION}

USER root

RUN npm upgrade -g npm && \
    chown -R node:node /home/node && \
    npm --version

USER node
