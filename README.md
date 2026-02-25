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

Для запуску та тестування знадобиться IP-камера, яка підтримує rtsp- протокол взаємодії. За звичай, його підтримують камери TP-LINK серії TAPO. В крайньому випадку для тестування та проб підійде мобільний телефон з встановленим додатком ip-camera [ipcam-01](#pic-01). Тільки треба мати на увазі, що телефони, особливо старі, довго працювати в режимі камери за rptsp протоколом мабуть не будуть бо  то перегріваються, то пам'яті не вистачає. З мого досвіду - ну хвилин на 5-6 безперервної роботи телефону вистачить, а далі як повезе. Але для тестування цього більш ніж достатньо.
Звичайно камера чи телефон  повинні бути підключеними до одного і того ж роутера щоб всі компоненти взаємодіяли між собою. 
<kbd><img src="doc/ipcam.jpg" /></kbd>
<p style="text-align: center;"><a name="ipcam-01">ipcam-01</a></p>

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
2. [SendProcessFile.ipynb](./notebooks/SendProcessFile.ipynb) - Відправити на обробку video-worker уже існуючий в каталозі video файл
3. [IsoletedFileProcessing](./notebooks//IsoletedFileProcessing) - викоати оброку файла  в обхід обробника video-worker, напряму прочивши повідомлення через [tasks.py](/shared_utils/tasks.py) і праямо в Jupyter Notebook побачити його лог оброки
4. [ViewProcessResuts.ipynb](./notebooks/ViewProcessResuts.ipynb) - переглянути лог роботи та розрахувати аналітику.


## Чому зроблено так і які майбутні перспекитив прототипа

Якщи є необхідність працювати з великим даними чи з комп'ютеним зором чи з навчанням нейромереж, то у нас появляється багато речей які вимагають важких обчислень. Виникає необходність обробляти велику кількість зображень. І, відповідно, виникає необхідність аналізувати ті великі об'єми даних або виконувати якість утилітарні задачі: 
- запустити тренування мережі
- завантажити в колецію  фотографію (фотграфії) для розмітки. 
Всі ці речі можна зробити повторбваними з поясненнями, не породжуючи великої кількості утиліт, утиліток і скриптів.  Тому це приклад найпростішого toolchain який можна модифікувати чи розширяти під потреби конкретного алгоритму.

## Як швидко стартонути

Додаток в репозиторії поставляється готовим і параметризованим. Файли env-зміннних налаштовані. Єдине що треба зробити - треба налаштувати URL камери в файлі [videocapure.env](./videocapure.env). 

Додаток розгортався і запкускався на віртуалці UBUBUNTU що запущена під  Hyper-V на Windwos машині.

### Підхід до налаштування камери

1. Якщо використовуємо камеру ноутбука та емелятор RTSP  потока.
На Windows-машині  треба запустити [python Flask WebService - прогарму емуляціі RTSP](https://github.com/pavlo-shcherbukha/sh-usbcam-as-rtsp). 

Якщо  налаштувати все, як описано в інструкції, то запустивши сервіс по URL; http://localhost:8080/videotest відкриється html сторінка з потокм вашої камери. А RTSP-потік  буде передаватися по URL: http://ip-host:8080/video. Якщо контейнера запущені на тій же windwos машині,то  ваш IP  то 127.0.0.1 або localhost. Якщо ж у вас контейнери запущені на віртуалці, то вам треба визначити IP вашої host-шини. За звичай цей  не той IP, що отриманий від роутера.  Це IP внутрішньої мережі windows host машина - віртуалка і він починається на 172.*.*.*. На малюнку показно результат роботи комнади wiwndows:

```bash

ipconfig
```

, що дозволяє визначити ip машини з камерою

<kbd><img src="doc/pic-01.png" /></kbd>
<p style="text-align: center;"><a name="pic-01">pic-01</a></p>

Якщо визначився ip windows host машини 172.0.0.22, то для отримання ip потоку треба в  [videocapure.env](./videocapure.env) налаштувати змінну **RTSP_URL**

```env
RTSP_URL=http://ip-host:8080/video
```

Емулятор працює без авторизації. 


2. Якщо використовуємо камеру мобільного телефона і мобільний додатко ip-camera

<kbd><img src="doc/ipcam.jpg" /></kbd>
<p style="text-align: center;"><a name="ipcam-01">ipcam-01</a></p>

То потрібно зайти в Setting та встановити логін та пароль для RTSP трафіка

<kbd><img src="doc/pic-02.jpg" /></kbd>
<p style="text-align: center;"><a name="pic-02">pic-02</a></p>


Далі перходимо в основний екран додатку, і запускаємо камеру:

<kbd><img src="doc/pic-03.jpg" /></kbd>
<p style="text-align: center;"><a name="pic-03">pic-03</a></p>


При запуску можна побачити реальний URL камери:

<kbd><img src="doc/pic-04.jpg" /></kbd>
<p style="text-align: center;"><a name="pic-04">pic-04</a></p>

та на одатко потрібно додати параметри авторизації з [pic-02](#pic-02)

Налаштувати змінної **RTSP_URL** буде виглядати приблизно так

```env
RTSP_URL=rtsp://user:password@ip-camera:8554/live
```


2. Якщо використовуємо камеру tapo TC60 чи щось подібне

Треба встановити мобільний додаток до камери

- Відкрийте додаток Tapo.

- Перейдіть у Налаштування камери (значок шестірні у верхньому правому куті вікна трансляції).

- Виберіть пункт Додаткові налаштування (Advanced Settings).

- Натисніть на Обліковий запис камери (Camera Account).

- Створіть ім'я користувача та пароль. Збережіть їх, вони знадобляться для RTSP-посилання.

- Дізнайтеся IP-адресу камери

Вона потрібна для адресації запиту: У налаштуваннях камери перейдіть у розділ Інформація про пристрій (Device Info).

- Знайдіть рядок IP-адреса (наприклад, 192.168.1.50).

- Формат RTSP-посилання

Тепер зберіть посилання докупи. Для Tapo TC60 воно виглядає так:

    Для високої якості (Stream 1):
    rtsp://ваше_ім'я:ваш_пароль@IP-адреса:554/stream1

    Для низької якості (Stream 2):
    rtsp://ваше_ім'я:ваш_пароль@IP-адреса:554/stream2

**Приклад**:
Якщо ваш логін admin, пароль Pass123, а IP камери 192.168.1.50, посилання буде таким:
rtsp://admin:Pass123@192.168.1.50:554/stream1

Налаштувати змінної **RTSP_URL** буде виглядати приблизно так

```env
RTSP_URL=rtsp://admin:Pass123@192.168.1.50:554/stream1
```


### Запуск додатку

1. Побудувати базовий  образ  на який встановляться "важкі" бібліолтеки.

Побудова виконується командою:

```bash
docker build -t data-pipeline-base:latest -f Dockerfile.base.dockerfile .
```

Доки вона виконується, можна заварити каву, тому що виконуватися воно буде хвили 10-15.
В результаті успішного виконання ви повинні побачити зібраний образ. Подивтитися можна командою:

```bash
docker image ls

```
Команда поверен список всіх образів, але серед них треба знайти **data-pipeline-base **

```text

docker image ls
REPOSITORY                                       TAG        IMAGE ID       CREATED        SIZE
data-pipeline-base                               latest     2d76c2693081   2 days ago     9.85GB

```

2. Запустити docker compose

Запускається комадню

```bash

 docker compose up -d

```

Запуск  в терміналі буде відображатися приблизно так

```text
$ docker compose up -d
[+] Running 5/5
 ✔ Network sh-video-srvc_default           Created                                                                                      0.0s 
 ✔ Container redis_video_queue             Started                                                                                      0.6s 
 ✔ Container jupyter_debug                 Started                                                                                      0.5s 
 ✔ Container sh-video-srvc-video-worker-1  Started                                                                                      0.7s 
 ✔ Container video_capture_service         Started    

```

Коли контейнер стартонув, ви побачите зібрані образи:

```bash
docker image ls

```


```text
REPOSITORY                                       TAG        IMAGE ID       CREATED        SIZE
sh-video-srvc-jupyter                            latest     21244695f43c   46 hours ago   9.86GB
sh-video-srvc-video-capture                      latest     3cb8570ef855   46 hours ago   9.86GB
sh-video-srvc-video-worker                       latest     a1ed4b76a58d   46 hours ago   9.86GB

```

А якщо подивитися запущені  контейнери 

```bash

docker ps

```

то побачимо такий список контейнерів.


```text
CONTAINER ID   IMAGE                         COMMAND                  CREATED         STATUS         PORTS                                         NAMES
831eb3a72e3b   sh-video-srvc-video-capture   "python vcam_runner.…"   4 minutes ago   Up 4 minutes                                                 video_capture_service
4fa4d0f0427f   sh-video-srvc-video-worker    "python video_runner…"   4 minutes ago   Up 4 minutes                                                 sh-video-srvc-video-worker-1
7ac911b1f0a2   redis:6-alpine                "docker-entrypoint.s…"   4 minutes ago   Up 4 minutes   0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp   redis_video_queue
caef030b2709   sh-video-srvc-jupyter         "jupyter lab --ip=0.…"   4 minutes ago   Up 4 minutes   0.0.0.0:8888->8888/tcp, [::]:8888->8888/tcp   jupyter_debug

````

Перевіримо, чи працює контейнер, що приймає трафік відеокамери, підключившись до логів контейнеру. Тут треба звернути увагу, що  вказується не назва контейнеру, а назва сервісу з docker-compose.yml.

```bash
$ docker compose logs video-capture -f

```

Нижче показано лог, коли камера не підключена

```text

video_capture_service  | WARNING ⚠️ user config directory '/root/.config/Ultralytics' is not writable, using '/tmp/Ultralytics'. Set YOLO_CONFIG_DIR to override.
video_capture_service  | Creating new Ultralytics Settings v0.0.6 file ✅ 
video_capture_service  | View Ultralytics Settings with 'yolo settings' or at '/tmp/Ultralytics/settings.json'
video_capture_service  | Update Settings with 'yolo settings key=value', i.e. 'yolo settings runs_dir=path/to/dir'. For help see https://docs.ultralytics.com/quickstart/#ultralytics-settings.
video_capture_service  | 2026-02-25 12:33:01,813 - DEBUG - utils.tasks - debug message
video_capture_service  | 2026-02-25 12:33:01,813 - DEBUG - utils.tasks - Модель завантажується з локального файлу: yolov8n.pt
video_capture_service  | 2026-02-25 12:33:01,909 - DEBUG - utils.tasks - Модель успішно завантажено з локального файлу.
video_capture_service  | YOLOv8n summary: 129 layers, 3,157,200 parameters, 0 gradients, 8.9 GFLOPs
video_capture_service  | 2026-02-25 12:33:02,050 - DEBUG - utils.tasks - YOLO model ready: (129, 3157200, 0, 8.8575488)
video_capture_service  | 2026-02-25 12:33:02,050 - DEBUG - vcam_worker.vcam_wrkr - debug message
video_capture_service  | 2026-02-25 12:33:02,050 - DEBUG - vcam_worker.vcam_wrkr - ===================================
video_capture_service  | 2026-02-25 12:33:02,050 - DEBUG - vcam_worker.vcam_wrkr - ===================================
video_capture_service  | 2026-02-25 12:33:02,050 - DEBUG - vcam_worker.vcam_wrkr - Підключення до Redis (використовуємо змінні з  env)
video_capture_service  | 2026-02-25 12:33:02,053 - DEBUG - vcam_worker.vcam_wrkr - Підключення до черги video_queue
video_capture_service  | 2026-02-25 12:33:02,053 - DEBUG - vcam_worker.vcam_wrkr - Читаю налаштування
video_capture_service  | [tcp @ 0x5633f7e905c0] Connection to tcp://192.168.0.102:8554?timeout=0 failed: Connection refused
video_capture_service  | ERROR:root:Камера недоступна. Наступна спроба через 10 секунд.
video_capture_service  | [tcp @ 0x5633f7e905c0] Connection to tcp://192.168.0.102:8554?timeout=0 failed: Connection refused
video_capture_service  | ERROR:root:Камера недоступна. Наступна спроба через 10 секунд.
video_capture_service  | [tcp @ 0x5633f7e90680] Connection to tcp://192.168.0.102:8554?timeout=0 failed: Connection refused
video_capture_service  | ERROR:root:Камера недоступна. Наступна спроба через 10 секунд.
video_capture_service  | [tcp @ 0x5633f7e90680] Connection to tcp://192.168.0.102:8554?timeout=0 failed: Connection refused

```

Тепер я підключу IP-камеру телефона і заставлю її дивитися на реле напруги

```text

video_capture_service  | ERROR:root:Камера недоступна. Наступна спроба через 10 секунд.
video_capture_service  | 2026-02-25 12:50:29,946 - DEBUG - vcam_worker.vcam_wrkr - Рух виявлено! Початок запису.
video_capture_service  | DEBUG:vcam_worker.vcam_wrkr:Рух виявлено! Початок запису.
video_capture_service  | 2026-02-25 12:51:00,035 - DEBUG - vcam_worker.vcam_wrkr - Запис завершено.
video_capture_service  | DEBUG:vcam_worker.vcam_wrkr:Запис завершено.
video_capture_service  | 2026-02-25 12:51:00,036 - DEBUG - vcam_worker.vcam_wrkr - Завантаження завершено!
video_capture_service  | DEBUG:vcam_worker.vcam_wrkr:Завантаження завершено!
video_capture_service  | 2026-02-25 12:51:00,037 - DEBUG - vcam_worker.vcam_wrkr - Повідомлення для черги: {"filename": "20260225-125029.avi"}
video_capture_service  | DEBUG:vcam_worker.vcam_wrkr:Повідомлення для черги: {"filename": "20260225-125029.avi"}
video_capture_service  | 2026-02-25 12:51:00,042 - INFO - vcam_worker.vcam_wrkr - Задачу додано в чергу: 34441a9b-d80d-4c97-b8ba-d52170f28472 для файлу 20260225-125029.avi
video_capture_service  | INFO:vcam_worker.vcam_wrkr:Задачу додано в чергу: 34441a9b-d80d-4c97-b8ba-d52170f28472 для файлу 20260225-125029.avi
video_capture_service  | 2026-02-25 12:51:00,042 - DEBUG - vcam_worker.vcam_wrkr - Локальний файл 20260225-125029.avi видалено.
video_capture_service  | DEBUG:vcam_worker.vcam_wrkr:Локальний файл 20260225-125029.avi видалено.
```
Тут далі руху не має і камера стоїть і очікую руху.

Тепер відключаємо камеру і переходимо до логів сервісу **video-worker:** (назва з docker-compose.yml).


```bash
docker compose logs video-worker

```

```text
video-worker-1  | 13:10:02 Worker 7874ebce42074efc8e6154532c4d87d6: calling multi() on pipeline for job 35eb81d8-8f4e-414d-92c6-95bd479486c6
video-worker-1  | 13:10:02 Worker 7874ebce42074efc8e6154532c4d87d6: saving job 35eb81d8-8f4e-414d-92c6-95bd479486c6's successful execution result
video-worker-1  | 13:10:02 Job 35eb81d8-8f4e-414d-92c6-95bd479486c6: handling success...
video-worker-1  | 13:10:02 Cleaning up execution of job 35eb81d8-8f4e-414d-92c6-95bd479486c6
video-worker-1  | 13:10:02 Cleaning up execution of job 35eb81d8-8f4e-414d-92c6-95bd479486c6
video-worker-1  | 13:10:02 Successfully completed utils.tasks.crttask_sendmsg('{"filename": "20260225-130913.avi"}') job in 0:00:18.511687s on worker 7874ebce42074efc8e6154532c4d87d6
video-worker-1  | 13:10:02 Worker 7874ebce42074efc8e6154532c4d87d6: finished handling successful execution of job 35eb81d8-8f4e-414d-92c6-95bd479486c6
video-worker-1  | 13:10:02 video_queue: Job OK (35eb81d8-8f4e-414d-92c6-95bd479486c6)
video-worker-1  | 13:10:02 Worker 7874ebce42074efc8e6154532c4d87d6: result: "{'ok': True, 'filename': '20260225-130913.avi', 'detected': [], 'count': 0, 'timestamp': '2026-02-25T13:10:02.840865'}"
video-worker-1  | 13:10:02 Result is kept for 500 seconds
video-worker-1  | 13:10:02 Worker 7874ebce42074efc8e6154532c4d87d6: work horse finished for job 35eb81d8-8f4e-414d-92c6-95bd479486c6: retpid=314, ret_val=0
video-worker-1  | 13:10:02 Worker 7874ebce42074efc8e6154532c4d87d6: sent heartbeat to prevent worker timeout. Next one should arrive in 480 seconds.

```

Тепер перевіряємо наявність Jupyter Lab

```bash
docker compose logs jupyter

```

```text
docker compose logs jupyter
jupyter_debug  | [I 2026-02-25 12:33:00.119 ServerApp] jupyter_lsp | extension was successfully linked.
jupyter_debug  | [I 2026-02-25 12:33:00.122 ServerApp] jupyter_server_terminals | extension was successfully linked.
jupyter_debug  | [W 2026-02-25 12:33:00.123 LabApp] 'token' has moved from NotebookApp to ServerApp. This config will be passed to ServerApp. Be sure to update your config before our next release.
jupyter_debug  | [W 2026-02-25 12:33:00.126 ServerApp] ServerApp.token config is deprecated in 2.0. Use IdentityProvider.token.
jupyter_debug  | [I 2026-02-25 12:33:00.126 ServerApp] jupyterlab | extension was successfully linked.
jupyter_debug  | [I 2026-02-25 12:33:00.130 ServerApp] Writing Jupyter server cookie secret to /root/.local/share/jupyter/runtime/jupyter_cookie_secret
jupyter_debug  | [I 2026-02-25 12:33:00.846 ServerApp] notebook_shim | extension was successfully linked.
jupyter_debug  | [W 2026-02-25 12:33:00.892 ServerApp] All authentication is disabled.  Anyone who can connect to this server will be able to run code.
jupyter_debug  | [I 2026-02-25 12:33:00.894 ServerApp] notebook_shim | extension was successfully loaded.
jupyter_debug  | [I 2026-02-25 12:33:00.899 ServerApp] jupyter_lsp | extension was successfully loaded.
jupyter_debug  | [I 2026-02-25 12:33:00.901 ServerApp] jupyter_server_terminals | extension was successfully loaded.
jupyter_debug  | [I 2026-02-25 12:33:00.905 LabApp] JupyterLab extension loaded from /usr/local/lib/python3.11/site-packages/jupyterlab
jupyter_debug  | [I 2026-02-25 12:33:00.906 LabApp] JupyterLab application directory is /usr/local/share/jupyter/lab
jupyter_debug  | [I 2026-02-25 12:33:00.906 LabApp] Extension Manager is 'pypi'.
jupyter_debug  | [I 2026-02-25 12:33:00.995 ServerApp] jupyterlab | extension was successfully loaded.
jupyter_debug  | [I 2026-02-25 12:33:00.996 ServerApp] Serving notebooks from local directory: /app
jupyter_debug  | [I 2026-02-25 12:33:00.996 ServerApp] Jupyter Server 2.17.0 is running at:
jupyter_debug  | [I 2026-02-25 12:33:00.996 ServerApp] http://caef030b2709:8888/lab
jupyter_debug  | [I 2026-02-25 12:33:00.996 ServerApp]     http://127.0.0.1:8888/lab
jupyter_debug  | [I 2026-02-25 12:33:00.996 ServerApp] Use Control-C to stop this server and shut down all kernels (twice to skip confirmation).
```
Лог в наявності - теж працює додаток.

Таким чином ми впевнилися що прикладні контейнери запустилися. контейнер Redis  теж бачили, але дивитися в його логи особливого сенсу немає.
Тому вважаємо, що додаток запущено


### Перевірка роботи аналітичної платформи Jupyter Lab


Jupyter lab запускається по URL:   http://localhost:8888/lab.
Якщо запустилася успішно, то на екрані поачимо щось подібне:


<kbd><img src="doc/pic-05.jpg" /></kbd>
<p style="text-align: center;"><a name="pic-05">pic-05</a></p>

Тут можемо побачити  кілька notebooks, каталог **/video**, що відмаплено на volume docker composer і видно всі відеофайли, jsonl файл з логом їх обробки. Та катлог **/utils** який в собі зберігає спільний обробник повідомлень черги Redis.

Відкриємо notebook [CheckJupyter.ipynb](./notebooks/CheckJupyter.ipynb) - перевірити, що notebook запускається.

 
<kbd><img src="doc/pic-06.jpg" /></kbd>
<p style="text-align: center;"><a name="pic-06">pic-06</a></p>


Тут звичайний простенький приклад. Завантажити в DataFrame pandas фіксований масив даних і їх відобразити.
 
## Використання Jupytre Lab



1. [CheckJupyter.ipynb](./notebooks/CheckJupyter.ipynb) - перевірити, що notebook запускається. 

Тут нічого особливого немає. Просто відображається фіксований pandas dataframe.



2. [SendProcessFile.ipynb](./notebooks/SendProcessFile.ipynb) - Відправити на обробку video-worker уже існуючий в каталозі video файл

Це дуже корисна книга. Вона допомагає підкладати різні відеофайли і на пряму, конкретно вказаний відофайл відправити на обробку обробникові. 
Тобто, можна повторно обробити файл, можна підкласти якийсь інший, скачаний в каталог **video**, і відправивши повідомлення в чергу, подивитися лог роботи обробника.

Тако ж можна побачити глибину черги. Стан обробки ващого повідомлення: в черзі воно, ч почалася обробка, чи вже закінчилася і можна дивитися результат
 

3. [IsoletedFileProcessing](./notebooks//IsoletedFileProcessing) - викоати оброку файла  в обхід обробника video-worker, напряму прочивши повідомлення через [tasks.py](/shared_utils/tasks.py) і праямо в Jupyter Notebook побачити його лог оброки

Тут виконуємо обробку поза video-worker, прямо викликаючи модуль оброки і праямо в Jupyter Notebook побачити його лог.


4. [ViewProcessResuts.ipynb](./notebooks/ViewProcessResuts.ipynb) - переглянути лог роботи та розрахувати аналітику.

А тут можна побачити журнал обробки файлів та їх статистику, використовуючи стандартні пакети pandas та tplotlib.


Jupyter notebooks  прекрасно відображаються прямо в github чи в Visual Studio code -тому скріншотів не наводжу. Нотебуки збережені з прикладами




