import os
import tempfile
import time 
import json
import sys

import logging

from datetime import datetime,timedelta
import uuid

import redis
from rq import Worker, Queue

from utils import tasks

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
logger = logging.getLogger(__name__)

apploglevel=os.environ.get("LOGLEVEL")
if apploglevel==None:
    logger.setLevel(logging.DEBUG)
elif apploglevel=='DEBUG':
    logger.setLevel(logging.DEBUG)    
elif apploglevel=='INFO':
    logger.setLevel(logging.INFO)    
elif apploglevel=='WARNING':
    logger.setLevel(logging.WARNING)    
elif apploglevel=='ERROR':    
    logger.setLevel(logging.ERROR)    
elif apploglevel=='CRITICAL':
    logger.setLevel(logging.CRITICAL)    
else:
    logger.setLevel(logging.DEBUG)  

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
if not logger.handlers:
    logger.addHandler(stream_handler)

logger.debug("debug message")





irds_host = os.getenv('RDS_HOST')
irds_port = os.getenv('RDS_PORT')
irds_psw = os.getenv('RDS_PSW')
irds_queue = os.getenv('RDSQ_OUTMSG')


def main():
    """
    Головна функція обробника
    """
    logger.debug("Читаю налаштування")

    red = redis.StrictRedis(irds_host, irds_port, password=irds_psw, decode_responses=False)

    # Створюємо список об'єктів Queue правильно
    # Для кожної назви черги в listen створюємо об'єкт Queue з підключенням
    listen = [irds_queue]
    queues = [Queue(irds_queue, connection=red) for name in listen]
    
    logger.debug(f"running worker for queues: {listen}")

    # Ініціалізація клієнта черги
    try:
        logger.debug("Починаю роботу воркера")
        # Передаємо вже створені об'єкти черг у воркер
        # Параметр connection=red тут також бажано залишити
        worker = Worker(queues, connection=red)
        process_result=worker.work(logging_level=logging.DEBUG)
        logger.debug(f"Робота воркера завершена з результатом: {process_result}")
  
    except Exception as e:
        logger.error(f"Помилка під час роботи воркера: {e}")   



  