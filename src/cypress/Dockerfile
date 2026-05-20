ARG BASE_REGISTRY=registry1.dso.mil
ARG BASE_IMAGE=ironbank/cypress/included
ARG BASE_TAG=15.15.0

FROM ${BASE_REGISTRY}/${BASE_IMAGE}:${BASE_TAG}

ARG UNLIGHTHOUSE_VERSION=v0.17.9

USER root

RUN npm install -g \
  @unlighthouse/cli@${UNLIGHTHOUSE_VERSION} \
  unlighthouse@${UNLIGHTHOUSE_VERSION} \
  cypress-multi-reporters \
  cypress-file-upload \
  mocha \
  mocha-junit-reporter \
  mochawesome \
  mochawesome-merge \
  mochawesome-report-generator

USER 1000