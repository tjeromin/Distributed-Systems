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
class Blackboard:

    def __init__(self):
        self.content = dict()

        self.clock_list = []
        self.entry_list = []

        self.counter = 0
        self.lock = Lock()  # use lock when you modify the content

    def get_content(self) -> dict:
        with self.lock:
            zip_iterator = zip(keys_list, values_list)
            cnt = dict(zip(self.clock_list, self.entry_list))
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

    def add_entry(self, clock, new_entry):
        with self.lock:
            self.clock_list.append(tuple(clock))
            self.entry_list.append(new_entry)
        return

    def integrate_entry(self, clock, new_entry):
        sum_arg = 0
        for element in clock:
            sum_arg += element
        with self.lock:
            index = len(self.clock_list)
            for timestamp in self.clock_list:
                sum = 0
                for element in timestamp:
                    sum += element
                if sum_arg > sum:
                    break
                if sum_arg < sum:
                    # the entry needs to be inserted before the currently checked stamp (according to the total ordering defined by this function)
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

            self.clock_list.insert(index, clock)
            self.entry_list.insert(index, new_entry)

# ------------------------------------------------------------------------------------------------------
class Message:

    def __init__(self, action, vector_clocks, entry=None):
        super.__init__()
        self.action = action
        self.vector_clocks = vector_clocks
        self.entry = entry

    def to_dict(self):
        return {'action': self.action, 'vector_clocks': self.vector_clocks, 'entry': self.entry}

    @staticmethod
    def request_to_msg(req: bottle.BaseRequest):
        form = req.forms
        return Message(form.get('action'), json.loads(form.get('vector_clock')), form.get('entry'))


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        """Distributed blackboard server using vector clocks and an ordered queue for writes."""
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.id = int(ID)
        self.ip = str(IP)
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

    def do_parallel_task(self, method, args=None):
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

    def propagate_to_all_servers(self, URI='/propagate', req='POST', params_dict=None):
        for srv_ip in self.svrs_dict:
            if srv_ip != self.ip:  # don't propagate to yourself
                success = self.contact_another_server(srv_ip, URI, req, params_dict)
                if not success:
                    print("[WARNING ]Could not contact server {}".format(srv_ip))

    # post to ('/propagate')
    def post_propagate(self):
        ###############################################################
        ###############################################################
        # GET CLOCK AND ENTRY FROM POST
        action = request.forms.get('action')
        element_id = request.forms.get('element_id')

        if action == 'submit':
            entry = request.forms.get('entry')
            self.blackboard.set_content(element_id, entry)
        elif action == 'modify':
            entry = request.forms.get('entry')
            self.blackboard.set_content(element_id, entry)
        elif action == 'delete':
            self.blackboard.del_content(element_id)

    # route to ('/')
    def index(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        role = 'leader' if self.svrs_dict.leader_ip == self.ip else 'follower'
        return template('server/templates/index.tpl',
                        board_title='Server {} ({}) - #: {} - {}'.format(self.id, self.ip,
                                                                         self.rnd_number, role),
                        board_dict=board.items(),
                        members_name_string='Lorenz Meierhofer and Tino Jeromin')

    # get on ('/board')
    def get_board(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        role = 'leader' if self.svrs_dict.leader_ip == self.ip else 'follower'
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({}) - #: {} - {}'.format(self.id, self.ip,
                                                                         self.rnd_number, role),
                        board_dict=board.items())

    # post on ('/board')
    def post_board(self):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            self.vector_clock [self.ID] += 1
            self.do_parallel_task(self.propagate_to_leader,
                                  args=('/propagate_leader', 'POST',
                                        {'action': 'submit', 'entry': new_entry, 'clock': self.vector_clock}))
        except Exception as e:
            print("[ERROR] " + str(e))

    # post on ('/board/<element_id>/')
    def post_modify(self, element_id):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            delete = request.forms.get('delete')

            if delete == '1':
                action = 'delete'
            else:
                action = 'modify'
            print("Received: {}".format(new_entry))
            self.do_parallel_task(self.propagate_to_leader,
                                  args=('/propagate_leader', 'POST',
                                        {'action': action, 'element_id': element_id, 'entry': new_entry}))
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
        server.do_parallel_task_after_delay(delay=2, method=server.start_leader_election, args=[])
        bottle.run(server,
                   host=server_ip,
                   port=PORT)
    except Exception as e:
        raise Exception(str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
