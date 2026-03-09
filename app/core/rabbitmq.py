import pika
import os
import json
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()


class Rabbitmq():

    def __init__(self, callback=None):
        self.__host = os.getenv("HOST_RABBITMQ")
        self.__port = int(os.getenv("PORT_RABBITMQ"))
        self.__vhost = os.getenv("VHOST")
        self.__username = os.getenv("USER")
        self.__password = os.getenv("PASSWORD")
        self.__queue_received_push = os.getenv("QUEUE_RECEIVED_EVENT_PUSH")
        self.__queue_return_status_push = os.getenv("QUEUE_RETURN_EVENT_STATUS_PUSH")
        self.__callback = callback
        self.__channel = self.__create_channel()

    def __create_channel(self):
        # Conecta ao servidor local
        connection_parameters = pika.ConnectionParameters(
            host=self.__host,
            port=self.__port,
            virtual_host=self.__vhost,
            credentials=pika.PlainCredentials(
                username=self.__username,
                password=self.__password
            )
        )
        channel = pika.BlockingConnection(connection_parameters).channel()

        return channel

    def consumer(self, queue, callback=None):
        # Declarar uma Fila (queue_declare)
        self.__channel.queue_declare(
            queue=queue,
            durable=True
        )
        # O parâmetro durable=True garante que a fila sobreviva caso o RabbitMQ seja reiniciado.

        self.__channel.basic_consume(
            queue=queue,
            on_message_callback=self.__callback if self.__callback else callback,
            auto_ack=True
        )

    def publisher(self, body, routing_key):
        self.__channel.basic_publish(
            exchange=os.getenv('EXCHANGE'),
            routing_key=routing_key,
            body=json.dumps(body),
            properties=pika.BasicProperties(
                delivery_mode=2 # Mensagem persistente
            )
        )

    def start(self):
        print('- (Status): Aguardando evento na fila "Received Push".')
        self.__channel.start_consuming()