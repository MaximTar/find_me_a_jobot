import ast
import contextlib
import difflib
import socket

import httpx
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import hh_utils
from db_utils import insert_from_dict, create_connection, simple_select, update_from_list, delete
from dicts import UserQuery, get_user_query_russian_text, UserTextQuery, create_user_text_query

# TODO ELSES
# TODO add logging
# TODO add 'help'
# TODO check if msg == start (restart)
# TODO replace register_next_step_handler with States?
# TODO proxy?
# TODO webhook?
# TODO remake all get_* functions for updates

REPLY_KEYBOARD_REMOVE = telebot.types.ReplyKeyboardRemove()

CROSS_ICON = u"\u274C"  # delete
PENCIL_ICON = u"\u270E"  # edit

bot = telebot.TeleBot(config.TOKEN)


@bot.message_handler(commands=['settings'])
def settings(msg):
    with contextlib.closing(create_connection(config.DB_NAME)) as connection:
        user_vacancies = simple_select(connection, config.TEXT_QUERIES_TABLE_NAME, 'VACANCY',
                                       condition=f'USER_ID = {msg.from_user.id}')
    if user_vacancies:
        vacancies_keyboard = InlineKeyboardMarkup()
        vacancies_keyboard.row_width = 2
        for vacancy in user_vacancies:
            vacancy, = vacancy
            vacancies_keyboard.add(
                # uv_ is for update_vacancy
                InlineKeyboardButton(f'{vacancy} {PENCIL_ICON}', callback_data=f"['uv_', '{vacancy}']"),
                InlineKeyboardButton(CROSS_ICON, callback_data=f"['delete', '{vacancy}']"))
        bot.send_message(msg.chat.id, 'Твои подписки:', reply_markup=vacancies_keyboard)
    else:
        bot.send_message(msg.chat.id, 'У тебя нет подписок на вакансии. '
                                      'Чтобы это исправить, напиши мне /start '
                                      'или выбери соответствующий пункт в меню.',
                         reply_markup=REPLY_KEYBOARD_REMOVE)


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data.startswith("['vacancy'"):
        bot.answer_callback_query(callback_query_id=call.id, show_alert=True,
                                  text='Сюда не тыкай. \nТыкай на правые кнопки.')
    elif call.data.startswith("['uv_'"):
        vacancy = ast.literal_eval(call.data)[1]
        with contextlib.closing(create_connection(config.DB_NAME)) as connection:
            text_fields = create_user_text_query(*simple_select(connection, config.TEXT_QUERIES_TABLE_NAME, '*',
                                                                condition=f'USER_ID = {chat_id} '
                                                                          f'and VACANCY = "{vacancy}"'))
        update_vacancy_keyboard = InlineKeyboardMarkup()
        uq_russian = get_user_query_russian_text()
        for key in UserQuery.__annotations__.keys():
            field_name = uq_russian[key]
            if field_name:
                field_text = text_fields[key]

                if field_text.startswith("{"):
                    field_text = ', '.join(ast.literal_eval(field_text))

                update_vacancy_keyboard.add(
                    # uvf_ is for update_vacancy_field
                    InlineKeyboardButton(f'{field_name}: {field_text} {PENCIL_ICON}',
                                         callback_data="['uvf_', '{}', '{}']".format(vacancy, key)))
        bot.send_message(chat_id, f'Параметры вакансии {vacancy}:', reply_markup=update_vacancy_keyboard)
    elif call.data.startswith("['uvf_'"):
        vacancy = ast.literal_eval(call.data)[1]
        key = ast.literal_eval(call.data)[2]
        # TODO check condition - it's not good (could make surrogate PK and update by id)
        eval(f"update_{key}({chat_id}, {[key.upper()]},"
             f" \"USER_ID = {repr(str(chat_id))} AND VACANCY = {repr(str(vacancy))}\")")
    elif call.data.startswith("['delete'"):
        vacancy = ast.literal_eval(call.data)[1]
        with contextlib.closing(create_connection(config.DB_NAME)) as connection:
            delete(connection, config.QUERIES_TABLE_NAME,
                   condition=f'USER_ID = {chat_id} and VACANCY = "{vacancy}"')
            delete(connection, config.TEXT_QUERIES_TABLE_NAME,
                   condition=f'USER_ID = {chat_id} and VACANCY = "{vacancy}"')


@bot.message_handler(commands=['start'])
def start(msg):
    user_query: UserQuery = {'user_id': msg.from_user.id}
    user_text_query: UserTextQuery = {'user_id': msg.from_user.id}

    try:
        hh_dicts = hh_utils.get_hh_dicts()
        bot.send_message(msg.chat.id, 'Привет! Давай найдем тебе работу. Какие ключевые слова будем искать?',
                         reply_markup=REPLY_KEYBOARD_REMOVE)
        bot.register_next_step_handler(msg, get_vacancy, user_query, hh_dicts, user_text_query)
    except (httpx.ConnectTimeout, socket.timeout):
        # TODO catch requests.exceptions.ConnectTimeout
        bot.send_message(msg.chat.id, 'У меня какие-то проблемы. Подожди немного, я попробую еще раз.',
                         reply_markup=REPLY_KEYBOARD_REMOVE)
        start(msg)


def get_vacancy(msg, user_query, hh_dicts, user_text_query):
    user_query['vacancy'] = msg.text
    user_query['areas'] = set()
    user_text_query['vacancy'] = msg.text
    user_text_query['areas'] = set()
    bot.reply_to(msg, 'Записал. Где будем искать? Напиши мне город или страну. '
                      'Можно несколько, но тогда пиши через запятую.')
    bot.register_next_step_handler(msg, get_areas, user_query, hh_dicts, user_text_query)


def update_vacancy(chat_id, columns, condition):
    def update(msg):
        update_both_tables(columns, [msg.text], condition)
        bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)

    bot.register_next_step_handler(bot.send_message(chat_id, 'Какие слова будем искать теперь?'), update)


def get_areas(msg, user_query=None, hh_dicts=None, user_text_query=None,
              update=False, upd_cols=None, upd_cond=None):
    suggested_areas, query_areas, text_query_areas = [], set(), set()
    # TODO check if user wants only remote work

    for word in msg.text.split(','):
        word = word.strip()
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
            #  'errors': [{'value': 'text', 'type': 'bad_argument'}], 'request_id': '...'}
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
                    bot.reply_to(msg, 'Не разобрал. Проверь на предмет опечаток и повтори, пожалуйста.')
                    # not sure if this is ok
                    return bot.register_next_step_handler(msg, get_areas, user_query, hh_dicts,
                                                          user_text_query, update, upd_cols, upd_cond)
        else:
            if not update:
                user_query['areas'].add(hh_dicts['areas'][word.lower()])
                user_text_query['areas'].add(word.title())
            else:
                query_areas.add(hh_dicts['areas'][word.lower()])
                text_query_areas.add(word.title())

    if suggested_areas:
        suggested_areas_keyboard = telebot.types.ReplyKeyboardMarkup()
        for area in suggested_areas:
            suggested_areas_keyboard.add(telebot.types.KeyboardButton(area))
        suggested_areas_keyboard.add(telebot.types.KeyboardButton('Далее'))

        bot.send_message(msg.chat.id, 'Я кое-что не разобрал, позволь уточню. '
                                      'Как закончишь - жми "Далее" в конце списка.',
                         reply_markup=suggested_areas_keyboard)
        if not update:
            bot.register_next_step_handler(msg, handle_suggested_areas, user_query, hh_dicts, user_text_query)
        else:
            bot.register_next_step_handler(msg, handle_suggested_areas, query_areas, hh_dicts,
                                           text_query_areas, update, upd_cols, upd_cond)
    else:
        if not update:
            get_experience(msg, user_query, hh_dicts, user_text_query)
        else:
            update_both_tables(upd_cols, [query_areas], upd_cond, ', '.join(text_query_areas))
            bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)


def update_areas(chat_id, columns, condition):
    hh_dicts = hh_utils.get_hh_dicts()
    bot.register_next_step_handler(bot.send_message(chat_id, 'Где будем искать работу теперь? '
                                                             'Точно так же напиши мне город или страну. '
                                                             'И снова можно несколько, но через запятую.'),
                                   get_areas, None, hh_dicts, None, True, columns, condition)


# TODO remake for update
def handle_suggested_areas(msg, user_query=None, hh_dicts=None, user_text_query=None,
                           update=False, upd_cols=None, upd_cond=None):
    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            if not update:
                get_experience(msg, user_query, hh_dicts, user_text_query)
            else:
                update_both_tables(upd_cols, [user_query], upd_cond, [', '.join(user_text_query)])
                bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
        elif msg.text.lower() in hh_dicts['areas'].keys():
            if not update:
                user_query['areas'].add(hh_dicts['areas'][msg.text.lower()])
                user_text_query['areas'].add(msg.text.title())
                bot.register_next_step_handler(msg, handle_suggested_areas, user_query, hh_dicts, user_text_query)
            else:
                user_query.add(hh_dicts['areas'][msg.text.lower()])
                user_text_query.add(msg.text.title())
                bot.register_next_step_handler(msg, handle_suggested_areas, user_query,
                                               hh_dicts, user_text_query, update, upd_cols, upd_cond)
        else:
            else_function(msg, bot.register_next_step_handler,
                          msg, handle_suggested_areas, user_query, hh_dicts, user_text_query,
                          update, upd_cols, upd_cond)


def get_experience(msg, user_query=None, hh_dicts=None, user_text_query=None,
                   update=False, upd_cols=None, upd_cond=None):
    experience_keyboard = telebot.types.ReplyKeyboardMarkup()
    for experience in hh_dicts['experiences'].keys():
        experience_keyboard.add(telebot.types.KeyboardButton(experience))

    if not update:
        bot.send_message(msg.chat.id, 'Теперь скажи, какой у тебя опыт?', reply_markup=experience_keyboard)
    else:
        msg = bot.send_message(msg, 'У тебя изменился опыт?', reply_markup=experience_keyboard)
    bot.register_next_step_handler(msg, handle_experience, user_query, hh_dicts, user_text_query,
                                   update, upd_cols, upd_cond)


def update_experience(chat_id, columns, condition):
    hh_dicts = hh_utils.get_hh_dicts()
    get_experience(chat_id, None, hh_dicts, None, True, columns, condition)


def handle_experience(msg, user_query=None, hh_dicts=None, user_text_query=None,
                      update=False, upd_cols=None, upd_cond=None):
    if msg.chat.type == 'private' and msg.text in hh_dicts['experiences']:
        if not update:
            user_query['experience'] = hh_dicts['experiences'][msg.text]
            user_text_query['experience'] = msg.text
            get_salary(msg, user_query, hh_dicts, user_text_query)
        else:
            update_both_tables(upd_cols, [hh_dicts['experiences'][msg.text]], upd_cond, [msg.text])
            bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
    else:
        else_function(msg, bot.register_next_step_handler,
                      msg, handle_experience, user_query, hh_dicts, user_text_query,
                      update, upd_cols, upd_cond)


def get_salary(msg, user_query=None, hh_dicts=None, user_text_query=None,
               update=False, upd_cols=None, upd_cond=None, call_from_handler=False):
    salary_keyboard = telebot.types.ReplyKeyboardMarkup()
    for salary in hh_dicts['only_with_salaries'].keys():
        salary_keyboard.add(telebot.types.KeyboardButton(salary))

    if not call_from_handler:
        if not update:
            bot.send_message(msg.chat.id, 'Отлично. А какая зарплата интересует?', reply_markup=salary_keyboard)
        else:
            try:
                msg = bot.send_message(msg, 'Какова желаемая з/п теперь?', reply_markup=salary_keyboard)
            except telebot.apihelper.ApiTelegramException:
                msg = bot.send_message(msg.chat.id, 'Какова желаемая з/п теперь?', reply_markup=salary_keyboard)
    bot.register_next_step_handler(msg, handle_salary, user_query, hh_dicts, user_text_query,
                                   update, upd_cols, upd_cond, salary_keyboard)


def update_salary(chat_id, columns, condition):
    hh_dicts = hh_utils.get_hh_dicts()
    get_salary(chat_id, None, hh_dicts, None, True, columns, condition)


# TODO fix ONLY_WITH_SALARY hardcode
def handle_salary(msg, user_query=None, hh_dicts=None, user_text_query=None,
                  update=False, upd_cols=None, upd_cond=None, keyboard=None):
    if msg.chat.type == 'private':
        if msg.text in hh_dicts['only_with_salaries'].keys():
            if not update:
                user_query['salary'] = None
                user_query['only_with_salary'] = hh_dicts['only_with_salaries'][msg.text]
                user_text_query['salary'] = msg.text
                get_employments(msg, user_query, hh_dicts, user_text_query)
            else:
                with contextlib.closing(create_connection(config.DB_NAME)) as connection:
                    update_from_list(connection, config.QUERIES_TABLE_NAME, upd_cols,
                                     [None], upd_cond)
                    update_from_list(connection, config.QUERIES_TABLE_NAME, ['ONLY_WITH_SALARY'],
                                     [hh_dicts['only_with_salaries'][msg.text]], upd_cond)
                    update_from_list(connection, config.TEXT_QUERIES_TABLE_NAME, upd_cols, [msg.text], upd_cond)
                bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
        else:
            try:
                user_salary = int(msg.text)
                assert user_salary > 0
                if not update:
                    user_query['salary'] = user_salary
                    user_query['only_with_salary'] = None
                    user_text_query['salary'] = msg.text
                    get_employments(msg, user_query, hh_dicts, user_text_query)
                else:
                    with contextlib.closing(create_connection(config.DB_NAME)) as connection:
                        update_from_list(connection, config.QUERIES_TABLE_NAME, upd_cols,
                                         [user_salary], upd_cond)
                        update_from_list(connection, config.QUERIES_TABLE_NAME, ['ONLY_WITH_SALARY'],
                                         [None], upd_cond)
                        update_from_list(connection, config.TEXT_QUERIES_TABLE_NAME, upd_cols, [msg.text], upd_cond)
                    bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
            except (ValueError, AssertionError):
                get_salary(bot.reply_to(msg, 'Похоже, тут где-то опечатка.\n'
                                             'Так какую зарплату ты хочешь?',
                                        reply_markup=keyboard),
                           user_query, hh_dicts, user_text_query,
                           update, upd_cols, upd_cond, call_from_handler=True)


def get_employments(msg, user_query=None, hh_dicts=None, user_text_query=None,
                    update=False, upd_cols=None, upd_cond=None):
    employment_keyboard = telebot.types.ReplyKeyboardMarkup()
    for employment in hh_dicts['employments'].keys():
        employment_keyboard.add(telebot.types.KeyboardButton(employment))
    employment_keyboard.add(telebot.types.KeyboardButton('Далее'))

    if not update:
        user_query['employments'] = set()
        user_text_query['employments'] = set()
        bot.send_message(msg.chat.id, 'Какой тип занятости тебя интересует?\n'
                                      'Можешь выбрать несколько вариантов, потом жми "Далее".',
                         reply_markup=employment_keyboard)
    else:
        user_query = set()
        user_text_query = set()
        msg = bot.send_message(msg, 'Какой тип занятости интересует теперь?\n'
                                    'Так же можно выбрать несколько вариантов, но потом не забудь нажать "Далее".',
                               reply_markup=employment_keyboard)
    bot.register_next_step_handler(msg, handle_employment, user_query, hh_dicts, user_text_query,
                                   update, upd_cols, upd_cond)


def update_employments(chat_id, columns, condition):
    hh_dicts = hh_utils.get_hh_dicts()
    get_employments(chat_id, None, hh_dicts, None, True, columns, condition)


def handle_employment(msg, user_query=None, hh_dicts=None, user_text_query=None,
                      update=False, upd_cols=None, upd_cond=None):
    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            if not update:
                get_schedules(msg, user_query, hh_dicts, user_text_query)
            else:
                update_both_tables(upd_cols, [user_query], upd_cond, [', '.join(user_text_query)])
                bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
        elif msg.text in hh_dicts['employments'].keys():
            if hh_dicts['employments'][msg.text] is None:
                if not update:
                    user_query['employments'] = None
                    user_text_query['employments'] = msg.text
                    get_schedules(msg, user_query, hh_dicts, user_text_query)
                else:
                    update_both_tables(upd_cols, [None], upd_cond, [msg.text])
                    bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
            else:
                if not update:
                    user_query['employments'].add(hh_dicts['employments'][msg.text])
                    user_text_query['employments'].add(msg.text)
                else:
                    user_query.add(hh_dicts['employments'][msg.text])
                    user_text_query.add(msg.text)
                bot.register_next_step_handler(msg, handle_employment, user_query, hh_dicts, user_text_query,
                                               update, upd_cols, upd_cond)

        else:
            else_function(msg, bot.register_next_step_handler,
                          msg, handle_employment, user_query, hh_dicts, user_text_query,
                          update, upd_cols, upd_cond)


def get_schedules(msg, user_query=None, hh_dicts=None, user_text_query=None,
                  update=False, upd_cols=None, upd_cond=None):
    schedule_keyboard = telebot.types.ReplyKeyboardMarkup()
    for schedule in hh_dicts['schedules'].keys():
        schedule_keyboard.add(telebot.types.KeyboardButton(schedule))
    schedule_keyboard.add(telebot.types.KeyboardButton('Далее'))

    if not update:
        user_query['schedules'] = set()
        user_text_query['schedules'] = set()
        bot.send_message(msg.chat.id, 'Почти закончили. Какой график работы хочешь?\n'
                                      'Можешь выбрать несколько вариантов, потом жми "Далее".',
                         reply_markup=schedule_keyboard)
    else:
        user_query = set()
        user_text_query = set()
        msg = bot.send_message(msg, 'Какой график хочешь теперь?\n'
                                    'Так же можно выбрать несколько вариантов, но потом не забудь нажать "Далее".',
                               reply_markup=schedule_keyboard)
    bot.register_next_step_handler(msg, handle_schedule, user_query, hh_dicts, user_text_query,
                                   update, upd_cols, upd_cond)


def update_schedules(chat_id, columns, condition):
    hh_dicts = hh_utils.get_hh_dicts()
    get_schedules(chat_id, None, hh_dicts, None, True, columns, condition)


def handle_schedule(msg, user_query=None, hh_dicts=None, user_text_query=None,
                    update=False, upd_cols=None, upd_cond=None):
    if msg.chat.type == 'private':
        if msg.text == 'Далее':
            if not update:
                get_subscription(msg, user_query, user_text_query)
            else:
                update_both_tables(upd_cols, [user_query], upd_cond, [', '.join(user_text_query)])
                bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
        elif msg.text in hh_dicts['schedules'].keys():
            if hh_dicts['schedules'][msg.text] is None:
                if not update:
                    user_query['schedules'] = None
                    user_text_query['schedules'] = msg.text
                    get_subscription(msg, user_query, user_text_query)
                else:
                    update_both_tables(upd_cols, [None], upd_cond, [msg.text])
                    bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
            else:
                if not update:
                    user_query['schedules'].add(hh_dicts['schedules'][msg.text])
                    user_text_query['schedules'].add(msg.text)
                else:
                    user_query.add(hh_dicts['schedules'][msg.text])
                    user_text_query.add(msg.text)
                bot.register_next_step_handler(msg, handle_schedule, user_query, hh_dicts, user_text_query,
                                               update, upd_cols, upd_cond)
        else:
            else_function(msg, bot.register_next_step_handler,
                          msg, handle_schedule, user_query, hh_dicts, user_text_query,
                          update, upd_cols, upd_cond)


def get_subscription(msg, user_query, user_text_query):
    subscription_keyboard = telebot.types.ReplyKeyboardMarkup()
    subscription_keyboard.add(telebot.types.KeyboardButton('Давай регулярно'))
    subscription_keyboard.add(telebot.types.KeyboardButton('Только сейчас'))

    bot.send_message(msg.chat.id, 'Присылать тебе вакансии регулярно или только сейчас?',
                     reply_markup=subscription_keyboard)
    bot.register_next_step_handler(msg, handle_subscription, user_query, user_text_query)


def handle_subscription(msg, user_query, user_text_query):
    if msg.chat.type == 'private' and msg.text == 'Давай регулярно':
        get_period(msg, user_query, user_text_query, subscribe=True)
    elif msg.chat.type == 'private' and msg.text == 'Только сейчас':
        bot.send_message(msg.chat.id, 'Ну ладно. Тогда последний вопрос. За сколько дней интересуют вакансии?\n'
                                      'Напиши число от 1 до 30.', reply_markup=REPLY_KEYBOARD_REMOVE)
        bot.register_next_step_handler(msg, handle_period, user_query, user_text_query,
                                       False, None, None, False)
    else:
        else_function(msg, bot.register_next_step_handler,
                      msg, handle_subscription, user_query, user_text_query)


def get_period(msg, user_query, user_text_query, update=False, upd_cols=None, upd_cond=None, subscribe=False):
    if not update:
        bot.send_message(msg.chat.id, 'Тогда последний вопрос. Как часто хочешь получать новые вакансии?\n'
                                      'Напиши число от 1 до 30.', reply_markup=REPLY_KEYBOARD_REMOVE)
    else:
        msg = bot.send_message(msg, 'Как часто присылать тебе новые вакансии теперь?\n'
                                    'Напиши число от 1 до 30.', reply_markup=REPLY_KEYBOARD_REMOVE)
    bot.register_next_step_handler(msg, handle_period, user_query, user_text_query,
                                   update, upd_cols, upd_cond, subscribe)


def update_period(chat_id, columns, condition):
    get_period(chat_id, None, None, True, columns, condition)


def handle_period(msg, user_query, user_text_query, update=False, upd_cols=None, upd_cond=None, subscribe=False):
    try:
        user_period = int(msg.text)
        assert 1 <= user_period <= 30
        if not update:
            user_query['period'] = user_period
            user_text_query['period'] = user_period
            publish_vacancies(msg, user_query, user_text_query, subscribe)
        else:
            update_both_tables(upd_cols, [user_period], upd_cond)
            bot.send_message(msg.chat.id, 'Обновил!', reply_markup=REPLY_KEYBOARD_REMOVE)
    except (ValueError, AssertionError):
        bot.reply_to(msg, 'Я же просил число от 1 до 30.')
        bot.register_next_step_handler(msg, handle_period, user_query, user_text_query,
                                       update, upd_cols, upd_cond, subscribe)


def publish_vacancies(msg, user_query, user_text_query=None, subscribe=False, mail=False):
    uq_keys = UserQuery.__annotations__.keys()
    for key in uq_keys:
        if isinstance(user_query[key], str) and user_query[key].startswith('{'):
            user_query[key] = ast.literal_eval(user_query[key])

    # 'search_field': ['name', 'description'],
    parameters = {
        'text': user_query['vacancy'],
        'area': list(user_query['areas']),
        'period': user_query['period']
    }

    for key, op in zip(['experience', 'employments', 'schedules', 'salary', 'only_with_salary'],
                       [str, list, list, str, str]):
        hh_utils.copy_pair(user_query, parameters, key, operation=op)

    if subscribe:
        user_query['counter'] = user_query['period']
        with contextlib.closing(create_connection(config.DB_NAME)) as connection:
            insert_from_dict(connection, config.QUERIES_TABLE_NAME, user_query)
            insert_from_dict(connection, config.TEXT_QUERIES_TABLE_NAME, user_text_query)

    response = httpx.get('https://api.hh.ru/vacancies', params=parameters).json()

    if response['items']:
        if not mail:
            bot.send_message(msg.chat.id, "Вот, что я нашел по твоим параметрам:")
        else:
            msg = bot.send_message(msg, f"Новые вакансии по твоей подписке {user_query['vacancy']}:")

        # result_string = ''
        for vacancy in response['items']:
            # result_string += f"{vacancy['name']}\n{vacancy['employer']['name']}\n" \
            #                  f"ЗП: {vacancy['salary']['from']}-{vacancy['salary']['to']}\n" \
            #                  f"{vacancy['alternate_url']}\n"
            bot.send_message(msg.chat.id, hh_utils.build_msg(vacancy))
        # bot.send_message(msg.chat.id, result_string)
    else:
        if not mail:
            bot.send_message(msg.chat.id, "Я ничего не нашел по твоим параметрам.")
        else:
            bot.send_message(msg, f"Новые вакансии по твоей подписке {user_query['vacancy']} отсутствуют. "
                                  f"Может, повезет в следующий раз!")


def mailing():
    with contextlib.closing(create_connection(config.DB_NAME)) as connection:
        queries = simple_select(connection, config.QUERIES_TABLE_NAME, '*')

    uq_keys = UserQuery.__annotations__.keys()
    for query in queries:
        user_query: UserQuery = {k: v if v != 'None' else None for k, v in zip(uq_keys, query)}
        counter = int(query[-1]) - 1
        if counter == 0:
            publish_vacancies(query[0], user_query, mail=True)
            with contextlib.closing(create_connection(config.DB_NAME)) as connection:
                update_from_list(connection, config.QUERIES_TABLE_NAME, ['COUNTER'], [user_query['period']],
                                 f"USER_ID = {repr(str(user_query['user_id']))} "
                                 f"AND VACANCY = {repr(str(user_query['vacancy']))}")
        else:
            with contextlib.closing(create_connection(config.DB_NAME)) as connection:
                update_from_list(connection, config.QUERIES_TABLE_NAME, ['COUNTER'], [counter],
                                 f"USER_ID = {repr(str(user_query['user_id']))} "
                                 f"AND VACANCY = {repr(str(user_query['vacancy']))}")


def update_both_tables(upd_cols, upd_values, upd_cond, upd_txt_values=None):
    with contextlib.closing(create_connection(config.DB_NAME)) as connection:
        update_from_list(connection, config.QUERIES_TABLE_NAME, upd_cols, upd_values, upd_cond)
        if upd_txt_values:
            update_from_list(connection, config.TEXT_QUERIES_TABLE_NAME, upd_cols, upd_txt_values, upd_cond)
        else:
            update_from_list(connection, config.TEXT_QUERIES_TABLE_NAME, upd_cols, upd_values, upd_cond)


def else_function(msg, func, *func_args):
    if msg.text == '/start':
        start(msg)
    else:
        bot.reply_to(msg, 'Такого не понимаю.\nТыкай на кнопки.')
        func(*func_args)


# update hh_dicts and send vacancies everyday
scheduler = BackgroundScheduler()
scheduler.add_job(hh_utils.update_hh_dicts, 'cron', hour=0)
scheduler.add_job(mailing, 'cron', hour=12)
scheduler.start()

bot.infinity_polling()
