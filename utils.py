import httpx


def get_areas():
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


def check_key(dictionary, key):
    return key in dictionary and dictionary[key]


def add_key_to_dict(from_dict, to_dict, key, operation=str):
    if check_key(from_dict, key):
        to_dict[key] = operation(from_dict[key])


def build_msg(vacancy):
    vacancy_name = vacancy['name'] if check_key(vacancy, 'name') else 'Без названия'
    employer_name = vacancy['employer']['name'] if check_key(
        vacancy, 'employer') and check_key(vacancy['employer'], 'name') else 'Без названия'
    salary = 'Не указана'
    if check_key(vacancy, 'salary'):
        if check_key(vacancy['salary'], 'from') and check_key(vacancy['salary'], 'to'):
            salary = vacancy['salary']['from'] + '-' + vacancy['salary']['to']
        elif check_key(vacancy['salary'], 'from'):
            salary = 'От ' + vacancy['salary']['from']
        elif check_key(vacancy['salary'], 'to'):
            salary = 'До ' + vacancy['salary']['to']
    alternate_url = vacancy['alternate_url'] if check_key(vacancy, 'alternate_url') else 'Ссылка не найдена'

    return f"Вакансия: {vacancy_name}\nКомпания: {employer_name}\nЗ/П: {salary}\n{alternate_url}"
