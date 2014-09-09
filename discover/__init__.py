import logging
import socket
import boto

LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s %(message)s'
LOG_DATE = '%Y-%m-%d %I:%M:%S %p'


logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.WARN)
logger = logging.getLogger('yoda-discover')
logger.level = logging.INFO

def port_test(port, host, protocol='tcp'):
    sock_type = socket.SOCK_DGRAM if protocol == 'udp' else socket.SOCK_STREAM
    sock = socket.socket(socket.AF_INET, sock_type)
    sock.settimeout(2000)
    try:
        sock.connect((host, port))
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()
        return True
    except socket.error as error:
        logger.warn('Port test failed for host: %s port: %s. Reason: %s',
                    host, port, error)
        return False


def map_proxy_host(proxy_host):
    proxy_host = proxy_host.lower()
    if proxy_host.startswith('ec2:meta-data:'):
        meta_data = proxy_host.replace('ec2:meta-data:', '')
        return boto.utils.get_instance_metadata()[meta_data]
    return proxy_host
