# -*- coding: utf-8 -*-
"""
Приложение для хранения данных о пользователях.

"""
import os
import json

import pika
from pika.adapters.tornado_connection import TornadoConnection

import pymongo
from pymongo import MongoClient
from bson.objectid import ObjectId

import tornado.ioloop
from tornado.options import define, options

 
MONGODB_HOST = "localhost"
MONGODB_PORT = 27017
MONGODB_BASE_NAME = 'user_auth'
MONGODB_COLLECTION_NAME = 'users'
AMPQ_URL = 'amqp://guest:guest@localhost:5672/'

define("mongodb_host", default=MONGODB_HOST, help="MongoDB host")
define("mongodb_port", default=MONGODB_PORT, help="MongoDB port")
define("mongodb_base_name", default=MONGODB_BASE_NAME,
       help="MongoDB base name")
define("mongodb_collection_name", default=MONGODB_COLLECTION_NAME,
       help="MongoDB collection name")
define("ampq_url", default=AMPQ_URL, help="url for link to RabbitMQ")
  

class BasePikaClient(object):
    """
    Базовый класс для работы с очередями


    """
    WEBTODATA_QUEUE_NAME = 'web_to_data'
    DATATOWEB_QUEUE_NAME = 'data_to_web'

    def __init__(self, amqp_url):
        self._amqp_url = amqp_url


    def connect(self):
        self.connection = TornadoConnection(pika.URLParameters(self._amqp_url),
                          on_open_callback=self.on_connected)


    def on_connected(self, connection):
        self.connection = connection
        self.connection.channel(self.on_channel_open)


    def on_channel_open(self, channel):
        """
        Действия при создании канала.

        Потомки должны расширить этот метод,
        добавив создание очередей и/или точек обмена.
        """
        self.channel = channel
        self.channel.add_on_cancel_callback(self.on_cancelled)


    def on_cancelled(self, method_frame):
        if self.channel:
            self.channel.close()


    def declare_queue(self, queue_name, on_queue_declare_ok=None):
        on_queue_declare_ok = on_queue_declare_ok or self.on_queue_declare_ok
        self.channel.queue_declare(on_queue_declare_ok, queue_name)


    def on_queue_declare_ok(self, method_frame):
        """
        Действия при создании очереди.

        Потомки могут переопределить этот метод,
        добавив создание привязок очередей к точкам обмена.
        """
        pass


    def declare_exchange(self, exhange_name, exhange_type):
        self._channel.exchange_declare(self.on_exchange_declare_ok,
                                       exhange_name, exhange_type)


    def on_exchange_declare_ok(self, frame):
        """
        Действия при создании точки обмена.

        Потомки могут переопределить этот метод,
        добавив создание очередей.
        """
        pass


    def send(self, exchange_name, queue_name, message):
        self.channel.basic_publish(exchange_name, queue_name, message)


class MongoStorage(object):
    """
    Управление данными о пользователях в MongoDB

    """

    def __init__(self, host, port, db_name, collection_name):
        self._host = host
        self._port = port
        self._db_name = db_name
        self._collection_name = collection_name

        self._client = MongoClient(host, port)
        self._db = self._client[db_name]
        self._collection = self._db[collection_name]

        # Доступные команды
        self.commands = {
            'add_user': self.add_user,
            'get_user': self.get_user,
            'delete_user': self.delete_user,
            'update_user': self.update_user,
            'get_user_list': self.get_user_list,
        }


    def command(self, data):
        """
        Обработка команд от web приложения

        """
        cmd = data.pop('command', None)
        if cmd is None:
            print("Command expected")
        try:
            result = self.commands.get(cmd, self.unknown_command)(data)
            return {'ok': {'command': cmd, 'result': result}}
        except Exception as exc:
            print(exc)
            return {'error': {'command': cmd, 'message': str(exc)}}


    def unknown_command(self, data):
        print("Unknown command")
        return {'error': {'message': "Unknown command"}}


    @staticmethod
    def _id_to_str(dct):
        """
        Заменяет ObjectId на строку

        """
        dct['id'] = str(dct.pop('_id'))
        return dct

    def add_user(self, data):
        """
        Добавляет пользователя

        """
        self._collection.insert_one(data)
        self._id_to_str(data)
        return data


    def get_user(self, data):
        """
        Возвращает информацию о пользователе по id

        """
        user_id = ObjectId(data['id'])
        user = self._collection.find_one({'_id': user_id})
        self._id_to_str(user)
        return data


    def delete_user(self, data):
        """
        Удаляет пользователя по id

        """
        user_id = data['id']
        self._collection.delete_one({'_id': ObjectId(user_id)})
        return {'id': user_id}


    def update_user(self, data):
        """
        Обновляет данные о пользователе

        """
        user_id = ObjectId(data['id'])
        self._collection.replace_one({'_id': user_id}, data)
        user = self._collection.find_one({'_id': user_id})
        self._id_to_str(user)
        return user


    def get_user_list(self, data):
        """
        Возвращает список всех пользователей

        """
        user_list = [self._id_to_str(user) for user in
                     self._collection.find()]
        return user_list


class DataPikaClient(BasePikaClient):
    """
    Класс для работы с очередями в приложении хранения данных


    """


    def __init__(self, amqp_url, storage):
        super(DataPikaClient, self).__init__(amqp_url)
        self._storage = storage


    def on_channel_open(self, channel):
        """
        Создаёт две очереди:
        для получения команд от web приложения
        и для отправки результатов web приложению

        """
        super(DataPikaClient, self).on_channel_open(channel)
        self.declare_queue(self.WEBTODATA_QUEUE_NAME,
                           self.set_receive_data)
        self.declare_queue(self.DATATOWEB_QUEUE_NAME)


    def set_receive_data(self, method_frame):
        """
        Получает команды от web приложения

        """
        self.channel.basic_consume(self.on_message,
                                   self.WEBTODATA_QUEUE_NAME)


    def on_message(self, channel, method, properties, body):
        """
        Передаёт команды от web приложения хранилищу.
        Посылает результат выполнения команды web приложению.

        """
        result = self._storage.command(json.loads(body.decode()))
        self.send('', self.DATATOWEB_QUEUE_NAME, json.dumps(result))
        self.channel.basic_ack(method.delivery_tag)


def main():
    tornado.options.parse_command_line()
    db = MongoStorage(options.mongodb_host, options.mongodb_port,
                      options.mongodb_base_name,
                      options.mongodb_collection_name)
    mq = DataPikaClient(options.ampq_url, db)
    mq.connect()
    tornado.ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()


