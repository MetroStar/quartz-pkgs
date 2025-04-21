# syntax=docker/dockerfile:1
FROM registry1.dso.mil/ironbank/big-bang/base:2.1.0

ARG GRYPE_SCANNER_VERSION=0.91.0
ARG SYFT_SCANNER_VERSION=1.22.0
ARG CRANE_VERSION=0.20.3
ARG SONAR_SCANNER_VERSION=7.0.2.4839
ARG TERRAFORM_VERSION=1.5.7
ARG AWS_VERSION=2.22.13

# https://github.com/anchore/grype#offline-and-air-gapped-environments
ENV GRYPE_DB_AUTO_UPDATE=true

# https://github.com/anchore/grype#data-staleness
ENV GRYPE_DB_VALIDATE_AGE=true

ENV PATH=/usr/local/go/bin:/opt/sonar/bin:$PATH

USER root

RUN microdnf upgrade -y --nobest && \
    microdnf install -y make tar gzip git gettext java-17-openjdk wget unzip which skopeo --nodocs && \
    microdnf clean all && \
    rm -rf /var/cache/dnf

RUN curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin v${SYFT_SCANNER_VERSION}

RUN curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin v${GRYPE_SCANNER_VERSION}

RUN curl -sL "https://github.com/google/go-containerregistry/releases/download/v${CRANE_VERSION}/go-containerregistry_Linux_x86_64.tar.gz" > go-containerregistry.tar.gz && \
    tar -zxvf go-containerregistry.tar.gz -C /usr/local/bin/ crane && \
    rm go-containerregistry.tar.gz

RUN SONAR_SCANNER_PACKAGE=sonar-scanner-cli-${SONAR_SCANNER_VERSION}-linux-x64 && \
    wget https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/${SONAR_SCANNER_PACKAGE}.zip && \
    unzip ${SONAR_SCANNER_PACKAGE}.zip && \
    rm ${SONAR_SCANNER_PACKAGE}.zip && \
    mv ./sonar-scanner-${SONAR_SCANNER_VERSION}-linux-x64/ /opt/sonar/

RUN curl -o terraform.zip https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform.zip && \
    mv terraform /usr/local/bin/terraform && \
    chmod +x /usr/local/bin/terraform && \
    rm terraform.zip

RUN curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${AWS_VERSION}.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf aws && \
    rm awscliv2.zip

RUN curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

RUN curl -sL https://fluxcd.io/install.sh | bash -s

USER 1000

RUN grype db update && \
    grype db status

RUN helm version && \
    flux --version && \
    grype --version && \
    syft --version && \
    terraform --version && \
    crane version && \
    skopeo --version && \
    java --version && \
    aws --version && \
    /opt/sonar/bin/sonar-scanner --version
