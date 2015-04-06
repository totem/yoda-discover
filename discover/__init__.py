import logging

LOG_FORMAT = '[%(name)s] %(levelname)s %(message)s'

logging.basicConfig(format=LOG_FORMAT, level=logging.WARN)
logger = logging.getLogger('yoda-discover')
logger.level = logging.INFO
