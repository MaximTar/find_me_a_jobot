import difflib
import socket
from typing import TypedDict, Dict

import httpx
import telebot

import config
import utils

# TODO add proxy?
# TODO add 'help'
# TODO webhook?
# TODO add logging
bot = telebot.TeleBot(config.TOKEN)

REPLY_KEYBOARD_REMOVE = telebot.types.ReplyKeyboardRemove()


class UserQuery(TypedDict):
    user_id: int
    vacancy: str
    areas: set
    experience: str
    salary: int
    only_with_salary: str
    employments: set
    schedules: str
    period: int


class HHDicts(TypedDict):
    areas: Dict[str, str]
    experiences: Dict[str, str]
    only_with_salaries: Dict[str, str]
    employments: Dict[str, str]
    schedules: Dict[str, str]


@bot.message_handler(commands=['start'])
def start(msg):
    # noinspection PyTypeChecker
    user_query: UserQuery = {'user_id': msg.from_user.id}

    try:
        schedules, employments, experiences, only_with_salaries = utils.get_dictionaries()
        hh_dicts: HHDicts = {'areas': utils.get_areas(),
                             'experiences': experiences,
                             'only_with_salaries': only_with_salaries,
                             'employments': employments,
                             'schedules': schedules}
        # TODO save hh_dicts
        bot.send_message(msg.chat.id, 'Привет! Давай найдем тебе работу. Какие слова будем искать?',
                         reply_markup=REPLY_KEYBOARD_REMOVE)
        bot.register_next_step_handler(msg, get_vacancy, user_query, hh_dicts)
    except (httpx.ConnectTimeout, socket.timeout):
        # TODO catch requests.exceptions.ConnectTimeout
        bot.send_message(msg.chat.id, 'У меня какие-то проблемы. Подожди немного, я попробую еще раз.',
                         reply_markup=REPLY_KEYBOARD_REMOVE)
        start(msg)


def get_vacancy(msg, user_query, hh_dicts):
    user_query['vacancy'] = msg.text
    bot.reply_to(msg, 'Записал. Где будем искать? Напиши мне город или страну. '
                      'Можно несколько, но тогда пиши через запятую.')
    bot.register_next_step_handler(msg, get_area, user_query, hh_dicts)


def get_area(msg, user_query, hh_dicts):
    suggested_areas = []

    # TODO check if user wants only remote work

    for word in msg.text.split(','):
        if word.lower() not in hh_dicts['areas'].keys():
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
            if 'items' in response.keys() and response['items']:
                for item in response['items']:
                    suggested_areas.append(item['text'])
            else:
                # last try
                words = difflib.get_close_matches(word.lower(), hh_dicts['areas'].keys(), n=1)
                if words:
                    # noinspection PyUnresolvedReferences
                    suggested_areas.append(words[0].title())
                else:
                    bot.reply_to(msg, 'Не разобрал. Повтори, пожалуйста.')
                    # not sure if this is ok
                    return bot.register_next_step_handler(msg, get_area, user_query, hh_dicts)
        else:
            user_query['areas'] = hh_dicts['areas'][word.lower()]

    if suggested_areas:
        suggested_areas_keyboard = telebot.types.ReplyKeyboardMarkup()
        for area in suggested_areas:
            suggested_areas_keyboard.add(telebot.types.KeyboardButton(area))
        suggested_areas_keyboard.add(telebot.types.KeyboardButton('Далее'))

        bot.send_message(msg.chat.id, 'Я кое-что не разобрал, позволь уточню.'
                                      'Как закончишь - жми "Далее" в конце списка.',
                         reply_markup=suggested_areas_keyboard)
        bot.register_next_step_handler(msg, handle_suggested_areas, user_query, hh_dicts)
    else:
        get_experience(msg, user_query, hh_dicts)


def handle_suggested_areas(msg, user_query, hh_dicts):
    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            get_experience(msg, user_query, hh_dicts)
        elif msg.text.lower() in hh_dicts['areas'].keys():
            user_query['areas'] = hh_dicts['areas'][msg.text.lower()]
            bot.register_next_step_handler(msg, handle_suggested_areas, user_query, hh_dicts)
        else:
            # TODO
            pass


def get_experience(msg, user_query, hh_dicts):
    experience_keyboard = telebot.types.ReplyKeyboardMarkup()
    for experience in hh_dicts['experiences'].keys():
        experience_keyboard.add(telebot.types.KeyboardButton(experience))

    bot.send_message(msg.chat.id, 'Теперь скажи, какой у тебя опыт?',
                     reply_markup=experience_keyboard)
    bot.register_next_step_handler(msg, handle_experience, user_query, hh_dicts)


def handle_experience(msg, user_query, hh_dicts):
    if msg.chat.type == 'private' and msg.text in hh_dicts['experiences']:
        user_query['experience'] = hh_dicts['experiences'][msg.text]
        get_salary(msg, user_query, hh_dicts)
    else:
        # TODO
        pass


def get_salary(msg, user_query, hh_dicts):
    salary_keyboard = telebot.types.ReplyKeyboardMarkup()
    for salary in hh_dicts['only_with_salaries'].keys():
        salary_keyboard.add(telebot.types.KeyboardButton(salary))

    bot.send_message(msg.chat.id, 'Отлично. А сколько в рублях ты хочешь получать?',
                     reply_markup=salary_keyboard)
    bot.register_next_step_handler(msg, handle_salary, user_query, hh_dicts)


def handle_salary(msg, user_query, hh_dicts):
    if msg.chat.type == 'private':
        if msg.text in hh_dicts['only_with_salaries'].keys():
            user_query['only_with_salary'] = hh_dicts['only_with_salaries'][msg.text]
            get_employment(msg, user_query, hh_dicts)
        else:
            try:
                user_salary = int(msg.text)
                assert user_salary > 0
                user_query['salary'] = user_salary
                get_employment(msg, user_query, hh_dicts)
            except (ValueError, AssertionError):
                bot.reply_to(msg, 'Похоже, ты где-то опечатался. Так какую зарплату ты хочешь?')
                bot.register_next_step_handler(msg, get_salary, user_query, hh_dicts)


def get_employment(msg, user_query, hh_dicts):
    employment_keyboard = telebot.types.ReplyKeyboardMarkup()
    for employment in hh_dicts['employments'].keys():
        employment_keyboard.add(telebot.types.KeyboardButton(employment))
    employment_keyboard.add(telebot.types.KeyboardButton('Далее'))

    bot.send_message(msg.chat.id, 'Какой тип занятости тебя интересуеут?\n'
                                  'Можешь выбрать несколько вариантов, потом жми "Далее".',
                     reply_markup=employment_keyboard)
    bot.register_next_step_handler(msg, handle_employment, user_query, hh_dicts)


def handle_employment(msg, user_query, hh_dicts):
    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            get_schedule(msg, user_query, hh_dicts)
        elif msg.text in hh_dicts['employments'].keys():
            if hh_dicts['employments'][msg.text] is None:
                user_query['employments'] = set()
                get_schedule(msg, user_query, hh_dicts)
            else:
                user_query['employments'] = hh_dicts['employments'][msg.text]
                bot.register_next_step_handler(msg, handle_employment, user_query, hh_dicts)
        else:
            # TODO
            pass


def get_schedule(msg, user_query, hh_dicts):
    schedule_keyboard = telebot.types.ReplyKeyboardMarkup()
    for schedule in hh_dicts['schedules'].keys():
        schedule_keyboard.add(telebot.types.KeyboardButton(schedule))
    schedule_keyboard.add(telebot.types.KeyboardButton('Далее'))

    bot.send_message(msg.chat.id, 'Почти закончили. Какой график работы хочешь?\n'
                                  'Можешь выбрать несколько вариантов... Короче, ты понял.',
                     reply_markup=schedule_keyboard)
    bot.register_next_step_handler(msg, handle_schedule, user_query, hh_dicts)


def handle_schedule(msg, user_query, hh_dicts):
    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            get_period(msg, user_query)
        elif msg.text in hh_dicts['schedules'].keys():
            if hh_dicts['schedules'][msg.text] is None:
                user_query['schedules'] = set()
                get_period(msg, user_query)
            else:
                user_query['schedules'] = hh_dicts['schedules'][msg.text]
                bot.register_next_step_handler(msg, handle_schedule, user_query, hh_dicts)
        else:
            # TODO
            pass


def get_period(msg, user_query):
    bot.send_message(msg.chat.id, 'Последний вопрос. Как часто хочешь получать новые вакансии? '
                                  'Напиши число от 1 до 30.', reply_markup=REPLY_KEYBOARD_REMOVE)
    bot.register_next_step_handler(msg, handle_period, user_query)


def handle_period(msg, user_query):
    try:
        user_period = int(msg.text)
        assert 1 <= user_period <= 30
        user_query['period'] = user_period
        publish_vacancies(msg, user_query)
    except (ValueError, AssertionError):
        bot.reply_to(msg, 'Я же просил число от 1 до 30. Так как часто хочешь получать новые вакансии?')
        bot.register_next_step_handler(msg, handle_period, user_query)


def publish_vacancies(msg, user_query):
    # 'search_field': ['name', 'description'],
    parameters = {
        'text': user_query['vacancy'],
        'area': list(user_query['areas']),
        'period': user_query['period']
    }

    for key, op in zip(['experience', 'employments', 'schedules', 'salary', 'only_with_salary'],
                       [str, list, list, str, str]):
        utils.copy_pair(user_query, parameters, key, operation=op)

    response = httpx.get('https://api.hh.ru/vacancies', params=parameters).json()

    bot.send_message(msg.chat.id, "Вот, что я нашел по твоим параметрам:")

    # result_string = ''
    for vacancy in response['items']:
        # result_string += f"{vacancy['name']}\n{vacancy['employer']['name']}\n" \
        #                  f"ЗП: {vacancy['salary']['from']}-{vacancy['salary']['to']}\n" \
        #                  f"{vacancy['alternate_url']}\n"
        bot.send_message(msg.chat.id, utils.build_msg(vacancy))
    # bot.send_message(msg.chat.id, result_string)


bot.infinity_polling()
