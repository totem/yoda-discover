"""
Syncs yoda etcd proxy nodes with route53
"""

import yoda
import argparse
from discover import logger


def yoda_client(parsed_args):
    return yoda.Client(etcd_host=parsed_args.etcd_host,
                       etcd_port=parsed_args.etcd_port,
                       etcd_base=parsed_args.etcd_base)


def route53_sync(parsed_args):

    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Syncs route53 nodes with etcd')

    parser.add_argument(
        '--etcd-host', metavar='<ETCD_HOST>',
        default='172.17.42.1',
        help='Docker URL (defaults to 172.17.42.1)')
    parser.add_argument(
        '--etcd-port', metavar='<ETCD_PORT>',
        default='4001', type=int,
        help='Docker URL (defaults to 4001)')
    parser.add_argument(
        '--etcd-base', metavar='<ETCD_BASE>',
        default='/yoda',
        help='Yoda base key (defaults to /yoda)')
    parser.add_argument(
        '--check-ports', metavar='<CHECK_PORTS>', default='4243',
        help='Comma separated ports to be used for status check. '
             'Defaults to 80')
    parser.add_argument(
        '--poll-interval', metavar='<POLL_INTERVAL">',
        help='Poll interval in seconds', type=int,
        default=180)

    parsed_args = parser.parse_args()
    parsed_args.check_ports = parsed_args.check_ports.split(",")
    logger.info('Started sync for yoda proxy nodes with route53')
    route53_sync(parsed_args)