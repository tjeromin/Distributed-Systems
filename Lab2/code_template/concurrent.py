import threading
from threading import Lock, Thread
import bottle
from bottle import Bottle, request, template, run, static_file
import requests


class MessageThread(threading.Thread):
    def __init__(self, ip, message):
        threading.Thread.__init__(self)
        self.ip = ip
        self.message = message

    def run(self):
        self.send_message(self.ip, self.message)

    def send_message(self, ip, entry):
        try:
            res = requests.post('http://{}/board'.format(ip), data={'entry': entry})

            # result can be accessed res.json()
            if res.status_code == 200:
                print('success {}'.format(self.ip))
        except Exception as e:
            print("[ERROR] " + str(e))


ip1 = '10.1.0.1'
ip2 = '10.1.0.2'

for i in range(0, 5, 1):
    t1 = MessageThread(ip1, 'server 1 message {}'.format(str(i)))
    t2 = MessageThread(ip2, 'server 2 message {}'.format(str(i)))
    t1.start()
    t2.start()
