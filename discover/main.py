__author__ = 'sukrit'


import docker
import os
import yoda
import logging
import json
import time


from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler


__all__ = ['scheduler']

executors = {
    'processpool': ProcessPoolExecutor(4)
}

job_defaults = {

}


ETCD_BASE = os.environ.get('ETCD_BASE', '/yoda')
DOCKER_URL = os.environ.get('DOCKER_URL', 'http://172.17.42.1:4243')
ETCD_HOST = os.environ.get('ETCD_HOST', '172.17.42.1')
ETCD_PORT = int(os.environ.get('ETCD_PORT', '4001'))
PROXY_HOST = os.environ.get('PROXY_HOST', '172.17.42.1')

LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s %(message)s'
LOG_DATE = '%Y-%m-%d %I:%M:%S %p'
DOCKER_POLL_RESTART_SECONDS=10

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.WARN)

logger = logging.getLogger('yoda-discover')
logger.level = logging.INFO



scheduler = BlockingScheduler(executors=executors, job_defaults=job_defaults)

docker_cl = docker.Client(
    base_url=DOCKER_URL,
    version='1.12',
    timeout=10)

yoda_cl = yoda.Client(etcd_host=ETCD_HOST, etcd_port=ETCD_PORT,
                      etcd_base=ETCD_BASE)


def parse_container_env(env_cfg):
    parsed_env = dict()
    for env_entry in env_cfg:
        env_name, env_value = env_entry.split('=', 1)
        parsed_env[env_name] = env_value
    return parsed_env

def handle_discover(container_id):
    container_info = docker_cl.inspect_container(container_id)

    if 'Config' in container_info and 'Env' in container_info['Config']:
        env_cfg = container_info['Config']['Env']
        parsed_env = parse_container_env(env_cfg)

        if 'DISCOVER_CLUSTER_NAME' in parsed_env and \
                'DISCOVER_NODE_NAME' in parsed_env:
            cluster = parsed_env['DISCOVER_CLUSTER_NAME']
            node = parsed_env['DISCOVER_NODE_NAME']
            for port_key in container_info['Config']['ExposedPorts']:
                private_port = port_key.split('/')[0]
                upstream = '%s-%s' % (cluster, private_port)

                if container_info['State']['Running']:
                    public_port = \
                        docker_cl.port(container_id,
                                       private_port)[0]['HostPort']
                    endpoint = yoda.as_endpoint(PROXY_HOST, public_port)
                    logger.info('Publishing %s : %s', node, endpoint)
                    yoda_cl.discover_node(upstream, node, endpoint)
                else:
                    logger.info('Removing node %s : %s', upstream, node)
                    yoda_cl.remove_node(upstream, node)


def handle_poll_event(event):
    event_dict = json.loads(event)
    scheduler.add_job(handle_discover, args=[event_dict['id']])



def docker_instances_poll():
    for container in docker_cl.containers(all=True):
        scheduler.add_job(handle_discover, args=[container['Id']])

def docker_event_poll():
    while(True):
        try:
            #Poll for all instances for first run (before event polling)
            docker_instances_poll()
            logger.info('Start polling for docker events....')
            for event in docker_cl.events():
                logger.info('%s', event)
                handle_poll_event(event)

        except:
            logger.exception(
                'Error happened while polling for docker events. Restarting '
                'polling in %ds' % DOCKER_POLL_RESTART_SECONDS)
            time.sleep(DOCKER_POLL_RESTART_SECONDS)




#Instance Polling to capture an
#scheduler.add_job(docker_instances_poll, trigger='cron', hour='*/1')
scheduler.add_job(docker_event_poll)
scheduler.start()
