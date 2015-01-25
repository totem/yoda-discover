import logging

LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s %(message)s'
LOG_DATE = '%Y-%m-%d %I:%M:%S %p'


logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.WARN)
logger = logging.getLogger('yoda-discover')
logger.level = logging.INFO
