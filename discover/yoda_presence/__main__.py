from discover.util import port_test, map_proxy_host, init_shutdown_handler

import os
import argparse
from discover import logger
import random
import sys
import yoda
import time

__author__ = 'sukrit'


def yoda_client(parsed_args):
    return yoda.Client(etcd_host=parsed_args.etcd_host,
                       etcd_port=parsed_args.etcd_port,
                       etcd_base=parsed_args.etcd_base)


def on_delete(parsed_args):
    yoda_cl = yoda_client(parsed_args)
    logger.info("Removing proxy node on exit %s", parsed_args.node_name)
    yoda_cl.remove_proxy_node(parsed_args.node_name)


def discover_proxy_nodes(parsed_args, poll=None):
    logger.info('Started discovery for proxy node: %s', parsed_args.node_name)
    poll = poll or (lambda: True)
    while poll():
        yoda_cl = yoda_client(parsed_args)
        port_test_passed = True
        for port in parsed_args.check_ports:
            if not port_test(port, parsed_args.proxy_host):
                logger.warn("Port test failed for %s:%s",
                            parsed_args.proxy_host, port)
                port_test_passed = False
                break

        if port_test_passed:
            logger.info("Registering proxy node to etcd: %s with host:%s",
                        parsed_args.node_name, parsed_args.proxy_host)
            yoda_cl.discover_proxy_node(parsed_args.node_name,
                                        host=parsed_args.proxy_host)
        else:
            logger.info("Removing proxy node (port test failed) %s",
                        parsed_args.node_name)
            yoda_cl.remove_proxy_node(parsed_args.node_name)

        time.sleep(parsed_args.poll_interval)


def create_parser():
    parser = argparse.ArgumentParser(
        description='Registers proxy nodes to etcd')

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
        '--check-ports', metavar='<CHECK_PORTS>',
        default=os.environ.get('CHECK_PORTS', '80'),
        help='Comma separated ports to be used for status check. '
             'Defaults to 80')
    parser.add_argument(
        '--node-name', metavar='<PROXY_NODE_NAME>',
        help='Identifier for the proxy node',
        default=random.randint(0, sys.maxsize))

    parser.add_argument(
        '--poll-interval', metavar='<POLL_INTERVAL">',
        help='Poll interval in seconds', type=int,
        default=180)

    parser.add_argument(
        'proxy_host', metavar='<PROXY_HOST>',
        help='Proxy host that needs to be registered.')

    return parser


def main():
    parser = create_parser()
    parsed_args = parser.parse_args()
    if parsed_args.check_ports:
        parsed_args.check_ports = [valid_port for valid_port in
                                   [port.strip() for port in
                                    parsed_args.check_ports.split(",")]
                                   if valid_port]
    else:
        parsed_args.check_ports = []

    parsed_args.proxy_host = map_proxy_host(parsed_args.proxy_host)
    init_shutdown_handler(on_delete, args=(parsed_args,))
    discover_proxy_nodes(parsed_args)


if __name__ == "__main__":
    main()
