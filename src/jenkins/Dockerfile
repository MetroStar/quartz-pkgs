ARG JENKINS_VERSION=2.510-jdk17

FROM registry1.dso.mil/ironbank/opensource/jenkins/jenkins:${JENKINS_VERSION}

USER root

COPY plugins.txt /usr/share/jenkins/ref/plugins/plugins.txt

RUN chmod +x /usr/bin/jenkins-plugin-cli && \
    jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins/plugins.txt --available-updates && \
    jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins/plugins.txt --verbose && \
    chown jenkins:jenkins /usr/share/jenkins/ref/plugins/*.*

USER jenkins