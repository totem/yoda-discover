FROM totem/python-base:3.4-trusty-b2

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update --fix-missing && apt-get install -y \
        libyaml-dev \
        libffi-dev \
    && apt-get clean \
    && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*

ADD requirements.txt /opt/requirements.txt
RUN pip3 install -r /opt/requirements.txt

ADD . /opt/yoda-discover
RUN pip3 install -r /opt/yoda-discover/requirements.txt

ENV ETCD_BASE /yoda
ENV DOCKER_URL http://172.17.42.1:4243
ENV ETC_HOST 172.17.42.1
ENV ETCD_PORT 4001
ENV PROXY_HOST 172.17.42.1

WORKDIR /opt/yoda-discover
ENTRYPOINT ["/usr/bin/python3","-m"]
CMD ["discover.docker_poller"]
