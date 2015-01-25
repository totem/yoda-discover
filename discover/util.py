import socket
import re
from urllib.request import urlopen
from boto.utils import get_instance_metadata
from discover import logger

__author__ = 'sukrit'

DEFAULT_TIMEOUT_MS = 2000
DEFAULT_TIMEOUT = '2s'
TIMEOUT_FORMAT = '^\\s*(\d+)(ms|h|m|s)\\s*$'


def port_test(port, host, protocol='tcp', timeout_ms=DEFAULT_TIMEOUT_MS):
    if isinstance(port, str):
        port = int(port)
    sock_type = socket.SOCK_DGRAM if protocol == 'udp' else socket.SOCK_STREAM
    sock = socket.socket(socket.AF_INET, sock_type)
    sock.settimeout(timeout_ms)
    try:
        sock.connect((host, port))
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()
        return True
    except:
        logger.exception('Port test failed for host: %s port: %s.', host, port)
        return False


def http_test(port, host, path='/health', timeout_ms=DEFAULT_TIMEOUT_MS):
    check_url = 'http://%s:%s%s' % (host, port, path)
    try:
        urlopen(check_url, None, timeout_ms)
        return True
    except:
        logger.exception("Deployment test failed for %s", check_url)
        return False


def convert_to_milliseconds(timeout):
    """
    Converts timeout string representation to milliseconds

    :param timeout: Timeout represented as string. e.g: 1m
    :type timeout: str
    :return: timeout in milliseconds
    :rtype: int
    """
    match = re.search(TIMEOUT_FORMAT, timeout)
    if match and len(match.groups()) == 2:
        suffix = match.group(2)
        time = int(match.group(1))
        if suffix == 's':
            return time * 1000
        elif suffix == 'm':
            return time * 60 * 1000
        elif suffix == 'h':
            return time * 60 * 60 * 1000
        else:
            return time  # time in ms
    else:
        logger.warn('Invalid timeout:%s specified. Defaulting to %d ms',
                    timeout, DEFAULT_TIMEOUT_MS)
        return DEFAULT_TIMEOUT_MS


def health_test(port, host, **health_check):
    """
    Should check the health

    :param port: Port to be used for health check
    :type port: int or str
    :param host: Host to be used for health check
    :type host: str
    :keyword uri: HTTP URI To be checked. If not specified, tcp/udp port test
        would be performed.
    :type uri: str
    :keyword timeout: Timeout to be used for health check. Default (2s)
    :type timeout: str
    :keyword protocol: Protocol to be used for port test (tcp or udp)
    :type protocol: str
    :return: boolean value representing if test was successful or not
    :rtype: bool
    """
    uri = health_check.get('uri')
    timeout_ms = convert_to_milliseconds(
        health_check.get('timeout', DEFAULT_TIMEOUT))
    protocol = health_check.get('protocol', 'tcp')

    if uri:
        return http_test(port, host, path=uri, timeout_ms=timeout_ms)
    else:
        return port_test(port, host, protocol=protocol, timeout_ms=timeout_ms)


def map_proxy_host(proxy_host):
    """
    Maps the proxy host to the actual host name. Currently, it supports mapping
    using ec2:meta-data:{meta-data-name}.

    :param proxy_host: String that needs to be mapped.
    :type proxy_host: str
    :return: Mapped host
    :rtype: str
    """
    proxy_host = proxy_host.lower()
    if proxy_host.startswith('ec2:meta-data:'):
        meta_data = proxy_host.replace('ec2:meta-data:', '')
        return get_instance_metadata()[meta_data]
    return proxy_host
