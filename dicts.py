from typing import Dict, TypedDict, Union, Optional


class UserQuery(TypedDict, total=False):
    user_id: Optional[int]
    vacancy: str
    areas: Union[set, str]
    experience: str
    salary: Union[int, str]
    only_with_salary: Optional[str]
    employments: Union[set, str]
    schedules: str
    period: Union[int, str]


def get_user_query_russian_text():
    uq_russian: UserQuery = {
        'user_id': None,
        'vacancy': 'Ключевые слова',
        'areas': 'Регион',
        'experience': 'Опыт',
        'salary': 'Желаемая з/п',
        'only_with_salary': None,
        'employments': 'Тип занятости',
        'schedules': 'График',
        'period': 'Периодичность рассылки'
    }
    return uq_russian


def create_user_query(values):
    uq_keys = UserQuery.__annotations__.keys()
    if len(values) == len(uq_keys):
        user_query: UserQuery = {k: v for k, v in zip(uq_keys, values)}
        return user_query
    else:
        # TODO log
        pass


class HHDicts(TypedDict):
    areas: Dict[str, str]
    experiences: Dict[str, str]
    only_with_salaries: Dict[str, str]
    employments: Dict[str, str]
    schedules: Dict[str, str]


class UserTextQuery(TypedDict, total=False):
    user_id: Optional[int]
    vacancy: str
    areas: Union[set, str]
    experience: str
    salary: Union[int, str]
    employments: Union[set, str]
    schedules: str
    period: Union[int, str]
