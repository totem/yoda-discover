import json
import os

import yoda
import argparse
import docker
import time

from discover import logger, port_test, map_proxy_host
from requests.exceptions import HTTPError

import datetime
import boto.utils

#Polling interval in seconds
DISCOVER_POLL_INTERVAL = 45

def docker_client(parsed_args):
    return docker.Client(
        base_url=parsed_args.docker_url,
        version='1.12',
        timeout=10)


def yoda_client(parsed_args):
    return yoda.Client(etcd_host=parsed_args.etcd_host,
                       etcd_port=parsed_args.etcd_port,
                       etcd_base=parsed_args.etcd_base)


def do_register(parsed_args, private_port, public_port, mode):
    upstream = yoda.as_upstream(parsed_args.app_name,
                                parsed_args.app_version,
                                private_port)
    endpoint = yoda.as_endpoint(parsed_args.proxy_host, public_port)
    yoda_client(parsed_args).discover_node(upstream, parsed_args.node_name,
                                           endpoint, mode=mode)


def do_unregister(parsed_args, private_port):
    upstream = yoda.as_upstream(parsed_args.app_name,
                                parsed_args.app_version,
                                private_port)
    yoda_client(parsed_args).remove_node(upstream, parsed_args.node_name)


def docker_container_poll(parsed_args):
    while True:
        docker_cl = docker_client(parsed_args)
        try:
            container_info = docker_cl.inspect_container(
                parsed_args.node_name)
        except HTTPError as error:
            if error.response.status_code == 404:
                logger.warn('Container with name %s could not be found. '
                            'Aborting...', parsed_args.node_name)
                break
            else:
                raise

        if container_info['State']['Running']:
            for port_key in container_info['Config']['ExposedPorts']:
                private_port, protocol = port_key.split('/')
                if parsed_args.discover_ports and \
                        private_port not in parsed_args.discover_ports:
                    logger.debug('Skip proxy for port %s', private_port)
                    continue

                docker_port = \
                    docker_cl.port(parsed_args.node_name,
                                   private_port)
                if docker_port:
                    public_port = docker_port[0]['HostPort']
                else:
                    logger.info('Public port not found for %s. Skipping...',
                                private_port)
                    continue
                if port_test(int(public_port), parsed_args.proxy_host,
                             protocol):
                    endpoint = yoda.as_endpoint(parsed_args.proxy_host,
                                                public_port)
                    proxy_mode = parsed_args.proxy_mode_mapping.get(
                        private_port, 'http')
                    logger.info('Publishing %s : %s with mode:%s',
                                parsed_args.node_name, endpoint, proxy_mode)

                    do_register(parsed_args, private_port, public_port,
                                proxy_mode)

                else:
                    logger.info('Removing failed node %s:%s->%s',
                                parsed_args.node_name, public_port,
                                private_port)
                    do_unregister(parsed_args, private_port)
            time.sleep(DISCOVER_POLL_INTERVAL)
        else:
            logger.info('Stopping container poll (Main node is not running)%s',
                        parsed_args.node_name)
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Registers nodes to Yoda Proxy')
    parser.add_argument(
        '--docker-url', metavar='<DOCKER_URL>',
        default=os.environ.get('DOCKER_URL', 'http://172.17.42.1:4243'),
        help='Docker URL (defaults to http://172.17.42.1:4243)')
    parser.add_argument(
        '--etcd-host', metavar='<ETCD_HOST>',
        default=os.environ.get('ETCD_HOST', '172.17.42.1'),
        help='Docker URL (defaults to 172.17.42.1)')
    parser.add_argument(
        '--etcd-port', metavar='<ETCD_PORT>',
        default=os.environ.get('ETCD_PORT', '4001'), type=int,
        help='Docker URL (defaults to 4001)')
    parser.add_argument(
        '--etcd-base', metavar='<ETCD_BASE>',
        default=os.environ.get('ETCD_BASE', '/yoda'),
        help='Yoda base key (defaults to /yoda)')
    parser.add_argument(
        '--proxy-host', metavar='<PROXY_HOST>',
        default=os.environ.get('PROXY_HOST', '172.17.42.1'),
        help='Docker URL (defaults to 172.17.42.1. For ec2 , you can also use '
             'metadata. e.g.: ec2:metadata:public-hostname)')
    parser.add_argument(
        '--proxy-mode-mapping', metavar='<PROXY_MODE_MAPPING>',
        default=os.environ.get('PROXY_MODE_MAPPING', ''),
        help='Proxy mode mapping json using "key": "value" format where key '
             'is container port and value is "tcp" or "http". '
             'If mapping for port does not exists, http is used as default.')
    parser.add_argument(
        '--discover-ports', metavar='<DISCOVER_PORTS>',
        default=os.environ.get('DISCOVER_PORTS', ''),
        help='Comma separated container ports that needs to be discovered. If '
             'empty all exposed ports are discovered ')

    parser.add_argument(
        'app_name', metavar='<APPLICATION_NAME>', help='Application name')
    parser.add_argument(
        'app_version', metavar='<APPLICATION_VERSION>',
        help='Application Version')
    parser.add_argument(
        'node_name', metavar='<NODE_NAME>', help='Node Name')

    parsed_args = parser.parse_args()
    parsed_args.proxy_host = map_proxy_host(parsed_args.proxy_host)

    if parsed_args.proxy_mode_mapping:
        parsed_args.proxy_mode_mapping = json.loads(
            parsed_args.proxy_mode_mapping)
    else:
        parsed_args.proxy_mode_mapping = {}

    if parsed_args.discover_ports:
        parsed_args.discover_ports = parsed_args.discover_ports.split(',')
    else:
        parsed_args.discover_ports = []

    logger.info('Started discovery for %s using PROXY_MODE_MAPPING %r',
                parsed_args.node_name, parsed_args.proxy_mode_mapping)
    docker_container_poll(parsed_args)