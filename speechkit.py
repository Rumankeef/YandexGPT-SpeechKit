import requests
import logging  # модуль для сбора логов
# подтягиваем константы из config файла
from config import *
from creds import get_creds

# настраиваем запись логов в файл
logging.basicConfig(filename=LOGS, level=logging.ERROR, format="%(asctime)s FILE: %(filename)s IN: %(funcName)s "
                                                               "MESSAGE: %(message)s", filemode="w")

iam_token, folder_id = get_creds()  # получаем iam_token и folder_id из файлов


def speech_to_text(data):
    # iam_token, folder_id для доступа к Yandex SpeechKit

    # Указываем параметры запроса
    params = "&".join([
        "topic=general",  # используем основную версию модели
        f"folderId={FOLDER_ID_PATH}",
        "lang=ru-RU"  # распознаём голосовое сообщение на русском языке
    ])

    # Аутентификация через IAM-токен
    headers = {
        'Authorization': f'Bearer {IAM_TOKEN_PATH}',
    }

    # Выполняем запрос
    response = requests.post(
        f"https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?{params}",
        headers=headers,
        data=data
    )

    # Читаем json в словарь
    decoded_data = response.json()
    # Проверяем, не произошла ли ошибка при запросе
    if decoded_data.get("error_code") is None:
        return True, decoded_data.get("result")  # Возвращаем статус и текст из аудио
    else:
        return False, "При запросе в SpeechKit возникла ошибка"


def text_to_speech(text: str):
    headers = {
        'Authorization': f'Bearer {BOT_TOKEN_PATH}',
    }
    data = {
        'text': text,
        'speed': 1.2,  # Скорость чтения
        'emotion': 'good',  # эмоциональная окраска
        'lang': 'ru-RU',  # язык текста - русский
        'voice': 'filipp',  # голос Джейн
        'folderId': folder_id,
    }
    # Выполняем запрос
    response = requests.post('https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize', headers=headers, data=data)

    if response.status_code == 200:
        return True, response.content  # Возвращаем голосовое сообщение
    else:
        return False, "При запросе в SpeechKit возникла ошибка"
