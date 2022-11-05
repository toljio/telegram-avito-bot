# -*- coding: utf-8 -*-
# export LC_ALL='en_US.utf8'

import json
import os
import random
import time

import requests
from bs4 import BeautifulSoup
from requests import RequestException

from config import Config

key = Config.AVITO_KEY # ключ, с которым всё работает, не разбирался где его брать, но похоже он статичен, т.к. гуглится на различных форумах
cookie = Config.AVITO_COOKIE # Если забанили, то добавьте свои куки, это не боевой код но он делает то, что надо
proxy = {'http': 'http://188.124.250.138:8008'}
headers = { 'authority': 'm.avito.ru',
            'pragma': 'no-cache',
            'cache-control': 'no-cache',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.66 Mobile Safari/537.36',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'sec-fetch-site': 'none',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'accept-language': 'ru-RU,ru;q=0.9',
            'cookie': cookie
            }

def get_proxy():
    proxy = requests.get(
        'https://gimmeproxy.com/api/getProxy?country=RU&get=true&supportsHttps=true&protocol=http', verify=False)
    proxy_json = json.loads(proxy.content)
    if proxy.status_code != 200 and 'ip' not in proxy_json:
        raise RequestException
    else:
        return proxy_json['ip'] + ':' + proxy_json['port']

proxy_env = os.environ.get('AVITO_PROXY_HTTP')
if proxy_env:
    if proxy_env == "auto":
        proxy_list = [get_proxy()]
    else:
        proxy_list = os.environ.get('AVITO_PROXY_HTTP').split(",")
else:
    proxy_list = None


def get_ads_list(avito_search_pattern, log):
    search = avito_search_pattern['search']     # Строка поиска на сайте и ниже параметры выбора города, радиуса разброса цены и т.п.
    categoryId = avito_search_pattern['categoryId']
    locationId = avito_search_pattern['locationId']          # 621540 - All 107620 - MO+M
    searchRadius = 200
    priceMin = avito_search_pattern['priceMin']
    priceMax = avito_search_pattern['priceMax']
    sort = 'priceDesc'
    withImagesOnly = 'true'     # Только с фото
    limit_page = 50     # Количество объявлений на странице 50 максимум

    s = requests.Session()                          # Будем всё делать в рамках одной сессии
    s.headers.update(headers)                       # Сохраняем заголовки в сессию
    s.proxies=proxy
    # s.get('https://m.avito.ru/')                  # Делаем запрос на мобильную версию.
                                                    # https://m.avito.ru/api/2/search/main - cписок всех категорий
                                                    # https://m.avito.ru/api/1/slocations - cписок всех регионов
                                                    
    url_api_9 = 'https://m.avito.ru/api/9/items'    # Урл первого API, позволяет получить id и url объявлений по заданным фильтрам
                                                    # Тут уже видно цену и название объявлений
    params = {
        'categoryId': categoryId,
        'locationId': locationId,
        'searchRadius': searchRadius,
        'priceMin': priceMin,
        'priceMax': priceMax,
        'sort': sort,
        'withImagesOnly': withImagesOnly,
        'display': 'list',
        'limit': limit_page,
        'query': search,
    }
    cicle_stop = True       # Переменная для остановки цикла
    cikle = 0               # Переменная для перебора страниц с объявлениями
    items = []              # Список, куда складываем объявления
    params['key'] =  key

    while cicle_stop:
        cikle += 1          # Так как страницы начинаются с 1, то сразу же итерируем
        params['page'] = cikle
        res = s.get(url_api_9, params=params)
        try:
            res = res.json()
        except json.decoder.JSONDecodeError:
            log.error(res.status_code, res.text)
        if res['status'] != 'ok':
            log.error(res['result'])
        if res['status'] == 'ok':
            items_page = int(len(res['result']['items']))

            if items_page > limit_page: # проверка на "snippet"
                items_page = items_page - 1

            for item in res['result']['items']:
                if item['type'] == 'item':
                    items.append(item)
            if items_page < limit_page:
                cicle_stop = False
    timestamp = int(time.time())
    ads_list = []

    for ad in items:
        id = str(ad['value']['id'])
        name = str(ad['value']['title'])
        url = "https://www.avito.ru" + str(ad['value']['uri_mweb'])
        price = str(ad['value']['price'])
        created = str(ad['value']['time'])
        ads_list.append({
            'id': id,
            'title': name,
            'price': price,
            'created': created,
            'parsed': timestamp,
            'url': url,
        })
    return ads_list


def get_new_ads(new, old):
    _ = []
    old_ids = [l['id'] for l in old]
    for ad in new:
        if ad['id'] not in old_ids:
            _.append(ad)
    return _

def get_categories_ids():
    s = requests.Session()
    s.headers.update(headers)
    s.proxies=proxy
    res = s.get('https://m.avito.ru/api/2/search/main', params={'key': key})
    j=res.json()
    return j['categories']

def get_regions():
    s = requests.Session()
    s.headers.update(headers)
    s.proxies=proxy
    res = s.get('https://m.avito.ru/api/1/slocations', params={'key': key})
    j=res.json()
    return j['result']['locations']

if __name__ == '__main__':
    get_ads_list(None)