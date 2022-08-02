from typing import Tuple, Dict

import httpx


# TODO wrap httpx.get with try
def get_areas() -> Dict[str, str]:
    response = httpx.get('https://api.hh.ru/areas').json()
    areas = {}
    for country in response:
        areas[country['name'].lower()] = country['id']
        for region in country['areas']:
            areas[region['name'].lower()] = region['id']
            cities = region['areas']
            if cities:
                for city in cities:
                    areas[city['name'].lower()] = city['id']
    return areas


def get_dictionaries() -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str], Dict[str, str]]:
    response = httpx.get('https://api.hh.ru/dictionaries').json()
    # schedules, employments, experiences, only_with_salaries
    dicts = {}, {}, {}, {'Не имеет значения, но указана': 'true'}

    for dct, key in zip(dicts, ['schedule', 'employment', 'experience', None]):
        # noinspection PyTypeChecker
        dct['Не имеет значения'] = None
        copy_nested_dict(response, dct, key)

    return dicts


def copy_nested_dict(from_dict, to_dict, key):
    if check_key(from_dict, key):
        for value in from_dict[key]:
            to_dict[value['name']] = value['id']


def check_key(dictionary, key):
    return key in dictionary and dictionary[key]


def copy_pair(from_dict, to_dict, key, operation=str):
    if check_key(from_dict, key):
        to_dict[key] = operation(from_dict[key])


def build_msg(vacancy):
    vacancy_name = vacancy['name'] if check_key(vacancy, 'name') else 'Без названия'
    employer_name = vacancy['employer']['name'] if check_key(
        vacancy, 'employer') and check_key(vacancy['employer'], 'name') else 'Без названия'
    salary = 'Не указана'
    if check_key(vacancy, 'salary'):
        if check_key(vacancy['salary'], 'from') and check_key(vacancy['salary'], 'to'):
            salary = f"{vacancy['salary']['from']}-{vacancy['salary']['to']}"
        elif check_key(vacancy['salary'], 'from'):
            salary = f"от {vacancy['salary']['from']}"
        elif check_key(vacancy['salary'], 'to'):
            salary = f"до {vacancy['salary']['to']}"
    alternate_url = vacancy['alternate_url'] if check_key(vacancy, 'alternate_url') else 'Ссылка не найдена'

    return f"Вакансия: {vacancy_name}\nКомпания: {employer_name}\nЗ/П: {salary}\n{alternate_url}"
