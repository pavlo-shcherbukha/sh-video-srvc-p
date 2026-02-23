# video streaming через підключення IP камери по ротоколу  rtsp з наступним аналізом відео вже готовою нейренною мережею

В цьому репозиторії наведено  прототип системи, що отримує  RTSP-відеотрафік з IP камери чи її емулятара. Програмно виконує детекцію руху. Якщо рух виявлено, то система виконує запис 30-секундного відео та його збереження на shared диску. Після закінчення запису відеофайлу, система  публікує повідомлення через Redis іншому обробнику, що обробляє отримане відео за допомогою нейромережі YOLO8 від ultralytics  та записує інформацію про результати детектування об'єктів в кадрах в JSON-LOG.
Також система має можливості аналізу отриманих даних, тестування та  моніторингу роботи за допомогою Jupyter Lab. 

Крожен компонент систем, окрім камери, запускається в окремому контейнері, а всі контейнери зв'язані в єдиний додаток з допомогою Docker-Composer.

Компонентна архітектура системи показана на малюнку. В кожному компоненті коротко описані його функції. Якщо є бажання використати USB-камеру ноутбука, то її треба запускати через емулятор RTSP  потока, що наведено за ліноком [sh-usbcam-as-rtsp](https://github.com/pavlo-shcherbukha/sh-usbcam-as-rtsp).

```mermaid
graph TD
    subgraph "Video Sources (RTSP Streams)"
        A1[Mobile App Camera] -->|RTSP| B
        A2[IP Camera - Tapo/Hikvision] -->|RTSP| B
        A3[Laptop USB Cam + Emulator] -->|sh-usbcam-as-rtsp| B
    end

    subgraph "Docker Container: video-capture"
        B[vcam_wrkr.py] -->|1. Motion Detection| C{Motion?}
        C -->|Yes| D[Record .avi]
        D -->|2. Save to Volume| E[(Shared Docker Volume)]
        D -->|3. Push Task| F[Redis Queue]
    end

    subgraph "Middleware"
        F --> G[Redis Server]
    end

    subgraph "Docker Container: video-worker"
        G -->|4. Fetch Task| H[video_wrkr.py]
        H -->|5. Load Model| I[tasks.py / YOLOv8]
        E -->|6. Read Video| I
        I -->|7. Analyze| J[Detection Results]
        J -->|8. Append| K[(detections_log.jsonl)]
    end

    subgraph "Analysis Layer"
        K --> L[Jupyter Notebook]
        L -->|9. Analytics| M[Pandas / Matplotlib Charts]
    end

    style G fill:#f9f,stroke:#333,stroke-width:2px
    style I fill:#bbf,stroke:#333,stroke-width:2px
    style L fill:#dfd,stroke:#333,stroke-width:2px
```

## Обладнання для  запуску та тестування

Для запуску та тестування знадобиться IP-камера, яка підтримує rtsp- протокол взаємодії. За звичай, його підтримують камери TP-LINK серії TAPO. В крайньому випадку для тестування та проб підійде мобільний телефон з встановленим додатком ip-camera [pic-01](#pic-01). Тільки треба мати на увазі, що телефони, особливо старі, довго працювати в режимі камери за rptsp протоколом мабуть не будуть бо  то перегріваються, то пам'яті не вистачає. З мого досвіду - ну хвилин на 5-6 безперервної роботи телефону вистачить, а далі як повезе. Але для тестування цього більш ніж достатньо.
Звичайно камера чи телефон  повинні бути підключеними до одного і того ж роутера щоб всі компоненти взаємодіяли між собою. 
<kbd><img src="doc/ipcam.jpg" /></kbd>
<p style="text-align: center;"><a name="pic-01">pic-01</a></p>

Використання RTSP трафіку вигідно, тому що легко можна запустити всі компоненти на в контейнерах чи віртуалках


## Особливості побудови Docker образів (images)

Всі компоненти запускаються за допомогою Docker-Composer. Але такі бібліотеки як ultralytics чи opencv  досить важкі і займають багато часу на встановлення. Тому тут використано такий підхід:
- Збираємо один раз базовий образ, який напаковуємо "важкими" бібліотеками. Цей образ описано в файлі [Dockerfile.base.dockerfile](./Dockerfile.base.dockerfile), а перелік бібліотек, що на ньому встановлюються описано в файлі [requirements.base.txt](./requirements.base.txt).

Побудувати образ можна класичною командою **docker build**:

```bash
docker build -t data-pipeline-base:latest -f Dockerfile.base.dockerfile .
```

- З нього будуємо 3 моленьких, які, безпосердньо і запускаємо через docker composer:

1. [Dockerfile.capture](./Dockerfile.capture) - з нього запускається контейнер що приймає відеотрафік з камери та виконує детекцію руху. На малюнку архітектури це **"Docker Container: video-capture"**.

2. [Dockerfile.video](./Dockerfile.video) - з нього запускається обробник, що пропускає кадри відео через нейромережу YOLO8, та записує результати в Json-лог.  На малюнку архітектури це **video-worker**.

3. [Dockerfile.jupyter](./Dockerfile.jupyter) - з нього запускається jupyter lab.  На малюнку архітектури це **Analysis Layer**.

Усі ці контейнери побудовані за спільними правилами. Тут наведено приклад **Dockerfile.capture**  з коментарями по кожному важливому рядку 

```dockerfile
# Використовуємо ваш уже зібраний базовий образ
FROM data-pipeline-base:latest

# Встановлення робочої директорії
WORKDIR /app

# Копіювання моделі (що вона вже є в корені проекту), але треба перенсти в поточний шар
RUN cp /usr/src/app/yolov8n.pt .

# Копіювання та встановлення специфічних залежностей (поки що порожній файл)
COPY requirements.capture.txt .
RUN pip install --no-cache-dir -r requirements.capture.txt

# копіювання коду обробника повідомлень з черги Redis
# навіть якщо контейнер публікує повідомлення, то цей обробник повинен бути пристнім, тому тримаю одну версію коду в shared_utils, а копіюю на кодний образ.
COPY ./shared_utils ./utils

# Копіювання коду обробника : спочатку папку з модулями, потім основний скрипт
COPY ./vcam_worker ./vcam_worker
COPY vcam_runner.py .

# Команда запуску
CMD ["python", "vcam_runner.py"]

```

Про Redis  тут не згадую, тому що його використовуємо, як є.

## Особливості побудови docker-composer

Опис Docker-composer знаходиться в файлі [docker-compose.yml](./docker-compose.yml).


```yaml
services:
  # Сервіс Redis
  redis:
    image: redis:6-alpine
    container_name: redis_video_queue
    ports:
      - "6379:6379"
    command: redis-server --requirepass ${REDIS_PASSWORD:-22}
    volumes:
      - ./redis_data:/data
    restart: always

  # Сервіс захоплення відео (використовує свій Dockerfile)
  video-capture:
    build:
      context: .
      dockerfile: Dockerfile.capture # Вкажіть назву файлу для цього сервісу
    container_name: video_capture_service
    env_file:
      - videocapure.env
    volumes:
      - ./video:/app/video
      - ./shared_utils:/app/utils
    depends_on:
      - redis

  # Jupyter Lab (використовує інший Dockerfile)
  jupyter:
    build:
      context: .
      dockerfile: Dockerfile.jupyter # Окремий файл для Jupyter
    container_name: jupyter_debug
    ports:
      - "8888:8888"
    volumes:
      - ./notebooks:/app
      - ./video:/app/video # Додайте доступ до відео для аналізу в ноутбуках
      - ./shared_utils:/app/utils
      
    environment:
      - RDS_HOST=redis
      - RDS_PORT=6379
      - RDS_PSW=${REDIS_PASSWORD:-22}
      - RDSQ_OUTMSG='video_queue'

  video-worker:
      build:
        context: .
        dockerfile: Dockerfile.video
      env_file:
        - videoworker.env  
      # Перезаписуємо CMD, щоб запустити саме воркер
      command: python video_runner.py 
      volumes:
        - ./video:/app/video
        - ./shared_utils:/app/utils
      depends_on:
        - redis

```

- Для сервіса Redis використовуємо volum ./redis_data,  для того, щоб він міг скидати туди свій кеш з пам'ятію

- Сервіс захоплення відео (використовує свій Dockerfile **video-capture**

Тут треба звернути увагу, з якого dockerfile він збирається. Прарметризацію контейнеру виконується через ENV-змінні, що описані у файлі: **videoworker.env**

```text

# Налаштування камери
## URL камери
RTSP_URL=rtsp://username:password@host:port/path
##  найменування shared folder де зберігаються записані відео
VIDEO_DIR=video

# Налаштування Redis
RDS_HOST=redis
RDS_PORT=6379
RDS_PSW=<password>
RDSQ_OUTMSG='video_queue'

```

Використовуються два  volumes:
- ./video:/app/video - куди зберігаємо записані відео
- ./shared_utils:/app/utils - де зберігаються спільні модулі (він там один)


- Jupyter Lab (використовує інший Dockerfile) **jupyter**  

Тут, із особливостей уже 3 volumes:
- ./notebooks:/app # зберігаються Jupyter notebooks
- ./video:/app/video # куди зберігаються  відео для аналізу та JSON-файл з логом обробки
- ./shared_utils:/app/utils де зберігаються спільні модулі (він там один)

Env змінні записані прямо в тексті yaml-файла


Попасти в web-інтерфейс Jupyter Lab  можна за URL: http://localhost:8888/


- Сервіс обробки відео **video-worker**:

Особливості його побудови аналогічні сервісу: video-capture
Для парамтеризації використовується env-file [videoworker.env](./videoworker.env)

```text
# Налаштування Redis
RDS_HOST=redis
RDS_PORT=6379
RDS_PSW=<password>
RDSQ_OUTMSG='video_queue'
# Налаштування YOLO
YOLO_CONFIG_DIR=/tmp/ultralytics_config
```

Файл [yolov8n.pt](./yolov8n.pt) якраз і є модель нейромережі. Але його не скачуємо кожний раз з інтренета, бо це довго, а скачали один раз і поклали локально.
 
## Запуск, зупинка та модифікація  в Docker Composer


- запуск

```bash
# щоб бачити всі логи
docker compose up

# щоб запустити відокремлено
docker compose up -d

```

- Зупинка

```bash
docker compose down

```

При зупинці  контейенри видаляються:

```text
 ✔ Container jupyter_debug                 Removed                                    1.3s 
 ✔ Container video_capture_service         Remov...                                  10.2s 
 ✔ Container sh-video-srvc-video-worker-1  Removed                                    0.7s 
 ✔ Container redis_video_queue             Removed                                    0.3s 
 ✔ Network sh-video-srvc_default           Removed                                    0.1s 
 ```

Якщо ви змінили код, то треба видалити образи:

```bash
docker image rm sh-video-srvc-video-worker
docker image rm sh-video-srvc-video-capture
docker image rm sh-video-srvc-jupyter

```

## Трошки про програмні модулі

- В модулі [/vcam_worker/vcam_wrkr.py](./vcam_worker/vcam_wrkr.py) знаходиться код прийому даних з камери, детекції руху та публікації повідомлення в чергу Redis

- В модулі [/video_worker/video_wrkr.py](./video_worker/video_wrkr.py) знаходиться код підлючення до Redis, як consumer.

- В модулі [/shared_utils/tasks.py](./shared_utils/tasks.py) знаходиться код, що безпосередньо обробляє повідомлення з Redis, виконує аналіз відео та пише лог аналізу.

Лог має такий вигляд [/video/detections_log.jsonl](./video/detections_log.jsonl)

```text
{"ok": true, "filename": "20260223-144657.avi", "detected": [], "count": 0, "timestamp": "2026-02-23T14:47:56.697779"}
{"ok": true, "filename": "20260223-144819.avi", "detected": ["person", "tv", "microwave", "oven", "keyboard"], "count": 5, "timestamp": "2026-02-23T14:49:15.581433"}
{"ok": true, "filename": "20260223-144923.avi", "detected": ["tv"], "count": 1, "timestamp": "2026-02-23T14:50:21.171055"}
{"ok": true, "filename": "20260223-144953.avi", "detected": ["person", "bicycle", "cow"], "count": 3, "timestamp": "2026-02-23T14:50:53.121085"}
{"ok": true, "filename": "20260223-145148.avi", "detected": ["tv", "person", "cat"], "count": 3, "timestamp": "2026-02-23T14:52:49.402444"}
{"ok": true, "filename": "20260223-145218.avi", "detected": ["cow", "person", "cat"], "count": 3, "timestamp": "2026-02-23T14:53:18.309112"}
{"ok": true, "filename": "20260223-145543.avi", "detected": [], "count": 0, "timestamp": "2026-02-23T14:57:01.068093"}
{"ok": true, "filename": "20260223-150244.avi", "detected": [], "count": 0, "timestamp": "2026-02-23T15:04:00.787072"}

```

- В папці [/notebooks](./notebooks/) - нведені такі notebooks

1. [CheckJupyter.ipynb](./notebooks/CheckJupyter.ipynb) - перевірити, що notebook запускається
2. [RedisConnectionTest.ipynb](./notebooks/RedisConnectionTest.ipynb) - перевірити підключення до Redis
3. [ViewProcessResuts.ipynb](./notebooks/ViewProcessResuts.ipynb) - переглянути лог роботи та розрахувати аналітику.


## Чому зроблено так і які майбутні перспекитив прототипа

Якщи є необхідність працювати з великим даними чи з комп'ютеним зором чи з навчанням нейромереж, то у нас появляється багато речей які вимагають важких обчислень. Виникає необходність обробляти велику кількість зображень. І, відповідно, виникає необхідність аналізувати ті великі об'єми даних або виконувати якість утилітарні задачі: 
- запустити тренування мережі
- завантажити в колецію  фотографію (фотграфії) для розмітки. 
Всі ці речі можна зробити повторбваними з поясненнями, не породжуючи великої кількості утиліт, утиліток і скриптів.  Тому це приклад найпростішого toolchain який можна модифікувати чи розширяти під потреби конкретного алгоритму.