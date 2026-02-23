import json
import os
import time 
import sys
import logging

from datetime import datetime,timedelta
import redis
from rq import Queue

import cv2
import shutil
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

RTSP_URL = os.environ.get('RTSP_URL','NONE')
VIDEO_DIR = os.environ.get('VIDEO_DIR', "NONE")
irds_host = os.getenv('RDS_HOST')
irds_port = os.getenv('RDS_PORT')
irds_psw = os.getenv('RDS_PSW')
irdsq_queue = os.getenv('RDSQ_OUTMSG')

logger.debug( f"===================================")
if RTSP_URL == "NONE":
    logger.debug( f"Не вказано URL rtsp камери")
if VIDEO_DIR == "NONE":
    logger.debug( f"Не вказано шлях до директорії відео")
logger.debug( f"===================================")


logger.debug( "Підключення до Redis (використовуємо змінні з  env)")
redis_conn = redis.Redis(host=irds_host,port=irds_port, password=irds_psw, decode_responses=False)

logger.debug( f"Підключення до черги {irdsq_queue}")
queue = Queue(irdsq_queue, connection=redis_conn)

def notify_worker(file_name):
    """Додає задачу на обробку відео в чергу RQ"""
    try:
        # Припускаємо, що обробник буде функція process_video в іншому модулі
        message_o={"filename": file_name}
        message_s=json.dumps(message_o)
        logger.debug(f"Повідомлення для черги: {message_s}")
        job = queue.enqueue('utils.tasks.crttask_sendmsg',  message_s)
        logger.info(f"Задачу додано в чергу: {job.id} для файлу {file_name}")
    except Exception as e:
        logger.error(f"Помилка черги Redis: {e}")

def upload_file(file_path, blob_name):
    """
    Завантажує файл у Azure Blob Storage.
    """
    try:
        shutil.copyfile( file_path, f'{VIDEO_DIR}/{blob_name}')
        logger.debug("Завантаження завершено!")
        return True
    except Exception as ex:
        logger.debug('Виникла помилка під час завантаження:', ex)
        return False



def main():
    """
    Головна функція обробника
    """
    logger.debug("Читаю налаштування")
    while True:
        logging.info("Спроба підключення до RTSP потоку...")
        cap = cv2.VideoCapture(RTSP_URL)
        
        if cap.isOpened():
            logging.info("З'єднання встановлено успішно.")
            # --- Ініціалізація для запису відео ---
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = None
            is_recording = False
            recording_start_time = None
            RECORDING_DURATION = 30 # Запис 30 секунд

            # --- Ініціалізація детектора фону ---
            fgbg = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
            MIN_AREA = 5000 # Мінімальна площа для виявлення руху

            while True:
                ret, frame = cap.read()
                if not ret:
                    logging.warning("Потік перервався. Спроба перепідключення...")
                    break
                
                # Викликаємо функцію обробки
                # Застосовуємо алгоритм віднімання фону
                fgmask = fgbg.apply(frame)
                
                # Видаляємо шум та знаходимо контури
                fgmask = cv2.erode(fgmask, None, iterations=2)
                fgmask = cv2.dilate(fgmask, None, iterations=2)
                contours, _ = cv2.findContours(fgmask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                motion_detected = False
                
                for contour in contours:
                    if cv2.contourArea(contour) < MIN_AREA:
                        continue
                    
                    motion_detected = True
                    (x, y, w, h) = cv2.boundingRect(contour)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    
                # Логіка запису
                if motion_detected and not is_recording:
                    logger.debug("Рух виявлено! Початок запису.")
                    is_recording = True
                    recording_start_time = time.time()
                    current_filename = time.strftime("%Y%m%d-%H%M%S") + ".avi"
                    out = cv2.VideoWriter(current_filename, fourcc, 20.0, (frame.shape[1], frame.shape[0]))
                
                if is_recording:
                    out.write(frame)
                    if time.time() - recording_start_time >= RECORDING_DURATION:
                        out.release()
                        is_recording = False
                        logger.debug("Запис завершено.")
                        if upload_file(current_filename, current_filename):
                            notify_worker(current_filename)
                            os.remove(current_filename)
                            logger.debug(f"Локальний файл {current_filename} видалено.")     
                # ВАЖЛИВО: У headless режимі cv2.waitKey(1) не потрібен для виводу зображення,
                # але він може бути потрібен для ініціалізації внутрішніх буферів OpenCV.
                # Якщо обробка дуже швидка, можна додати невелику паузу, щоб не вантажити CPU.
                # time.sleep(0.01) 
                
            cap.release()
        else:
            logging.error("Камера недоступна. Наступна спроба через 10 секунд.")
            time.sleep(10)



