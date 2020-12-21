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
SERVER_COUNT = 8


# ------------------------------------------------------------------------------------------------------
class Entry:

    def __init__(self, vector_clock: list, text: str, id: tuple):
        self.vector_clock = vector_clock
        self.text = text
        self.id = id


# ------------------------------------------------------------------------------------------------------
class Blackboard:

    def __init__(self):
        self.content = dict()

        self.clock_list = []
        self.entry_list = []

        self.counter = 0
        self.lock = Lock()  # use lock when you modify the content

    def get_content(self) -> dict:
        with self.lock:
            cnt = dict(zip(self.clock_list, self.entry_list))
        return cnt

    def modify_entry(self, entry: Entry, index: str, ):

        self.del_entry(index)
        self.integrate_entry(entry)
        return

    def del_entry(self, index: str):
        with self.lock:
            self.clock_list.pop(int(index))
            self.entry_list.pop(int(index))
        return

    def add_entry(self, clock: list, new_entry: str):
        with self.lock:
            self.clock_list.append(tuple(clock))
            self.entry_list.append(new_entry)
        return

    def integrate_entry(self, entry: Entry):
        clock = entry.vector_clock
        text = entry.text

        sum_arg = 0
        for element in clock:
            sum_arg += element
        with self.lock:
            # index at which to insert clock and entry
            index = len(self.clock_list)
            for timestamp in reversed(self.clock_list):
                sum = 0
                for element in timestamp:
                    sum += element
                if sum_arg > sum:
                    break
                if sum_arg < sum:
                    # the entry needs to be inserted before the currently checked stamp
                    # (according to the total ordering defined by this function)
                    index -= 1
                    continue
                if sum_arg == sum:
                    for j in range(SERVER_COUNT):
                        if clock[j] == timestamp[j]:
                            continue
                        elif clock[j] > timestamp[j]:
                            index -= 1
                            break
                        elif clock[j] < timestamp[j]:
                            break
                    break

            self.clock_list.insert(index, tuple(clock))
            self.entry_list.insert(index, text)


# ------------------------------------------------------------------------------------------------------
class Message:

    def __init__(self, action, vector_clock, from_id, entry=None, entry_id=None):
        self.action = action
        self.vector_clock = vector_clock
        self.entry = Entry(vector_clock, entry, (from_id, entry_id,))
        self.entry_id = entry_id
        self.to_ip = None
        self.from_id = from_id

    def to_dict(self):
        return {'action': self.action, 'vector_clock': str(self.vector_clock),
                'from_id': self.from_id, 'entry': self.entry.text, 'entry_id': self.entry_id}

    @staticmethod
    def request_to_msg(form: bottle.FormsDict):
        return Message(form.get('action'), json.loads(form.get('vector_clock').replace("'", '"')),
                       int(form.get('from_id')), form.get('entry'), form.get('entry_id'))


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
        # self.out_msg = list()
        # all messages that couldn't be delivered to its receiver
        # self.in_msg = list()
        # start method which tries to send undelivered messages
        # self.do_parallel_task(self.send_msg_from_queue)
        self.vector_clock = [0] * 8
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
                    # msg.ip = srv_ip

    def send_msg_from_queue(self):
        while True:
            time.sleep(3)
            # try to send all messages in queue and delete all which could be delivered
            # self.out_msg[:] = [msg for msg in self.out_msg
            #                    if not self.contact_another_server(
            #         srv_ip=msg.to_ip, URI='/propagate', req='POST', params_dict=msg.to_dict)]

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
        print(msg.action)
        if msg.action == SUBMIT:
            print(str(msg.vector_clock) + ' from ' + str(msg.from_id))
            self.blackboard.integrate_entry(msg.entry)
        elif msg.action == MODIFY:
            print(str(msg.vector_clock) + ' from ' + str(msg.from_id) + ' | modify entry ' + str(msg.entry_id))
            self.blackboard.modify_entry(msg.entry, msg.entry_id)
        elif msg.action == DELETE:
            self.blackboard.del_entry(msg.entry_id)

        self.vector_clock[self.id - 1] += 1
        for svr_id in range(1, SERVER_COUNT):
            if svr_id != self.id:
                self.vector_clock[svr_id - 1] = max(self.vector_clock[svr_id - 1], msg.vector_clock[svr_id - 1])

    # route to ('/')
    def index(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        return template('server/templates/index.tpl',
                        board_title='Server {} ({}) - {}'.format(self.id, self.ip, self.vector_clock),
                        board_dict=board.items(),
                        members_name_string='Lorenz Meierhofer and Tino Jeromin')

    # get on ('/board')
    def get_board(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({}) - {}'.format(self.id, self.ip, self.vector_clock),
                        board_dict=board.items())

    # post on ('/board')
    def post_board(self):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            with self.lock:
                self.vector_clock[self.id - 1] += 1
                msg = Message(SUBMIT, self.vector_clock, self.id, new_entry)
            self.blackboard.add_entry(self.vector_clock, new_entry)

            print("Received: {}".format(new_entry))
            self.do_parallel_task(self.propagate_to_all_servers, args=('/propagate', 'POST', msg,))

        except Exception as e:
            print("[ERROR] " + str(e))

    # post on ('/board/<element_id>/')
    def post_modify(self, element_id):
        print('modify')
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            delete = request.forms.get('delete')

            with self.lock:
                self.vector_clock[self.id - 1] += 1

                if delete == '1':
                    msg = Message(DELETE, self.vector_clock, self.id, entry=new_entry, entry_id=element_id)
                    self.blackboard.del_entry(element_id)
                else:
                    msg = Message(MODIFY, self.vector_clock, self.id, entry=new_entry, entry_id=element_id)
                    self.blackboard.modify_entry(msg.entry, element_id)

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
