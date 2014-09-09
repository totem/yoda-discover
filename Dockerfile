FROM totem/python-base:3.4-trusty

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update
RUN apt-get install -y openssh-server openssh-client libffi-dev

##SSH Server (To troubleshoot issues with discover)
RUN mkdir /var/run/sshd
ADD .root/.ssh /root/.ssh
RUN chmod -R 400 /root/.ssh/* && chmod  500 /root/.ssh & chown -R root:root /root/.ssh

ADD requirements.txt /opt/requirements.txt
RUN pip3 install -r /opt/requirements.txt

ADD . /opt/yoda-discover
RUN pip3 install -r /opt/yoda-discover/requirements.txt

EXPOSE 22

ENV ETCD_BASE /yoda
ENV DOCKER_URL http://172.17.42.1:4243
ENV ETC_HOST 172.17.42.1
ENV ETCD_PORT 4001
ENV PROXY_HOST 172.17.42.1

WORKDIR /opt/yoda-discover
ENTRYPOINT ["/usr/bin/python3","-m"]
CMD ["discover.docker_poller"]