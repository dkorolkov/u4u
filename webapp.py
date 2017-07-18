# -*- coding: utf-8 -*-
"""
Управление пользователями.

"""
import os
import json

import pika
from pika.adapters.tornado_connection import TornadoConnection

import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web

from tornado.options import define, options
import tornado.websocket

from data_repository import BasePikaClient

AMPQ_URL = 'amqp://guest:guest@localhost:5672/'

define("port", default=8000, help="run on the given port", type=int)
define("ampq_url", default=AMPQ_URL, help="url for link to RabbitMQ")
 
class WebApplication(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r'/', MainHandler),
            (r'/ws', WebSocketHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
        )
        super(WebApplication, self).__init__(handlers, **settings)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    senders = []
    connection_list = []


    def open(self):
        self.connection_list.append(self)
        self.data_manager.set_command_receiver(self.send_to_websocket)


    def on_message(self, message):
        self.data_manager.send_from_websocket(message)


    def on_close(self):
        self.connection_list.remove(self)
        

    def check_origin(self, origin):
        return True


    def send_to_websocket(self, message):
        if 'ok' in message\
           and 'command' in message['ok']\
           and message['ok']['command'] == 'get_user_list':
            self.write_message(json.dumps(message))
        else:
            for c in self.connection_list:
                c.write_message(json.dumps(message))


class WebPikaClient(BasePikaClient):


    def __init__(self, amqp_url):
        super(WebPikaClient, self).__init__(amqp_url)
        self._senders = []


    def on_channel_open(self, channel):
        super(WebPikaClient, self).on_channel_open(channel)
        self.declare_queue(self.WEBTODATA_QUEUE_NAME)
        self.declare_queue(self.DATATOWEB_QUEUE_NAME, self.set_receive_data)


    def set_receive_data(self, method_frame):
        self.channel.basic_consume(self.on_message, self.DATATOWEB_QUEUE_NAME)


    def on_message(self, channel, method, properties, body):
        self.send_to_websocket(json.loads(body.decode()))
        self.channel.basic_ack(method.delivery_tag)


    def send_from_websocket(self, message):
        self.send('', self.WEBTODATA_QUEUE_NAME, message)


    def send_to_websocket(self, message):
        if hasattr(self, '_command_receiver'):
            self._command_receiver(message)


    def set_command_receiver(self, receiver):
        self._command_receiver = receiver


    def add_sender(self, sender):
        self._senders.append(sender)


def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(WebApplication())
    http_server.listen(options.port)
    mq = WebPikaClient(options.ampq_url)
    mq.connect()
    WebSocketHandler.data_manager = mq
    tornado.ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()

