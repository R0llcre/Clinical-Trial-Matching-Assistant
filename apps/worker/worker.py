import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("worker started")

while True:
    time.sleep(60)
