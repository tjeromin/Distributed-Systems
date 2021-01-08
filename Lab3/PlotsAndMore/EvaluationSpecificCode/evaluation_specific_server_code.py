        # coding=utf-8
import argparse
import copy
import json
import sys
from threading import Lock, Thread, RLock
import time
import traceback
from typing import Any

import bottle
from bottle import Bottle, request, template, run, static_file
import requests

SUBMIT = 'submit'
MODIFY = 'modify'
DELETE = 'delete'
SERVER_COUNT = 8


# ------------------------------------------------------------------------------------------------------
class Entry:

    def __init__(self, vector_clock: list, text: str, action: str):
        self.vector_clock = vector_clock
        self.text = text
        self.action = action
        self.log = list()


# ------------------------------------------------------------------------------------------------------
class Blackboard:

    def __init__(self):
        # list of type Entry
        self.entries = list()
        # list of vector_clocks
        self.deleted = list()
        # list of type tuple of (Entry, vector_clock)
        self.to_be_applied = list()
        self.counter = 0
        # RLock, because it can be acquired multiple times by the same thread
        self.lock = RLock()  # use lock when you modify the content

    def get_content(self) -> dict:
        with self.lock:
            text_list = [e.text for e in self.entries]
            clock_list = [tuple(e.vector_clock) for e in self.entries]
            cnt = dict(zip(clock_list, text_list))
        return cnt

    def get_index(self, entry_clock: list) -> int:
        for i in range(0, len(self.entries)):
            if self.entries[i].vector_clock == entry_clock:
                return i
        return -1

    def search_logs(self, entry_clock: list) -> int:
        for i in range(0, len(self.entries)):
            for v in self.entries[i].log:
                if entry_clock == v:
                    return i
        return -1

    def modify_entry(self, entry: Entry, entry_clock: list, from_apply=False) -> bool:
        success = False

        with self.lock:
            index = self.get_index(entry_clock)

            # entry clock is a current vector clock of an entry
            if index >= 0:
                print('To be modified vector clock {} is a current vector clock of an entry.'.format(entry_clock))
                entry.log = self.entries[index].log
                entry.log.append(self.entries[index].vector_clock)
                self.entries.pop(index)
                self.integrate_entry(entry)
                print(entry.log)
                success = True
            # entry clock is in the log of an entry
            elif self.search_logs(entry_clock) >= 0:
                print('To be modified vector clock {} is in the log of an entry.'.format(entry_clock))
                index = self.search_logs(entry_clock)

                new_entry_clock = entry.vector_clock
                new_entry_sum = 0
                for element in new_entry_clock:
                    new_entry_sum += element

                current_clock = self.entries[index].vector_clock
                current_entry_sum = 0
                for element in current_clock:
                    current_entry_sum += element

                print('new: {} | old: {}'.format(new_entry_sum, current_entry_sum))

                apply_new_entry = False

                if new_entry_sum > current_entry_sum:
                    apply_new_entry = True
                elif new_entry_sum < current_entry_sum:
                    apply_new_entry = False
                else:
                    for j in range(SERVER_COUNT):
                        if new_entry_clock[j] == current_clock[j]:
                            continue
                        elif new_entry_clock[j] > current_clock[j]:
                            apply_new_entry = True
                            break
                        elif new_entry_clock[j] < current_clock[j]:
                            apply_new_entry = False
                            break
                success = True
                print('apply new {}'.format(apply_new_entry))
                if apply_new_entry:
                    entry.log = self.entries[index].log
                    entry.log.append(self.entries[index].vector_clock)
                    self.entries.pop(index)
                    self.integrate_entry(entry)
                else:
                    self.entries[index].log.append(entry_clock)
            # entry clock belongs to an entry which was deleted
            elif entry_clock in self.deleted:
                print('To be modified vector clock {} is a vector clock of an deleted entry.'.format(entry_clock))
                self.deleted.append(entry_clock)
                success = True
            # entry clock is neither the current vector clock or in the log of an entry
            elif not from_apply:
                print('To be modified vector clock {} couldn\'t be found.'.format(entry_clock))
                self.to_be_applied.append((entry, entry_clock,))
        return success

    def del_entry(self, entry: Entry, entry_clock: list, from_apply=False):
        success = True

        with self.lock:
            index = self.get_index(entry_clock)
            if index < 0:
                index = self.search_logs(entry_clock)
                if index < 0:
                    success = False
                    if not from_apply:
                        self.to_be_applied.append((entry, entry_clock))

            if success:
                self.deleted.append(self.entries[index].vector_clock)
                self.deleted += self.entries[index].log
                self.entries.pop(index)
        return success

    def apply_entries_from_queue(self):
        with self.lock:
            apply_list = self.to_be_applied
            self.to_be_applied = list()
            not_applied = list()
            for elem in apply_list:
                entry = elem[0]
                entry_clock = elem[1]

                success = False
                if entry.action == MODIFY:
                    success = self.modify_entry(entry, entry_clock, from_apply=True)
                else:
                    success = self.del_entry(entry, entry_clock, from_apply=True)

                if not success:
                    not_applied.append(elem)

            self.to_be_applied = not_applied

    def add_entry(self, new_entry: Entry):
        with self.lock:
            self.entries.append(new_entry)
        return

    def integrate_entry(self, entry: Entry):
        clock = entry.vector_clock

        sum_arg = 0
        for element in clock:
            sum_arg += element
        with self.lock:
            # index at which to insert clock and entry
            index = len(self.entries)
            for timestamp in reversed([e.vector_clock for e in self.entries]):
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

            self.entries.insert(index, entry)

        if len(self.to_be_applied) > 0:
            self.apply_entries_from_queue()


# ------------------------------------------------------------------------------------------------------
class Message:

    def __init__(self, action: str, vector_clock: list, from_id: int, entry=None, entry_clock=None):
        if entry_clock is None:
            entry_clock = []
        vector_clock = vector_clock.copy()
        entry_clock = entry_clock.copy()
        self.action = action
        self.vector_clock = vector_clock
        self.entry = Entry(vector_clock, entry, action)
        self.entry_clock = entry_clock
        self.to_ip = None
        self.from_id = from_id

    def to_dict(self):
        return {'action': self.action, 'vector_clock': str(self.vector_clock),
                'from_id': self.from_id, 'entry': self.entry.text, 'entry_clock': str(self.entry_clock)}

    @staticmethod
    def request_to_msg(form: bottle.FormsDict):
        return Message(form.get('action'), json.loads(form.get('vector_clock').replace("'", '"')),
                       int(form.get('from_id')), form.get('entry'),
                       json.loads(form.get('entry_clock').replace("'", '"')))


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        """Distributed blackboard server using vector clocks and an ordered queue for writes."""
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.servers_list = servers_list
        self.id = int(ID)
        self.ip = str(IP)

        self.clock_lock = Lock()
        self.vector_clocks = {ip: 0 for ip in servers_list}
        # all messages that couldn't be delivered to its receiver
        self.out_queue = list()
        self.queue_lock = Lock()
        self.do_parallel_task(self.send_msg_from_queue)
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

    @staticmethod
    def do_parallel_task(method, args=()):
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

    @staticmethod
    def _wrapper_delay_and_execute(delay, method, args):
        time.sleep(delay)  # in sec
        method(*args)

    @staticmethod
    def contact_another_server(srv_ip, URI, req='POST', params_dict=None):
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

    def propagate_to_all_servers(self, URI='/propagate', req='POST', msg=None):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip:  # don't propagate to yourself
                msg.to_ip = srv_ip
                success = self.contact_another_server(srv_ip, URI, req, msg.to_dict())
                if not success:
                    print("[WARNING ]Could not contact server {}".format(srv_ip))
                    with self.queue_lock:
                        self.out_queue.append(copy.copy(msg))

    def send_msg_from_queue(self):
        while True:
            time.sleep(1)
            n = len(self.out_queue)
            if n > 0:
                # try to send all messages in queue and delete all which could be delivered
                with self.queue_lock:
                    print('Trying to send {} messages that are currently in the queue...'.format(len(self.out_queue)))
                    self.out_queue[:] = [msg for msg in self.out_queue
                                         if not self.contact_another_server(
                            srv_ip=msg.to_ip, URI='/propagate', req='POST', params_dict=msg.to_dict())]
                print('Sent {} messages from the queue.'.format(n - len(self.out_queue)))

    # post to ('/propagate')
    def post_propagate(self):
        msg = Message.request_to_msg(request.forms)
        print(str(msg.vector_clock) + ' from ' + str(msg.from_id) + ' (' + msg.action + ')')

        if msg.action == SUBMIT:
            self.blackboard.integrate_entry(msg.entry)
        elif msg.action == MODIFY:
            self.blackboard.modify_entry(msg.entry, msg.entry_clock)
        elif msg.action == DELETE:
            self.blackboard.del_entry(msg.entry, msg.entry_clock)

        with self.clock_lock:
            self.vector_clock[self.id - 1] += 1
            for svr_id in range(1, SERVER_COUNT + 1):
                if svr_id != self.id:
                    self.vector_clock[svr_id - 1] = max(self.vector_clock[svr_id - 1], msg.vector_clock[svr_id - 1])

        print("h " + str(len(self.blackboard.entries)))
        if len(self.blackboard.entries) == 16:
            f = open("server/time.txt", "a")
            f.write("stop at server " + str(self.id) + ": " + str(time.time()) + "\n")
            f.close()

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
            with self.clock_lock:
                self.vector_clock[self.id - 1] += 1
                msg = Message(SUBMIT, self.vector_clock, self.id, new_entry)
            self.blackboard.add_entry(msg.entry)

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
            with self.blackboard.lock:
                entry_clock = self.blackboard.entries[element_id].vector_clock

            print('modify/delete entry with clock ' + str(entry_clock))
            with self.clock_lock:
                self.vector_clock[self.id - 1] += 1

                if delete == '1':
                    msg = Message(DELETE, self.vector_clock, self.id, entry=new_entry, entry_clock=entry_clock)
                    self.blackboard.del_entry(msg.entry, entry_clock)
                else:
                    msg = Message(MODIFY, self.vector_clock, self.id, entry=new_entry, entry_clock=entry_clock)
                    self.blackboard.modify_entry(msg.entry, entry_clock)

            print("Received: {}".format(new_entry))
            self.do_parallel_task(self.propagate_to_all_servers,
                                  args=('/propagate', 'POST', msg))
        except Exception as e:
            print("[ERROR] " + str(e))

    @staticmethod
    def get_template(filename):
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
