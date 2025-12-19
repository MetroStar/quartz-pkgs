ARG STRIMZI_VERSION=0.49.1
ARG KAFKA_VERSION=4.1.1

FROM quay.io/strimzi/kafka:${STRIMZI_VERSION}-kafka-${KAFKA_VERSION}

USER root

RUN mkdir /src && \
    cd /src && \
    curl -sLO https://github.com/streamthoughts/kafka-connect-file-pulse/releases/download/v2.16.0/streamthoughts-kafka-connect-file-pulse-2.16.0.zip && \
    curl -sLO https://d2p6pa21dvn84.cloudfront.net/api/plugins/confluentinc/kafka-connect-jdbc/versions/10.9.2/confluentinc-kafka-connect-jdbc-10.9.2.zip && \
    unzip '/src/*.zip' -d /opt/kafka/plugins/ && \
    rm -rf /src

USER kafka