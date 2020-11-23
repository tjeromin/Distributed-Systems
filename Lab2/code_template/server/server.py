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


# ------------------------------------------------------------------------------------------------------

class Blackboard:

    def __init__(self):
        self.content = dict()
        self.counter = 0
        self.lock = Lock()  # use lock when you modify the content

    def get_content(self):
        with self.lock:
            cnt = self.content
        return cnt

    def add_content(self, new_entry):
        with self.lock:
            self.content[self.counter] = new_entry
            self.counter += 1
        return

    def set_content(self, index, new_content):
        with self.lock:
            self.content[index] = new_content
        return

    def del_content(self, index):
        with self.lock:
            self.content.pop(index)
        return


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.id = int(ID)
        self.ip = str(IP)
        self.rnd_number = random.randint(0, 10 ** 6)
        # dictionary with shape server_ip: (rnd_number, next_ip)
        self.servers_dict = dict.fromkeys(servers_list, (Any, Any))
        # Bottle doesn't allow reassigning an attribute, so this is a workaround by changing the 1st element of the list
        self.leader_ip = ['']
        self.next_ip = ['']
        if self.id < 8:
            self.next_ip[0] = '10.1.0.' + str(self.id + 1)
        else:
            self.next_ip[0] = '10.1.0.1'
        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board', callback=self.post_board)
        self.post('/board/<element_id:int>/', callback=self.post_modify)
        # we give access to the templates elements
        self.get('/templates/<filename:path>', callback=self.get_template)
        self.post('/propagate', callback=self.post_propagate)
        self.post('/leader_election', callback=self.post_leader_election)
        # You can have variables in the URI, here's an example self.post('/board/<element_id:int>/',
        # callback=self.post_board) where post_board takes an argument (integer) called element_id
        time.sleep(2)
        print('id ' + str(self.id))
        if self.id == 1:
            print('sending')
            self.start_leader_election()

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

    def start_leader_election(self):
        # put ip and random number in str separated by "|"
        servers_str = str(self.ip) + '|' + str(self.rnd_number) + '|'
        self.do_parallel_task(self.contact_another_server,
                              args=(self.next_ip[0], '/leader_election', 'POST',
                                    {'action': 'election', 'servers_dict': servers_str, 'initiator_ip': self.ip}))

    def post_leader_election(self):
        action = request.forms.get('action')
        servers_str = request.forms.get('servers_dict')
        init_ip = request.forms.get('initiator_ip')

        if action == 'election':
            print('election')
            if init_ip == self.ip:
                self.do_parallel_task(self.contact_another_server,
                                      args=(self.next_ip[0], '/leader_election', 'POST',
                                            {'action': 'coordination',
                                             'servers_dict': servers_str,
                                             'initiator_ip': init_ip}))
            else:
                servers_str += str(self.ip) + '|' + str(self.rnd_number) + '|'
                self.do_parallel_task(self.contact_another_server,
                                      args=(self.next_ip[0], '/leader_election', 'POST',
                                            {'action': 'election',
                                             'servers_dict': servers_str,
                                             'initiator_ip': init_ip}))
        elif action == 'coordination':
            if servers_str[-1] == '|':
                servers_str = servers_str[:-1]
            print(servers_str)
            servers_list = servers_str.split('|')
            print(servers_list)
            ip_list = servers_list[0::2]
            print(ip_list)
            rnd_list = [int(i) for i in servers_list[1::2]]
            print(rnd_list)
            # make a dictionary of shape server_ip: (rnd_number, next_ip)
            # self.servers_dict = {ip_list[i]: (rnd_list[i], ip_list[(i + 1) % len(ip_list)])
                                 # for i in range(0, len(ip_list))}
            for i in range(0, len(ip_list)):
                self.servers_dict[ip_list[i]] = (rnd_list[i], ip_list[(i + 1) % len(ip_list)])
            # get a list of all indices of rnd_list where rnd_number max is
            max_indices = [i for i, j in enumerate(rnd_list) if j == max(rnd_list)]
            # get a list of IPs where rnd_number max is
            max_ip_list = [ip_list[i] for i in max_indices]
            # leader_ip is the max ip where rnd_number max is
            self.leader_ip[0] = max(max_ip_list)
            self.next_ip[0] = self.servers_dict[self.ip][1]
            print('leader ' + self.leader_ip[0])

            if self.ip != init_ip:
                self.do_parallel_task(self.contact_another_server,
                                      args=(self.next_ip[0], '/leader_election', 'POST',
                                            {'action': 'coordination',
                                             'servers_dict': servers_str,
                                             'initiator_ip': init_ip}))


    def propagate_to_all_servers(self, URI='/propagate', req='POST', params_dict=None):
        for srv_ip in self.servers_dict:
            if srv_ip != self.ip:  # don't propagate to yourself
                success = self.contact_another_server(srv_ip, URI, req, params_dict)
                if not success:
                    print("[WARNING ]Could not contact server {}".format(srv_ip))

    def propagate_to_leader(self, URI, req='POST', params_dict=None):
        success = self.contact_another_server(self.leader_ip[0], URI, req, params_dict)
        if not success:
            print('[WARNING ]Could not contact leader.')
            # initiate election

    # post to ('/propagate')
    def post_propagate(self):
        action = request.forms.get('action')
        # only at leader
        if action == 'submit':
            print("at leader")
            entry = request.forms.get('entry')
            # waiting for all to return when spreading content
            self.propagate_to_all_servers('/propagate', 'POST',
                                          {'action': 'sync_content', 'sync_content': entry})
            self.blackboard.add_content(entry)
        # only at follower
        elif action == 'sync_content':
            print("at follower")
            sync_content = request.forms.get('sync_content')
            self.blackboard.add_content(sync_content)

    # route to ('/')
    def index(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        return template('server/templates/index.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board.items(),
                        members_name_string='Lorenz Meierhofer and Tino Jeromin')

    # get on ('/board')
    def get_board(self):
        # we must transform the blackboard as a dict for compatibility reasons
        board = dict()
        board = self.blackboard.get_content()
        print(self.blackboard.get_content())
        return template('server/templates/blackboard.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board.items())

    # post on ('/board')
    def post_board(self):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            print("Received: {}".format(new_entry))
            self.do_parallel_task(self.propagate_to_leader,
                                  args=('/propagate', 'POST',
                                        {'action': 'submit', 'entry': new_entry}))
        except Exception as e:
            print("[ERROR] " + str(e))

    # post on ('/board/<element_id>/')
    def post_modify(self, element_id):
        try:
            # we read the POST form, and check for an element called 'entry'
            new_entry = request.forms.get('entry')
            delete = request.forms.get('delete')
            if delete == '0':
                self.blackboard.set_content(index=element_id, new_content=new_entry)
            else:
                self.blackboard.del_content(index=element_id)
            print("Received: {}".format(new_entry))
            self.do_parallel_task(self.propagate_to_all_servers,
                                  args=('/propagate', 'POST',
                                        {'delete': delete, 'element_id': element_id, 'entry': new_entry}))
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
        print("[ERROR] " + str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
