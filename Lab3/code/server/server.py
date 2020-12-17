# coding=utf-8
import argparse
import json
import sys
from threading import Lock, Thread
import time
import traceback
from typing import Any

import bottle
from bottle import Bottle, request, template, run, static_file
import requests
import random
import collections

SUBMIT = 'submit'
MODIFY = 'modify'
DELETE = 'delete'


# ------------------------------------------------------------------------------------------------------
class Blackboard:

    def __init__(self):
        self.content = dict()
        self.counter = 0
        self.lock = Lock()  # use lock when you modify the content

    def get_content(self) -> dict:
        with self.lock:
            cnt = self.content
        return cnt

    def add_content(self, new_entry: str) -> str:
        with self.lock:
            self.content[self.counter] = new_entry
            element_id = str(self.counter)
            self.counter += 1
        return element_id

    def set_content(self, index: str, new_content: str):
        with self.lock:
            self.content[int(index)] = new_content
            self.counter = len(self.content)
            # ordering the dict
            self.content = collections.OrderedDict(sorted(self.content.items()))
        return

    def del_content(self, index: str):
        with self.lock:
            self.content.pop(int(index))
            self.counter = len(self.content)
        return


# ------------------------------------------------------------------------------------------------------
class Message:

    def __init__(self, action, vector_clocks, from_ip, entry=None, entry_id=None):
        self.action = action
        self.vector_clocks = vector_clocks
        self.entry = entry
        self.entry_id = entry_id
        self.to_ip = None
        self.from_ip = from_ip

    def to_dict(self):
        return {'action': self.action, 'vector_clocks': str(self.vector_clocks),
                'from_ip': self.from_ip, 'entry': self.entry, 'entry_id': self.entry_id}

    @staticmethod
    def request_to_msg(form: bottle.FormsDict):
        return Message(form.get('action'), json.loads(form.get('vector_clocks').replace("'", '"')),
                       form.get('from_ip'), form.get('entry'), form.get('entry_id'))


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        """Distributed blackboard server using vector clocks and an ordered queue for writes."""
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.servers_list = servers_list
        self.lock = Lock()
        self.id = int(ID)
        self.ip = str(IP)
        self.vector_clocks = {ip: 0 for ip in servers_list}
        self.out_msg = list()
        # all messages that couldn't be delivered to its receiver
        self.in_msg = list()
        # start method which tries to send undelivered messages
        self.do_parallel_task(self.send_msg_from_queue)
        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board', callback=self.post_board)
        self.post('/board/<element_id:int>/', callback=self.post_modify)
        # we give access to the templates elements
        self.get('/templates/<filename:path>', callback=self.get_template)
        # leader propagates new entries to all followers
        self.post('/propagate', callback=self.post_propagate)
        # You can have variables in the URI, here's an example self.post('/board/<element_id:int>/',
        # callback=self.post_board) where post_board takes an argument (integer) called element_id

    def do_parallel_task(self, method, args=()):
        # create a thread running a new task Usage example: self.do_parallel_task(self.contact_another_server,
        # args=("10.1.0.2", "/index", "POST", params_dict)) this would start a thread sending a post request to
        # server 10.1.0.2 with URI /index and with params params_dict
        thread = Thread(target=method,
                        args=args)
        thread.daemon = True
        thread.start()

    def do_parallel_task_after_delay(self, delay, method, args=None):
        # create a thread, and run a task after a specified delay
        # Usage example: self.do_parallel_task_after_delay(10, self.start_election, args=(,))
        # this would start a thread starting an election after 10 seconds
        thread = Thread(target=self._wrapper_delay_and_execute,
                        args=(delay, method, args))
        thread.daemon = True
        thread.start()

    def _wrapper_delay_and_execute(self, delay, method, args):
        time.sleep(delay)  # in sec
        method(*args)

    def contact_another_server(self, srv_ip, URI, req='POST', params_dict=None):
        # Try to contact another server through a POST or GET
        # usage: server.contact_another_server("10.1.1.1", "/index", "POST", params_dict)
        success = False
        try:
            res = 0
            if 'POST' in req:
                res = requests.post('http://{}{}'.format(srv_ip, URI),
                                    data=params_dict)
            elif 'GET' in req:
                res = requests.get('http://{}{}'.format(srv_ip, URI))
            # result can be accessed res.json()
            if res.status_code == 200:
                success = True
        except Exception as e:
            print("[ERROR] " + str(e))
        return success

    def propagate_to_all_servers(self, URI='/propagate', req='POST', msg=Message):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip:  # don't propagate to yourself
                success = self.contact_another_server(srv_ip, URI, req, msg.to_dict())
                if not success:
                    print("[WARNING ]Could not contact server {}".format(srv_ip))
                    msg.ip = srv_ip
                    self.out_msg.append(msg)

    def send_msg_from_queue(self):
        while True:
            time.sleep(3)
            # try to send all messages in queue and delete all which could be delivered
            self.out_msg[:] = [msg for msg in self.out_msg
                               if not self.contact_another_server(
                                srv_ip=msg.to_ip, URI='/propagate', req='POST', params_dict=msg.to_dict)]

    def process_msg(self, msg: Message):
        # TODO: implement queue
        deliverable = True

        if not deliverable:
            self.out_msg.append(msg)
        else:
            # apply msg
            pass

    # post to ('/propagate')
    def post_propagate(self):
        msg = Message.request_to_msg(request.forms)
        # print("received " + str(msg.to_dict()))
        # print(msg.vector_clocks)

        if msg.action == SUBMIT:
            self.blackboard.add_content(msg.entry)
        elif msg.action == MODIFY:
            self.blackboard.set_content(msg.entry_id, msg.entry)
        elif msg.action == DELETE:
            self.blackboard.del_content(msg.entry_id)

    # route to ('/')
    def index(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        return template('server/templates/index.tpl',
                        board_title='Server {} ({})'.format(self.id, self.ip),
                        board_dict=board.items(),
                        members_name_string='Lorenz Meierhofer and Tino Jeromin')

    # get on ('/board')
    def get_board(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({})'.format(self.id, self.ip),
                        board_dict=board.items())

    # post on ('/board')
    def post_board(self):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            with self.lock:
                self.vector_clocks[self.ip] += 1
                msg = Message(SUBMIT, self.vector_clocks, self.ip, new_entry)
            self.blackboard.add_content(msg.entry)

            print("Received: {}".format(new_entry))
            self.do_parallel_task(self.propagate_to_all_servers, args=('/propagate', 'POST', msg,))
        except Exception as e:
            print("[ERROR] " + str(e))

    # post on ('/board/<element_id>/')
    def post_modify(self, element_id):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            delete = request.forms.get('delete')

            if delete == '1':
                action = DELETE
                self.blackboard.del_content(element_id)
            else:
                action = MODIFY
                self.blackboard.set_content(element_id, new_entry)
            msg = Message(action, self.vector_clocks, self.ip, entry=new_entry, entry_id=element_id)
            with self.lock:
                self.vector_clocks[self.ip] += 1
            print("Received: {}".format(new_entry))
            self.do_parallel_task(self.propagate_to_all_servers,
                                  args=('/propagate', 'POST', msg))
        except Exception as e:
            print("[ERROR] " + str(e))

    def get_template(self, filename):
        return static_file(filename, root='./server/templates/')


# ------------------------------------------------------------------------------------------------------
def main():
    PORT = 80
    parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
    parser.add_argument('--id',
                        nargs='?',
                        dest='id',
                        default=1,
                        type=int,
                        help='This server ID')
    parser.add_argument('--servers',
                        nargs='?',
                        dest='srv_list',
                        default="10.1.0.1,10.1.0.2",
                        help='List of all servers present in the network')
    args = parser.parse_args()
    server_id = args.id
    server_ip = "10.1.0.{}".format(server_id)
    servers_list = args.srv_list.split(",")

    try:
        server = Server(server_id,
                        server_ip,
                        servers_list)
        bottle.run(server,
                   host=server_ip,
                   port=PORT)
    except Exception as e:
        raise Exception(str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
