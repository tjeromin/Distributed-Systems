# coding=utf-8
import argparse
import json
import sys
from threading import Lock, Thread
import time
import bottle
from bottle import Bottle, request, template, run, static_file
import requests

# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        super(Server, self).__init__()
        self.id = int(ID)
        self.ip = str(IP)
        self.servers_list = servers_list
        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.home)
        self.get('/vote/result', callback=self.get_vote)
        self.post('/vote/attack', callback=self.post_attack)
        self.post('/vote/retreat', callback=self.post_retreat)
        self.post('/vote/byzantine', callback=self.post_byzantine)
        # we give access to the templates elements
        self.get('/templates/<filename:path>', callback=self.get_template)
        # You can have variables in the URI, here's an example
        # self.post('/board/<element_id:int>/', callback=self.post_board) where post_board takes an argument (integer) called element_id

    def do_parallel_task(self, method, args=None):
        # create a thread running a new task
        # Usage example: self.do_parallel_task(self.contact_another_server, args=("10.1.0.2", "/index", "POST", params_dict))
        # this would start a thread sending a post request to server 10.1.0.2 with URI /index and with params params_dict
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
        # Try to contact another serverthrough a POST or GET
        # usage: server.contact_another_server("10.1.1.1", "/index", "POST", params_dict)
        success = False
        try:
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

    def propagate_to_all_servers(self, URI, req='POST', params_dict=None):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip:  # don't propagate to yourself
                success = self.contact_another_server(srv_ip, URI, req, params_dict)
                if not success:
                    print("[WARNING ]Could not contact server {}".format(srv_ip))

    # route to ('/')
    def home(self):
        # we must transform the blackboard as a dict for compatiobility reasons
        return template('server/templates/vote_frontpage_template.html',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        members_name_string='INPUT YOUR NAME HERE')

    # get on ('/board')
    def get_vote(self):
        return template('server/templates/vote_frontpage_template.html')


    def post_attack(self):
        print("attack!!!!!!!!!!!!!!!!!!!!!!!!!")

    def post_retreat(self):
        print("retreat!!!!!!!!!!!!!!!!!!!!!!!!!")

    def post_byzantine(self):
        print("byzantine!!!!!!!!!!!!!!!!!!!!!!!!!")

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
