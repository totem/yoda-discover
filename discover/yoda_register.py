import os

import yoda
import argparse
import docker
import time

from discover import logger, port_test, map_proxy_host
from requests.exceptions import HTTPError

import datetime
import boto.utils


def docker_client(parsed_args):
    return docker.Client(
        base_url=parsed_args.docker_url,
        version='1.12',
        timeout=10)


def yoda_client(parsed_args):
    return yoda.Client(etcd_host=parsed_args.etcd_host,
                       etcd_port=parsed_args.etcd_port,
                       etcd_base=parsed_args.etcd_base)


def do_register(parsed_args, private_port, public_port):
    upstream = yoda.as_upstream(parsed_args.app_name,
                                parsed_args.app_version,
                                private_port)
    endpoint = yoda.as_endpoint(parsed_args.proxy_host, public_port)
    yoda_client(parsed_args).discover_node(upstream, parsed_args.node_name,
                                endpoint)


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

                public_port = \
                    docker_cl.port(parsed_args.node_name,
                                   private_port)[0]['HostPort']
                if port_test(int(public_port), parsed_args.proxy_host,
                             protocol):
                    endpoint = yoda.as_endpoint(parsed_args.proxy_host,
                                                public_port)
                    logger.info('Publishing %s : %s',
                                parsed_args.node_name,
                                endpoint)
                    do_register(parsed_args, private_port, public_port)

                else:
                    logger.info('Removing failed node %s:%s->%s',
                                parsed_args.node_name, public_port,
                                private_port)
                    do_unregister(parsed_args, private_port)
            time.sleep(45)
        else:
            logger.info('Stopping container poll (Main node is not running)%s',
                        parsed_args.node_name)
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Registers nodes to Yoda Proxy')
    parser.add_argument(
        '--docker-url', metavar='<DOCKER_URL>',
        default='http://172.17.42.1:4243',
        help='Docker URL (defaults to http://172.17.42.1:4243)')
    parser.add_argument(
        '--etcd-host', metavar='<ETCD_HOST>',
        default='172.17.42.1',
        help='Docker URL (defaults to 172.17.42.1)')
    parser.add_argument(
        '--etcd-port', metavar='<ETCD_PORT>',
        default='4001',type=int,
        help='Docker URL (defaults to 4001)')
    parser.add_argument(
        '--etcd-base', metavar='<ETCD_BASE>',
        default='/yoda',
        help='Docker URL (defaults to /yoda)')
    parser.add_argument(
        '--proxy-host', metavar='<PROXY_HOST>',
        default='172.17.42.1',
        help='Docker URL (defaults to 172.17.42.1. For ec2 , you can also use '
             'metadata. e.g.: ec2:metadata:public-hostname)')

    parser.add_argument(
        'app_name', metavar='<APPLICATION_NAME>', help='Application name')
    parser.add_argument(
        'app_version', metavar='<APPLICATION_VERSION>',
        help='Application Version')
    parser.add_argument(
        'node_name', metavar='<NODE_NAME>', help='Node Name')

    parsed_args = parser.parse_args()
    parsed_args.proxy_host = map_proxy_host(parsed_args.proxy_host)
    logger.info('Started discovery for %s', parsed_args.node_name)
    docker_container_poll(parsed_args)