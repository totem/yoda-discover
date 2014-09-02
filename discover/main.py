__author__ = 'sukrit'


import docker
import etcd
import os


from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler


__all__ = ['scheduler']

executors = {
    'processpool': ProcessPoolExecutor(4)
}

job_defaults = {

}

ETCD_BASE = os.environ.get('ETCD_BASE', '/yoda')
DOCKER_URL = os.environ.get('DOCKER_URL', 'http://172.17.42.1:8283')
ETCD_HOST = os.environ.get('ETCD_HOST', '172.17.42.1')
ETCD_PORT = int(os.environ.get('ETCD_PORT', '4001'))
PROXY_HOST = os.environ.get('PROXY_HOST', '172.17.42.1')


scheduler = BlockingScheduler(executors=executors, job_defaults=job_defaults)

docker_cl = docker.Client(
    base_url=DOCKER_URL,
   version='1.12',
   timeout=10)

etcd_cl = etcd.Client(host=ETCD_HOST, port=ETCD_PORT)


def fetch_instances():
    for container in docker_cl.containers():
        scheduler.add_job(publish_discover, args=[container])


def parse_container_env(env_cfg):
    parsed_env = dict()
    for env_entry in env_cfg:
        env_name, env_value = env_entry.split('=', 1)
        parsed_env[env_name] = env_value
    return parsed_env

def publish_discover(container):
    container_info = docker_cl.inspect_container(container['Id'])

    if 'Config' in container_info and 'Env' in container_info['Config']:
        env_cfg = container_info['Config']['Env']
        parsed_env = parse_container_env(env_cfg)

        if 'DISCOVER_CLUSTER_NAME' in parsed_env and \
            'DISCOVER_NODE_NAME' in parsed_env:
            cluster = parsed_env['DISCOVER_CLUSTER_NAME']
            node = parsed_env['DISCOVER_NODE_NAME']
            for port_key in container_info['Config']['ExposedPorts']:
                private_port = port_key.split('/')[0]
                public_port = \
                    docker_cl.port(container, private_port)[0]['HostPort']
                upstream = '%s-%s' % (cluster, private_port)
                key = '{etcd_base}/upstreams/{upstream}/endpoints/{node}'\
                    .format(
                        etcd_base=ETCD_BASE, upstream=upstream, node=node)
                value = '%s:%s' % (PROXY_HOST, public_port)
                print('Publishing %s==>%s with ttl 300'%(key, value))
                etcd_cl.set(key, value, 300)


scheduler.add_job(fetch_instances, trigger='cron', second='*/60')
scheduler.start()
