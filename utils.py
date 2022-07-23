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
