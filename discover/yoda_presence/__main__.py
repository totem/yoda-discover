from discover import map_proxy_host

__author__ = 'sukrit'

import os
import argparse
from discover import logger, map_proxy_host, port_test
import random
import sys
import yoda
import time
import signal


def yoda_client(parsed_args):
    return yoda.Client(etcd_host=parsed_args.etcd_host,
                       etcd_port=parsed_args.etcd_port,
                       etcd_base=parsed_args.etcd_base)


def create_deregister_handler(parsed_args):
    """
    Creates the SIGTERM and SIGINT handler.
    """
    def handler(*args, **kwargs):
        yoda_cl = yoda_client(parsed_args)
        logger.info("Removing proxy node on exit %s", parsed_args.node_name)
        yoda_cl.remove_proxy_node(parsed_args.node_name)
        sys.exit(0)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def discover_proxy_nodes(parsed_ars):
    create_deregister_handler(parsed_args)
    while True:
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Registers proxy nodes to etcd')

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

    parsed_args = parser.parse_args()
    parsed_args.check_ports = parsed_args.check_ports.split(",")
    if parsed_args.check_ports:
        parsed_args.check_ports.split(",")
    else:
        parsed_args.check_ports =[]

    parsed_args.proxy_host = map_proxy_host(parsed_args.proxy_host)
    logger.info('Started yoda presence for  proxy node-> %s:%s',
                parsed_args.node_name, parsed_args.proxy_host)
    discover_proxy_nodes(parsed_args)
