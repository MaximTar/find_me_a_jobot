import difflib
import socket

import httpx
import telebot
import config
import utils

# TODO add proxy?
# TODO add logging
bot = telebot.TeleBot(config.TOKEN)

REPLY_KEYBOARD_REMOVE = telebot.types.ReplyKeyboardRemove()

areas = {}
# TODO get from request
experiences = {
    'Не имеет значения': None,
    'От 1 года до 3 лет': 'between1And3',
    'Нет опыта': 'noExperience',
    'От 3 до 6 лет': 'between3And6',
    'Более 6 лет': 'moreThan6'
}
only_with_salaries = {
    'Не имеет значения': None,
    'Не имеет значения, но указана': 'true'
}
employments = {
    'Не имеет значения': None,
    'Полная': 'full',
    'Частичная': 'part',
    'Стажировка': 'project',
    'Проектная': 'volunteer',
    'Волонтерство': 'probation'
}
schedules = {
    'Не имеет значения': None,
    'Полный день': 'fullDay',
    'Сменный график': 'shift',
    'Вахтовый метод': 'flyInFlyOut',
    'Гибкий график': 'flexible',
    'Удаленная работа': 'remote'
}

user_vacancy = None
user_areas = set()
user_experience = None
user_salary = None
user_only_with_salary = None
user_employments = set()
user_schedules = set()
user_period = None


@bot.message_handler(commands=['start'])
def start(msg):
    global areas

    try:
        areas = utils.get_areas()
        bot.send_message(msg.chat.id, 'Привет! Давай найдем тебе работу. Какие слова будем искать?',
                         reply_markup=REPLY_KEYBOARD_REMOVE)
        bot.register_next_step_handler(msg, get_vacancy)
    except (httpx.ConnectTimeout, socket.timeout):
        # TODO catch requests.exceptions.ConnectTimeout
        bot.send_message(msg.chat.id, 'У меня какие-то проблемы. Подожди немного, я попробую еще раз.',
                         reply_markup=REPLY_KEYBOARD_REMOVE)
        start(msg)


def get_vacancy(msg):
    global user_vacancy
    # TODO check if empty
    user_vacancy = msg.text
    bot.reply_to(msg, 'Записал. Где будем искать? Напиши мне город или страну. '
                      'Можно несколько, но тогда пиши через запятую.')
    bot.register_next_step_handler(msg, get_area)


def get_area(msg):
    global user_areas

    suggested_areas = []

    # TODO check if msg is empty (only remote work)

    for word in msg.text.split(','):
        if word.lower() not in areas.keys():
            # let's suggest
            # TODO catch httpx.ConnectTimeout
            # try:
            response = httpx.get(f'https://api.hh.ru/suggests/areas?text={word}').json()
            # except (httpx.ConnectTimeout, socket.timeout):
            #     # TODO catch requests.exceptions.ConnectTimeout
            #     bot.reply_to(msg, 'У меня какие-то проблемы. Давай попробуем еще раз.')
            #     # get_area(msg)
            # TODO {'description': 'text length must be 2 or greater', 'bad_argument': 'text', 'bad_arguments':
            #  [{'name': 'text', 'description': 'text length must be 2 or greater'}],
            #  'errors': [{'value': 'text', 'type': 'bad_argument'}], 'request_id': '1658490563278c88bc33600bdac45c03'}
            if response['items']:
                # TODO check if only one item in response
                for item in response['items']:
                    suggested_areas.append(item['text'])
            else:
                # last try
                words = difflib.get_close_matches(word.lower(), areas.keys(), n=1)
                if words:
                    # noinspection PyUnresolvedReferences
                    suggested_areas.append(words[0].title())
                else:
                    # TODO: strange word -> needs further clarification
                    pass
        else:
            user_areas.add(areas[word.lower()])

    if suggested_areas:
        suggested_areas_keyboard = telebot.types.ReplyKeyboardMarkup()
        for area in suggested_areas:
            suggested_areas_keyboard.add(telebot.types.KeyboardButton(area))
        suggested_areas_keyboard.add(telebot.types.KeyboardButton('Далее'))

        bot.send_message(msg.chat.id, 'Я кое-что не разобрал, позволь уточню.'
                                      'Как закончишь - жми "Далее" в конце списка.',
                         reply_markup=suggested_areas_keyboard)
        bot.register_next_step_handler(msg, handle_suggested_areas)
    else:
        get_experience(msg)


def handle_suggested_areas(msg):
    global user_areas

    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            get_experience(msg)
        elif msg.text.lower() in areas.keys():
            user_areas.add(areas[msg.text.lower()])
            bot.register_next_step_handler(msg, handle_suggested_areas)
        else:
            # TODO
            pass


def get_experience(msg):
    experience_keyboard = telebot.types.ReplyKeyboardMarkup()
    for experience in experiences.keys():
        experience_keyboard.add(telebot.types.KeyboardButton(experience))

    bot.send_message(msg.chat.id, 'Теперь скажи, какой у тебя опыт?',
                     reply_markup=experience_keyboard)
    bot.register_next_step_handler(msg, handle_experience)


def handle_experience(msg):
    global user_experience

    if msg.chat.type == 'private' and msg.text in experiences:
        user_experience = experiences[msg.text]
        get_salary(msg)
    else:
        # TODO
        pass


def get_salary(msg):
    salary_keyboard = telebot.types.ReplyKeyboardMarkup()
    for salary in only_with_salaries.keys():
        salary_keyboard.add(telebot.types.KeyboardButton(salary))

    bot.send_message(msg.chat.id, 'Отлично. А сколько в рублях ты хочешь получать?',
                     reply_markup=salary_keyboard)
    bot.register_next_step_handler(msg, handle_salary)


def handle_salary(msg):
    global user_salary, user_only_with_salary

    if msg.chat.type == 'private':
        if msg.text in only_with_salaries.keys():
            user_only_with_salary = only_with_salaries[msg.text]
            get_employment(msg)
        else:
            try:
                user_salary = int(msg.text)
                assert user_salary > 0
                get_employment(msg)
            except (ValueError, AssertionError):
                bot.reply_to(msg, 'Похоже, ты где-то опечатался. Так какую зарплату ты хочешь?')
                bot.register_next_step_handler(msg, get_salary)


def get_employment(msg):
    employment_keyboard = telebot.types.ReplyKeyboardMarkup()
    for employment in employments.keys():
        employment_keyboard.add(telebot.types.KeyboardButton(employment))
    employment_keyboard.add(telebot.types.KeyboardButton('Далее'))

    bot.send_message(msg.chat.id, 'Какой тип занятости тебя интересуеут?\n'
                                  'Можешь выбрать несколько вариантов, потом жми "Далее".',
                     reply_markup=employment_keyboard)
    bot.register_next_step_handler(msg, handle_employment)


def handle_employment(msg):
    global user_employments

    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            get_schedule(msg)
        elif msg.text in employments.keys():
            if employments[msg.text] is None:
                user_employments = set()
                get_schedule(msg)
            else:
                user_employments.add(employments[msg.text])
                bot.register_next_step_handler(msg, handle_employment)
        else:
            # TODO
            pass


def get_schedule(msg):
    schedule_keyboard = telebot.types.ReplyKeyboardMarkup()
    for schedule in schedules.keys():
        schedule_keyboard.add(telebot.types.KeyboardButton(schedule))
    schedule_keyboard.add(telebot.types.KeyboardButton('Далее'))

    bot.send_message(msg.chat.id, 'Почти закончили. Какой график работы хочешь?\n'
                                  'Можешь выбрать несколько вариантов... Короче, ты понял.',
                     reply_markup=schedule_keyboard)
    bot.register_next_step_handler(msg, handle_schedule)


def handle_schedule(msg):
    global user_schedules

    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            get_period(msg)
        elif msg.text in schedules.keys():
            if schedules[msg.text] is None:
                user_schedules = set()
                get_period(msg)
            else:
                user_schedules.add(schedules[msg.text])
                bot.register_next_step_handler(msg, handle_schedule)
        else:
            # TODO
            pass


def get_period(msg):
    bot.send_message(msg.chat.id, 'Последний вопрос. Как часто хочешь получать новые вакансии? '
                                  'Напиши число от 1 до 30.', reply_markup=REPLY_KEYBOARD_REMOVE)
    bot.register_next_step_handler(msg, handle_period)


def handle_period(msg):
    global user_period

    try:
        user_period = int(msg.text)
        assert 1 <= user_period <= 30
        publish_vacancies(msg)
    except (ValueError, AssertionError):
        bot.reply_to(msg, 'Я же просил число от 1 до 30. Так как часто хочешь получать новые вакансии?')
        bot.register_next_step_handler(msg, handle_period)


def publish_vacancies(msg):
    parameters = {
        'text': user_vacancy,
        # 'search_field': ['name', 'description'],
        'area': list(user_areas),
        'period': user_period
    }

    if user_experience:
        parameters['experience'] = user_experience
    if user_employments:
        parameters['employment'] = list(user_employments)
    if user_schedules:
        parameters['schedule'] = list(user_schedules)
    if user_salary:
        parameters['salary'] = str(user_salary)
    if user_only_with_salary:
        parameters['only_with_salary'] = user_only_with_salary

    print(parameters)
    response = httpx.get('https://api.hh.ru/vacancies', params=parameters).json()
    print(response)

    bot.send_message(msg.chat.id, "Вот, что я нашел по твоим параметрам:")

    # result_string = ''
    for vacancy in response['items']:
        # result_string += f"{vacancy['name']}\n{vacancy['employer']['name']}\n" \
        #                  f"ЗП: {vacancy['salary']['from']}-{vacancy['salary']['to']}\n" \
        #                  f"{vacancy['alternate_url']}\n"
        # TODO vacancy['salary']['from'] could be empty
        bot.send_message(msg.chat.id, f"Вакансия: {vacancy['name']}\n"
                                      f"Компания: {vacancy['employer']['name']}\n"
                                      f"З/П: {vacancy['salary']['from']}-{vacancy['salary']['to']}\n"
                                      f"{vacancy['alternate_url']}")

    # bot.send_message(msg.chat.id, result_string)


bot.infinity_polling()