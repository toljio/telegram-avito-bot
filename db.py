from pymongo import MongoClient

from config import Config

client = MongoClient(Config.MONGO_URL, 27017)
db = client['mongoosito']
search_collection = db['search_collection']
search_data_interlayer = db['search_data_interlayer']


def save_search_to_temp(uid, filter):
    _remove_search_data_from_temp(uid)
    return search_data_interlayer.insert_one({'uid': uid, 'search': filter})

def save_categoryId_to_temp(uid, categoryId):
    search_data_interlayer.update_one({'uid': uid}, {'$set': {'categoryId': categoryId}}, upsert=True)

def save_locationId_to_temp(uid, locationId):
    search_data_interlayer.update_one({'uid': uid}, {'$set': {'locationId': locationId}}, upsert=True)

def save_priceMin_to_temp(uid, priceMin):
    search_data_interlayer.update_one({'uid': uid}, {'$set': {'priceMin': priceMin}}, upsert=True)

def save_priceMax_to_temp(uid, priceMax):
    search_data_interlayer.update_one({'uid': uid}, {'$set': {'priceMax': priceMax}}, upsert=True)

def _remove_search_data_from_temp(uid):
    search_data_interlayer.delete_many({'uid': uid})


def get_temp_search_data(uid):
    search_data = search_data_interlayer.find_one({'uid': uid},{'uid':False, '_id': False})
    _remove_search_data_from_temp(uid)
    return search_data


def save_search_data(uid, search_data, log):
    """
    :param uid: идентификатор чата
    :param search_data: параметры для поиска
    :return boolean: запись добавлена / не добавлена (ошибка бд)
    """
    from app import parserr
    try:
        search_collection.update_one({'uid': uid}, {'$push': {'tracking_searches': {
            'search_data': search_data,
            'ads': parserr.get_ads_list(search_data, log)
        }}}, upsert=True)
        return True
    except:
        return False


def get_search_collection_entries():
    return list(search_collection.find({}))


def get_users_tracking_searches_list(uid):
    """
    :param uid: telegram user id
    :return: list of dicts [{'search_data': ''}]
    """
    user = search_collection.find_one({'uid': uid},{'uid':False, '_id': False})

    if not user:
        return None

    tracking_searches = user['tracking_searches']

    _ = []
    for u in tracking_searches:
        _.append({
            'search_data': u['search_data']
        })
    return _


def delete_search_data_from_tracking(uid, human_index):
    """
    :param uid:
    :param human_index: > 0, [12, 45, 17] human_index = 1 : 12, human_index = 3 : 17
    :return: boolean
    """
    user = search_collection.find_one({'uid': uid})

    if not user:
        return None

    tracking_searches = user['tracking_searches']
    try:
        del tracking_searches[human_index - 1]
        search_collection.update_one({'uid': uid}, {'$set': {
            'tracking_searches': tracking_searches
        }})
        return True
    except:
        return False


def set_actual_ads(uid, tracking_searches):
    search_collection.update_one({'uid': uid}, {'$set': {
        'tracking_searches': tracking_searches
    }})
