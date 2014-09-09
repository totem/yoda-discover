import os
from discover import logger, PROXY_HOST, docker_client, yoda_client, \
    port_test

HOSTED_ZONE_ID = os.environ.get('HOSTED_ZONE_ID')
ROUTE53_RECORD = os.environ.get('ROUTE53_RECORD', 'yoda')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')

DISCOVER_APP_VERSION = os.environ.get('DISCOVER_APP_VERSION', 'v1')
DISCOVER_APP_NAME = os.environ.get('DISCOVER_APP_NAME', 'unspecified')
DISCOVER_NODE_NUMBER = os.environ.get('DISCOVER_NODE_NUMBER', 1)
DISCOVER_CONTAINER = '%s-%s-%d' %(DISCOVER_APP_NAME, DISCOVER_APP_VERSION,
                                  DISCOVER_NODE_NUMBER)