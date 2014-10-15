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

def parse_container_env(env_cfg):
    parsed_env = dict()
    for env_entry in env_cfg:
        env_name, env_value = env_entry.split('=', 1)
        parsed_env[env_name] = env_value
    return parsed_env


def yoda_client(parsed_args):
    return yoda.Client(etcd_host=parsed_args.etcd_host,
                       etcd_port=parsed_args.etcd_port,
                       etcd_base=parsed_args.etcd_base)


def do_register(parsed_args, app_name, app_version, private_port, public_port,
                mode):
    upstream = yoda.as_upstream(app_name, app_version, private_port)
    endpoint = yoda.as_endpoint(parsed_args.proxy_host, public_port)
    yoda_client(parsed_args).discover_node(upstream, parsed_args.node_name,
                                           endpoint, mode=mode)


def do_unregister(parsed_args, app_name, app_version, private_port):
    upstream = yoda.as_upstream(app_name, app_version, private_port)
    yoda_client(parsed_args).remove_node(upstream, app_name, app_version)


def docker_container_poll(parsed_args):
    docker_cl = docker_client(parsed_args)
    try:
        container_info = docker_cl.inspect_container(
            parsed_args.node_name)
    except HTTPError as error:
        if error.response.status_code == 404:
            logger.warn('Container with name %s could not be found. '
                        'Aborting...', parsed_args.node_name)
            return
        else:
            raise

    env_cfg = container_info['Config']['Env']
    parsed_env = parse_container_env(env_cfg)

    if not 'DISCOVER_APP_VERSION' in parsed_env or \
            not 'DISCOVER_APP_NAME' in parsed_env:
        logger.warn('Discover env variables not set for container: %s. '
                    'Aborting...', parsed_args.node_name)
        return

    app_name = parsed_env['DISCOVER_APP_NAME']
    app_version = parsed_env['DISCOVER_APP_VERSION']
    proxy_modes = parsed_env.get('DISCOVER_PROXY_MODES', '{}')
    proxy_modes = json.loads(proxy_modes) if proxy_modes else {}
    discover_ports = parsed_env.get('DISCOVER_PORTS', '')
    discover_ports = [valid_port for valid_port in
                      [port.strip() for port in discover_ports.split(',')]
                      if valid_port]

    while True:
        try:
            container_info = docker_cl.inspect_container(
                parsed_args.node_name)
        except HTTPError as error:
            if error.response.status_code == 404:
                logger.warn('Container with name %s could not be found. '
                            'Aborting...', parsed_args.node_name)
                return
            else:
                raise

        if container_info['State']['Running']:
            for port_key in container_info['Config']['ExposedPorts']:
                private_port, protocol = port_key.split('/')
                if discover_ports and private_port not in discover_ports:
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
                    proxy_mode = proxy_modes.get(private_port, 'http')
                    if proxy_mode not in ['http', 'tcp']:
                        logger.warn('Invalid proxy mode found for %s: %s.'
                                    'Skipping...', private_port, proxy_mode)
                        continue
                    logger.info('Publishing %s : %s with mode:%s',
                                parsed_args.node_name, endpoint, proxy_mode)

                    do_register(parsed_args, app_name, app_version,
                                private_port, public_port, proxy_mode)

                else:
                    logger.info('Removing failed node %s:%s->%s',
                                parsed_args.node_name, public_port,
                                private_port)
                    do_unregister(parsed_args, app_name, app_version,
                                  private_port)
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
        'node_name', metavar='<NODE_NAME>', help='Node Name (Container Name)')

    parsed_args = parser.parse_args()
    parsed_args.proxy_host = map_proxy_host(parsed_args.proxy_host)

    logger.info('Started discovery for %s', parsed_args.node_name)
    docker_container_poll(parsed_args)