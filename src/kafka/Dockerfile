ARG STRIMZI_VERSION=0.45.0
ARG KAFKA_VERSION=3.9.0

FROM quay.io/strimzi/kafka:${STRIMZI_VERSION}-kafka-${KAFKA_VERSION}

USER root

RUN mkdir /src && \
    cd /src && \
    curl -sLO https://github.com/streamthoughts/kafka-connect-file-pulse/releases/download/v2.14.1/streamthoughts-kafka-connect-file-pulse-2.14.1.zip && \
    curl -sLO https://d2p6pa21dvn84.cloudfront.net/api/plugins/confluentinc/kafka-connect-jdbc/versions/10.7.6/confluentinc-kafka-connect-jdbc-10.7.6.zip && \
    unzip '/src/*.zip' -d /opt/kafka/plugins/ && \
    rm -rf /src

USER kafka