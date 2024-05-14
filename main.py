# https://github.com/Rumankeef/YandexGPT-SpeechKit
from validators import *  # модуль для валидации
from yandex_gpt import ask_gpt  # модуль для работы с GPT
from speechkit import text_to_speech, speech_to_text
# подтягиваем константы из config файла
from database import create_database, add_message, select_n_last_messages
from creds import get_bot_token
import requests
import telebot
import logging
from config import *

bot = telebot.TeleBot(get_bot_token())

session = requests.Session()


@bot.message_handler(commands=['start'])
def start(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row('/stt', '/tts', '/chat', '/help')
    logging.info(f"Пользователь {message.from_user.username} начал работу с ботом")
    bot.reply_to(message,
                 "Добро пожаловать в бот с внедренным Yandex GPT! /chat для работы с нейросетью, /help, если хотите узнать остальные функции бота")


@bot.message_handler(commands=['help'])
def send_welcome(message):
    bot.reply_to(message, """\
После ввода команды /chat введите текстом или голосовым сообщением запрос. На каждого пользователя установлено ограничение по использованию GPT
После ввода команды /tts введите текстом запрос. На каждого пользователя установлено ограничение по использованию SpeechKit
После ввода команды /stt введите запрос голосовым сообщением. На каждого пользователя установлено ограничение по использованию SpeechKit
Команды бота:
/start - Начало
/chat - Чат-бот
/tts - text-to-speech
/stt - speech-to-text
\
""")


@bot.message_handler(commands=['debug'])
def send_logs(message):
    logging.info(f"Пользователь {message.from_user.username} вызвал лог")
    with open("log_file.txt", "rb") as f:
        bot.send_document(message.chat.id, f)


@bot.message_handler(commands=['tts'])
def tts_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Отправь следующим сообщеним текст, чтобы я его озвучил!')
    bot.register_next_step_handler(message, tts)


def tts(message):
    user_id = message.from_user.id
    text = message.text

    if message.content_type != 'text':
        bot.send_message(user_id, 'Отправь текстовое сообщение')
        return

    text_symbol = is_tts_symbol_limit(message, text)
    if text_symbol is None:
        return

    insert_row(user_id, text, text_symbol)

    status, content = text_to_speech(text)

    if status:
        bot.send_voice(user_id, content)
    else:
        bot.send_message(user_id, content)


@bot.message_handler(commands=['stt'])
def stt_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Отправь голосовое сообщение, чтобы я его распознал!')
    bot.register_next_step_handler(message, stt)


# Переводим голосовое сообщение в текст после команды stt

def stt(message):
    user_id = message.from_user.id

    # Проверка, что сообщение действительно голосовое
    if not message.voice:
        return

    # Считаем аудиоблоки и проверяем сумму потраченных аудиоблоков
    stt_blocks = is_stt_block_limit(message, message.voice.duration)
    if not stt_blocks:
        return

    file_id = message.voice.file_id  # получаем id голосового сообщения
    file_info = bot.get_file(file_id)  # получаем информацию о голосовом сообщении
    file = bot.download_file(file_info.file_path)  # скачиваем голосовое сообщение

    # Получаем статус и содержимое ответа от SpeechKit
    status, text = speech_to_text(file)  # преобразовываем голосовое сообщение в текст

    # Если статус True - отправляем текст сообщения и сохраняем в БД, иначе - сообщение об ошибке
    if status:
        # Записываем сообщение и кол-во аудиоблоков в БД
        insert_row(user_id, text, 'stt_blocks', stt_blocks)
        bot.send_message(user_id, text, reply_to_message_id=message.id)
        bot.send_message(user_id, 'Для нового запроса нажми /stt')
    else:
        bot.send_message(user_id, text)
        bot.send_message(user_id, 'Для нового запроса нажми /stt')


@bot.message_handler(commands=['chat'])
def tts_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Введите запрос текстом или голосовым сообщением')


def handle_voice(message):
    user_id = message.from_user.id
    try:
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)
            return
        stt_blocks, error_message = is_stt_block_limit(message, message.voice.duration)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        file_id = message.voice.file_id
        file_info = bot.get_file(file_id)
        file = bot.download_file(file_info.file_path)
        status_stt, stt_text = speech_to_text(file)
        if not status_stt:
            bot.send_message(user_id, stt_text)
            return
        add_message(user_id=user_id,
                    full_message=[stt_text, 'user', 0, 0, stt_blocks])
        last_messages, total_spent_tokens = select_n_last_messages(user_id,
                                                                   COUNT_LAST_MSG)
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages,
                                                             total_spent_tokens)
        if error_message:
            bot.send_message(user_id, error_message)
            return
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        if not status_gpt:
            bot.send_message(user_id, answer_gpt)
            return
        total_gpt_tokens += tokens_in_answer
        tts_symbols, error_message = is_tts_symbol_limit(message=message,
                                                         text=answer_gpt)
        add_message(user_id=user_id,
                    full_message=[answer_gpt, 'assistant', total_gpt_tokens,
                                  tts_symbols, 0])
        if error_message:
            bot.send_message(user_id, error_message)
            return
        status_tts, voice_response = text_to_speech(answer_gpt)
        if status_tts:
            bot.send_voice(user_id, voice_response,
                           reply_to_message_id=message.id)
        else:
            bot.send_message(user_id, answer_gpt,
                             reply_to_message_id=message.id)
    except Exception as e:
        logging.error(e)  # если ошибка — записываем её в логи
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй написать другое сообщение")


# обрабатываем текстовые сообщения
def handle_text(message):
    try:
        user_id = message.from_user.id

        # ВАЛИДАЦИЯ: проверяем, есть ли место для ещё одного пользователя (если пользователь новый)
        status_check_users, error_message = check_number_of_users(user_id)
        if not status_check_users:
            bot.send_message(user_id, error_message)  # мест нет =(
            return

        # БД: добавляем сообщение пользователя и его роль в базу данных
        full_user_message = [message.text, 'user', 0, 0, 0]
        add_message(user_id=user_id, full_message=full_user_message)

        # ВАЛИДАЦИЯ: считаем количество доступных пользователю GPT-токенов
        # получаем последние 4 (COUNT_LAST_MSG) сообщения и количество уже потраченных токенов
        last_messages, total_spent_tokens = select_n_last_messages(user_id, COUNT_LAST_MSG)
        # получаем сумму уже потраченных токенов + токенов в новом сообщении и оставшиеся лимиты пользователя
        total_gpt_tokens, error_message = is_gpt_token_limit(last_messages, total_spent_tokens)
        if error_message:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, error_message)
            return

        # GPT: отправляем запрос к GPT
        status_gpt, answer_gpt, tokens_in_answer = ask_gpt(last_messages)
        # GPT: обрабатываем ответ от GPT
        if not status_gpt:
            # если что-то пошло не так — уведомляем пользователя и прекращаем выполнение функции
            bot.send_message(user_id, answer_gpt)
            return
        # сумма всех потраченных токенов + токены в ответе GPT
        total_gpt_tokens += tokens_in_answer

        # БД: добавляем ответ GPT и потраченные токены в базу данных
        full_gpt_message = [answer_gpt, 'assistant', total_gpt_tokens, 0, 0]
        add_message(user_id=user_id, full_message=full_gpt_message)

        bot.send_message(user_id, answer_gpt, reply_to_message_id=message.id)  # отвечаем пользователю текстом
    except Exception as e:
        logging.error(e)  # если ошибка — записываем её в логи
        bot.send_message(message.from_user.id, "Не получилось ответить. Попробуй написать другое сообщение")


# обрабатываем все остальные типы сообщений
@bot.message_handler(func=lambda: True)
def handler(message):
    bot.send_message(message.from_user.id, "Отправь мне голосовое или текстовое сообщение, и я тебе отвечу")


if __name__ == '__main__':
    create_database()
    bot.polling()
