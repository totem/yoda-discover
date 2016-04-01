import json
import os

import yoda
import argparse
import docker
import time

from discover import logger
from requests.exceptions import HTTPError

from discover.util import map_proxy_host, health_test, init_shutdown_handler

# Polling interval in seconds
DISCOVER_POLL_INTERVAL = 45
DEPLOYMENT_BLUE_GREEN = 'blue-green'


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
                deployment_mode, ttl, service_name=None, node_num=None):
    use_version = app_version if deployment_mode == DEPLOYMENT_BLUE_GREEN \
        else None
    upstream = yoda.as_upstream(app_name, private_port,
                                app_version=use_version)
    endpoint = yoda.as_endpoint(parsed_args.proxy_host, public_port)
    meta = {}
    if service_name:
        meta['service-name'] = service_name
    if node_num:
        meta['node-num'] = node_num

    yoda_client(parsed_args).discover_node(
        upstream, parsed_args.node_name, endpoint, ttl=ttl, meta=meta)


def renew_upstream(parsed_args, app_name, app_version, private_port,
                   deployment_mode, ttl=3600):
    use_version = app_version if deployment_mode == DEPLOYMENT_BLUE_GREEN \
        else None
    upstream = yoda.as_upstream(app_name, private_port,
                                app_version=use_version)
    yoda_client(parsed_args).renew_upstream(upstream, ttl=ttl)


def get_container_info(docker_cl, node_name):
    try:
        return docker_cl.inspect_container(node_name)
    except HTTPError as error:
        if error.response.status_code == 404:
            logger.warn('Container with name %s could not be found. '
                        'Aborting...', node_name)
            return None
        else:
            raise


def docker_container_poll(parsed_args, poll=None):
    logger.info('Started discovery for %s', parsed_args.node_name)
    docker_cl = docker_client(parsed_args)
    container_info = get_container_info(docker_cl, parsed_args.node_name)
    if not container_info:
        return

    env_cfg = container_info['Config']['Env']
    parsed_env = parse_container_env(env_cfg)

    app_name = parsed_env.get('DISCOVER_APP_NAME', 'not-set')
    app_version = parsed_env.get('DISCOVER_APP_VERSION')
    health_checks = parsed_env.get('DISCOVER_HEALTH', '{}')
    deployment_mode = parsed_env.get('DISCOVER_MODE', 'blue-green').lower()
    health_checks = json.loads(health_checks) if health_checks else {}
    discover_ports = parsed_env.get('DISCOVER_PORTS', '')
    discover_ports = [valid_port for valid_port in
                      [port.strip() for port in discover_ports.split(',')]
                      if valid_port]
    poll_interval = int(parsed_env.get('DISCOVER_POLL_INTERVAL',
                                       DISCOVER_POLL_INTERVAL))

    # Set default ttl to 4 times the poll_interval (plus buffer) which
    # gives 4 chances for bad node to survive bad health test
    discover_ttl = int(parsed_env.get('DISCOVER_TTL', poll_interval*4+10))
    upstream_ttl = int(parsed_env.get('DISCOVER_UPSTREAM_TTL', '86400'))

    poll = poll or (lambda: True)

    while poll():
        container_info = get_container_info(docker_cl, parsed_args.node_name)
        if not container_info:
            return

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
                # Renew upstream (Whether health check fail or passes)
                renew_upstream(parsed_args, app_name, app_version,
                               private_port, deployment_mode, ttl=upstream_ttl)
                health_check = health_checks.get(private_port, {})
                if health_test(int(public_port), parsed_args.proxy_host,
                               protocol=protocol, **health_check):
                    endpoint = yoda.as_endpoint(parsed_args.proxy_host,
                                                public_port)

                    logger.info('Publishing %s : %s',
                                parsed_args.node_name, endpoint)

                    do_register(parsed_args, app_name, app_version,
                                private_port, public_port, deployment_mode,
                                ttl=discover_ttl,
                                node_num=parsed_args.node_num,
                                service_name=parsed_args.service_name)

                else:
                    logger.warn('Health check failed for node %s:%s->%s',
                                parsed_args.node_name, public_port,
                                private_port)
            time.sleep(poll_interval)
        else:
            logger.info('Stopping container poll (Main node is not running)%s',
                        parsed_args.node_name)
            break


def create_parser():
    parser = argparse.ArgumentParser(
        description='Registers nodes to Yoda Proxy')
    parser.add_argument(
        '--docker-url', metavar='<DOCKER_URL>',
        default=os.environ.get('DOCKER_URL', 'http://172.17.42.1:4243'),
        help='Docker URL (defaults to http://172.17.42.1:4243)')
    parser.add_argument(
        '--etcd-host', metavar='<ETCD_HOST>',
        default=os.environ.get('ETCD_HOST', '172.17.42.1'),
        help='Etcd Host (defaults to 172.17.42.1)')
    parser.add_argument(
        '--etcd-port', metavar='<ETCD_PORT>',
        default=os.environ.get('ETCD_PORT', '4001'), type=int,
        help='Etcd Port (defaults to 4001)')
    parser.add_argument(
        '--etcd-base', metavar='<ETCD_BASE>',
        default=os.environ.get('ETCD_BASE', '/yoda'),
        help='Yoda base key (defaults to /yoda)')
    parser.add_argument(
        '--proxy-host', metavar='<PROXY_HOST>',
        default=os.environ.get('PROXY_HOST', '172.17.42.1'),
        help='Proxy Host (defaults to 172.17.42.1. For ec2 , you can also use '
             'metadata. e.g.: ec2:metadata:public-hostname)')
    parser.add_argument(
        '--node-num', metavar='<NODE_NUM>',
        default=os.environ.get('NODE_NUM'),
        help='Node number to be stored as meta-information during discovery')
    parser.add_argument(
        '--service-name', metavar='<SERVICE_NAME>',
        default=os.environ.get('SERVICE_NAME'),
        help='Service name to be stored as meta-information during discovery')
    parser.add_argument(
        'node_name', metavar='<NODE_NAME>', help='Node Name (Container Name)')
    return parser


def main():
    parser = create_parser()
    parsed_args = parser.parse_args()
    parsed_args.proxy_host = map_proxy_host(parsed_args.proxy_host)

    init_shutdown_handler()
    docker_container_poll(parsed_args)


if __name__ == "__main__":
    main()
