from datetime import datetime,timedelta
import time 
import json
import random
import requests

import os
import sys
import traceback
import logging


import redis
import rq
from rq import Queue

import cv2
from ultralytics import YOLO
import torch
import os

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


LOG_FILE = os.path.join(os.environ.get('VIDEO_DIR', '/app/video'), 'detections_log.jsonl')
MODEL_PATH = "/usr/src/app/yolov8n.pt"
#MODEL_PATH = "../app/yolov/yolov8n.pt"
logger.debug(f"Модель завантажується з локального файлу: {MODEL_PATH}")
if os.path.exists(MODEL_PATH):
    yolo_model = YOLO(MODEL_PATH)
    logger.debug("Модель успішно завантажено з локального файлу.")
else:
    logger.debug(f"Помилка: Файл моделі не знайдено за шляхом {MODEL_PATH}")
logger.debug(f"YOLO model ready: {yolo_model.info()}")

def save_to_log(data):
    # Додаємо мітку часу
    data['timestamp'] = datetime.now().isoformat()
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')


def crttask_sendmsg( message ):
    process_result = {}     

    if yolo_model is None:
        process_result["ok"] = False
        process_result["error"] = "Model not loaded"
        logger.error( process_result["error"] )
        return process_result

    try:
        data = json.loads(message) if isinstance(message, str) else message
        filename = data.get('filename')
        
        # ВАЖЛИВО: Переконайтеся, що шлях VIDEO_DIR однаковий 
        # у capture_service та worker_service (спільний volume)
        video_path = os.path.join(os.environ.get('VIDEO_DIR', '/app/video'), filename)
        
        if not os.path.exists(video_path):
                return {"ok": False, "error": f"File {video_path} not found"}

        cap = cv2.VideoCapture(video_path)
        found_objects = []
        frame_number = 0

        while cap.isOpened():
                ret, frame = cap.read()
                if not ret: break
                
                # Запускаємо YOLO на кадрі
                results = yolo_model(frame, conf=0.5, verbose=False)
                
                for r in results:
                        for box in r.boxes:
                                cls_id = int(box.cls[0])
                                label = yolo_model.names[cls_id]
                                if label not in found_objects:
                                        found_objects.append(label)
        
        cap.release()
        
        logger.info(f"Обробка {filename} завершена. Знайдено: {found_objects}")
        result= {"ok": True, "filename": filename,"detected": found_objects, 'count': len(found_objects) }
        # Зберігаємо для аналізу в Jupyter
        save_to_log(result)
        
        return {"ok": True, **result}
        
    except Exception as e:
        logger.error(f"Помилка обробки: {str(e)}")
        return {"ok": False, "error": str(e)}



