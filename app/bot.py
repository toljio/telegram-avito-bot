import datetime
import threading
import time

import flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

import db
import utils
from app.parserr import get_ads_list, get_new_ads, get_regions, get_categories_ids
from config import Config

class Bot(threading.Thread):

    def __init__(self, tg_token, bot_users, app):
        super().__init__()
        self.tg_token = tg_token
        self.app = app
        self.bot_users = bot_users
        self.l = app.logger
        self.bot = telebot.TeleBot(self.tg_token)

    def run(self):
        self.l.info("Bot starting")
        self.init_commands()
        self.use_webhooks(Config.WEBHOOK_ENABLE)

    def use_webhooks(self, value):
        bot = self.bot
        app = self.app
        bot.remove_webhook()
        time.sleep(0.1)
        if value:
            if not Config.WEBHOOK_HOST:
                raise Exception("WEBHOOK_HOST is not defined")

            @app.route('/', methods=['GET', 'HEAD'])
            def index():
                return ''

            @app.route(Config.WEBHOOK_URL_PATH, methods=['POST'])
            def webhook():
                if flask.request.headers.get('content-type') == 'application/json':
                    json_string = flask.request.get_data().decode('utf-8')
                    update = telebot.types.Update.de_json(json_string)
                    bot.process_new_updates([update])
                    self.l.debug("hook: " + json_string)
                    return ''
                else:
                    flask.abort(403)

            bot.set_webhook(url=Config.WEBHOOK_URL_BASE + Config.WEBHOOK_URL_PATH,
                            certificate=open(Config.WEBHOOK_SSL_CERT, 'r'))
        else:
            while (True):
                try:
                    bot.polling(none_stop=True)
                except BaseException as e:
                    self.l.error(e)
                    time.sleep(30)
        self.l.info("Webhook enabled: " + str(value))

    def init_commands(self):
        bot = self.bot
        app = self.app

        def is_allowed(message):
            return message.chat.title is None and (self.bot_users is None or message.from_user.id in self.bot_users)

        @bot.message_handler(commands=['help', 'start'], func=lambda message: is_allowed(message))
        def send_welcome(message):
            msg = bot.send_message(message.chat.id, 'Данный бот следит за объявлениями по указанным параметрам (название, город, раздел и цена) '
                                                    'и присылает новые. '
                                                    '\nНажмите на значек "/" для просмотра доступных команд.')

        # # # Adding search # # #
        @bot.message_handler(commands=['add'], func=lambda message: is_allowed(message))
        def add_search(message):
            bot.send_message(message.chat.id,
                             'Что ищем? Пример: алгоритмы кормен\n')
            msg = bot.send_message(message.chat.id, 'Ожидаю запрос...')
            bot.register_next_step_handler(msg, waiting_step_search)

        def waiting_step_search(message):
            search_text = str(message.text)
            try:
                db.save_search_to_temp(message.chat.id, search_text)
            except:
                msg = bot.send_message(message.chat.id, 'Ошибка сервера. Повторите попытку позже.')
                return
            msg = bot.send_message(message.chat.id, 'Минимальная цена (руб).')
            bot.register_next_step_handler(msg, waiting_step_priceMin)

        def waiting_step_priceMin(message):
            db.save_priceMin_to_temp(message.chat.id, message.text)
            msg = bot.send_message(message.chat.id, 'Максимальная цена (руб).')
            bot.register_next_step_handler(msg, waiting_step_priceMax)

        def waiting_step_priceMax(message):
            db.save_priceMax_to_temp(message.chat.id, message.text)
            markup=InlineKeyboardMarkup()
            for cat in sorted(get_categories_ids(), key=lambda x: x['id']):
                markup.add(InlineKeyboardButton(cat['name'], callback_data = waiting_step_categoryId(message.chat.id, cat['id'])))
                if 'children' in cat:
                    for child in sorted(cat['children'], key=lambda x: x['id']):
                        markup.add(InlineKeyboardButton("--"+cat['name'], callback_data = waiting_step_categoryId(message.chat.id, cat['id'])))

            msg = bot.send_message(message.chat.id, 'ID категории (полный список можно получить через /categories). Например: 83')
            bot.register_next_step_handler(msg, waiting_step_categoryId,reply_markup=markup)

        def waiting_step_categoryId(chatId, message):
            db.save_categoryId_to_temp(chatId, message)
            msg = bot.send_message(chatId, 'ID локации (полный список можно получить через /regions). Например: 621540')
            bot.register_next_step_handler(msg, waiting_step_locationId)

        def waiting_step_locationId(message):
            db.save_locationId_to_temp(message.chat.id, message.text)

            try:
                search_params = db.get_temp_search_data(message.chat.id)
            except:
                bot.send_message(message.chat.id, 'Ошибка сервера. Повторите попытку позже.')
                return

            if db.save_search_data(message.chat.id, search_params, self.l):
                bot.send_message(message.chat.id, 'Поиск сохранен. Теперь вы будете получать уведомления о новых объявлениях.')
            else:
                bot.send_message(message.chat.id, 'Произошла ошибка при добавлении. Повторите ошибку позже.')

        # # # End adding search # # #

        def send_tracking_searches_list(uid):
            user_tracking_searches_list = db.get_users_tracking_searches_list(uid)

            if not user_tracking_searches_list:
                bot.send_message(uid, 'Вы не ничего отслеживаете.')
                return

            msg = ''
            i = 1
            for search in user_tracking_searches_list:
                msg += str(i) + '. ' + str(search['search_data'])
                msg += '\n' + "---------" + '\n'
                i += 1

            bot.send_message(uid, msg, disable_web_page_preview=True)

        # # # Deleting search # # #
        @bot.message_handler(commands=['delete'], func=lambda message: is_allowed(message))
        def deleting_search(message):
            if not db.get_users_tracking_searches_list(message.chat.id):
                bot.send_message(message.chat.id, 'Вы ничего не отслеживаете.')
                return
            send_tracking_searches_list(uid=message.chat.id)
            msg = bot.send_message(message.chat.id, 'Отправьте порядковый номер удаляемой ссылки.')
            bot.register_next_step_handler(msg, waiting_num_to_delete)

        def waiting_num_to_delete(message):
            try:
                delete_index_in_list = int(message.text)
            except:
                bot.send_message(message.chat.id, 'Отправьте только число.')
                return

            if delete_index_in_list <= 0:
                bot.send_message(message.chat.id, 'Порядковый номер должен быть больше нуля.')
                return

            if db.delete_search_data_from_tracking(message.chat.id, delete_index_in_list):
                bot.send_message(message.chat.id, 'Ссылка удалена из отслеживаемых.')
            else:
                bot.send_message(message.chat.id, 'Ошибка сервера. Повторите попытку позже.')

        # # # End deleting search # # #

        # # # Send list of tracking searches # # #
        @bot.message_handler(commands=['list'], func=lambda message: is_allowed(message))
        def send_list(message):
            send_tracking_searches_list(message.chat.id)

        # # # End send list of tracking searches # # #

        # # # Get list of regions # # #
        @bot.message_handler(commands=['regions'], func=lambda message: is_allowed(message))
        def send_regions(message):
            msg = ""
            for reg in get_regions():
                msg += str(reg['id']) + ': ' + reg['names']['1'] + '\n'
            bot.send_message(message.chat.id, msg)
        # # # End get list of regions # # #

        # # # Get list of regions # # #
        @bot.message_handler(commands=['categories'], func=lambda message: is_allowed(message))
        def send_categories_ids(message):
            msg=""
            for cat in sorted(get_categories_ids(), key=lambda x: x['id']):
                msg += str(cat['id']) + ': ' + cat['name'] + '\n'
                if 'children' in cat:
                    for child in sorted(cat['children'], key=lambda x: x['id']):
                        msg += '  ' + str(child['id']) + ': ' + child['name'] + '\n'
            bot.send_message(message.chat.id, msg)
        # # # End get list of regions # # #

        MSG = "{0}: {1}\n{2}\n{3}\n{4}"

        def send_updates():
            sce = db.get_search_collection_entries()

            for i in sce:
                tracking_searches = []
                for search in i['tracking_searches']:
                    old_ads = search['ads']
                    self.l.debug("handling updates for " + search['search_data']['search'])
                    actual_ads = get_ads_list(search['search_data'], self.l)
                    while not actual_ads:
                        time.sleep(5)
                        actual_ads = get_ads_list(search['search_data'], self.l)
                    self.l.debug(f'parsed ads count = {len(actual_ads)}')
                    new_ads = get_new_ads(actual_ads, old_ads)
                    if new_ads:
                        self.l.info(f'new_ads count = {len(new_ads)}')

                    for n_a in new_ads:
                        msg = MSG.format(search['search_data']['search'], n_a['title'].rstrip(), n_a['price'].rstrip(),
                                         n_a['created'].rstrip(),
                                         n_a['url'])
                        bot.send_message(i['uid'], msg)

                    timestamp = int(time.time())

                    filtered = [u for u in old_ads if 'parsed' in u and u['parsed'] + 604800 > timestamp]
                    search['ads'] = filtered
                    search['ads'].extend(new_ads)
                    self.l.debug(f"ads in db {str(len(search['ads']))}")
                    tracking_searches.append(search)

                    import random
                    time.sleep(random.randint(1, 15) / 10)
                db.set_actual_ads(i['uid'], tracking_searches)

        def in_between(now, start, end):
            if start <= end:
                return start <= now < end
            else:
                return start <= now or now < end

        def send_updates_thread():
            import schedule

            send_updates()
            schedule.every(Config.PARSING_INTERVAL_SEC).seconds.do(send_updates)

            while True:
                cur_time = datetime.datetime.now().time()
                if in_between(cur_time, datetime.time(Config.SLEEP_START),
                              datetime.time(Config.SLEEP_END)):
                    self.l.info(f"It's time to sleep for {str(Config.SLEEP_TIME)} hours!")
                    time.sleep(3600 * Config.SLEEP_TIME + 60)  # not accurate
                    self.l.info("Bot is waking up")

                n = schedule.idle_seconds()
                if n is None:
                    break
                elif n > 0:
                    time.sleep(n)   # sleep exactly the right amount of time
                schedule.run_pending()

        thread = threading.Thread(target=send_updates_thread)
        thread.start()