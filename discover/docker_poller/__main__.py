__author__ = 'sukrit'


import docker
import os
import yoda
import json
import datetime
import socket


from apscheduler.executors.pool import ProcessPoolExecutor, ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from discover import logger, port_test


DISCOVER_POOL_SIZE = int(os.environ.get('DISCOVER_POOL_SIZE', '3'))
DOCKER_POLL_RESTART_SECONDS = 60

ETCD_BASE = os.environ.get('ETCD_BASE', '/yoda')
DOCKER_URL = os.environ.get('DOCKER_URL', 'http://172.17.42.1:4243')
ETCD_HOST = os.environ.get('ETCD_HOST', '172.17.42.1')
ETCD_PORT = int(os.environ.get('ETCD_PORT', '4001'))
PROXY_HOST = os.environ.get('PROXY_HOST', '172.17.42.1')

executors = {
    # Default Pool for event streaming and docker instances poll
    'default': ThreadPoolExecutor(2),
    # Process poll for inpsecting docker container and publishing to etcd.
    'processpool': ProcessPoolExecutor(DISCOVER_POOL_SIZE)
}

job_defaults = {

}

scheduler = BlockingScheduler(executors=executors, job_defaults=job_defaults)


def docker_client():
    return docker.Client(
        base_url=DOCKER_URL,
        version='1.12',
        timeout=10)


def yoda_client():
    return yoda.Client(etcd_host=ETCD_HOST, etcd_port=ETCD_PORT,
                       etcd_base=ETCD_BASE)

def parse_container_env(env_cfg):
    parsed_env = dict()
    for env_entry in env_cfg:
        env_name, env_value = env_entry.split('=', 1)
        parsed_env[env_name] = env_value
    return parsed_env


def handle_discover(container_id):
    docker_cl = docker_client()
    yoda_cl = yoda_client()
    container_info = docker_cl.inspect_container(container_id)
    if 'Config' in container_info and 'Env' in container_info['Config']:
        env_cfg = container_info['Config']['Env']
        parsed_env = parse_container_env(env_cfg)

        if 'DISCOVER_APP_VERSION' in parsed_env and \
                'DISCOVER_APP_NAME' in parsed_env and \
                'DISCOVER_NODE_NAME' in parsed_env:
            app = parsed_env['DISCOVER_APP_NAME']
            version = parsed_env['DISCOVER_APP_VERSION']
            node = parsed_env['DISCOVER_NODE_NAME']
            for port_key in container_info['Config']['ExposedPorts']:
                private_port, protocol = port_key.split('/')
                upstream = yoda.as_upstream(app, version, private_port)

                if container_info['State']['Running']:
                    public_port = \
                        docker_cl.port(container_id,
                                       private_port)[0]['HostPort']
                    if port_test(int(public_port), PROXY_HOST, protocol):
                        endpoint = yoda.as_endpoint(PROXY_HOST, public_port)
                        logger.info('Publishing %s : %s', node, endpoint)
                        yoda_cl.discover_node(upstream, node, endpoint)
                    else:
                        logger.info('Removing failed node %s : %s',
                                    upstream, node)
                        yoda_cl.remove_node(upstream, node)
                else:
                    logger.info('Removing (Not running) node %s : %s',
                                upstream, node)
                    yoda_cl.remove_node(upstream, node)


def schedule_discover_job(container_id):
    logger.info('Scheduling discover job for container: %s', container_id)
    scheduler.add_job(handle_discover, args=[container_id],
                      executor='processpool',
                      misfire_grace_time=300,
                      next_run_time=datetime.datetime.now())



@scheduler.scheduled_job(
    trigger='cron', minute='*/1', next_run_time=datetime.datetime.now(),
    misfire_grace_time=5, executor='default')
def docker_instances_poll():
    for container in docker_client().containers():
        schedule_discover_job(container['Id'])


#Adding as a scheduled job so that it will automatically restart if docker
#polling gets interrupted
@scheduler.scheduled_job(
    trigger='cron', hour='*/1', next_run_time=datetime.datetime.now(),
    misfire_grace_time=5, executor='default')
def docker_event_poll():
    #Poll for all instances for first run (before event polling)
    #docker_instances_poll()
    logger.info('Start polling for docker events....')
    for event in docker_client().events():
        logger.info('%s', event)
        event_dict = json.loads(event)
        schedule_discover_job(event_dict['id'])

if __name__ == "__main__":
    scheduler.start()
