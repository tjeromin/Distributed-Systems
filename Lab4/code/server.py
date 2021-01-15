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


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        """Distributed blackboard server using vector clocks and an ordered queue for writes."""
        super(Server, self).__init__()
        self.servers_list = servers_list
        self.id = int(ID)
        self.ip = str(IP)

        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.index)
        self.get('/vote/result', callback=self.get_result)
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

    def propagate_to_all_servers(self, URI='/propagate', req='POST', params_dict=None):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip:  # don't propagate to yourself
                success = self.contact_another_server(srv_ip, URI, req, params_dict)
                if not success:
                    print("[WARNING ]Could not contact server {}".format(srv_ip))

    # route to ('/')
    def index(self):
        return static_file(filename='vote_frontpage_template.html', root='./lab4-html')

    # get on ('/vote/result')
    def get_result(self):
        return static_file(filename='vote_result_template.html', root='./lab4-html')


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
