# coding=utf-8
import argparse
import json
import sys
from threading import Lock, Thread
import time
import traceback
import bottle
from bottle import Bottle, request, template, run, static_file
import requests
# ------------------------------------------------------------------------------------------------------

class Blackboard():

    def __init__(self):
        self.content = dict()
        self.counter = 0;
        self.lock = Lock() # use lock when you modify the content


    def get_content(self):
        with self.lock:
            cnt = self.content
        return cnt

    # add entry to blackboard dict
    def add_content(self, new_content):
        with self.lock:
            self.content [self.counter] = new_content
            self.counter += 1
        return
    
    # modify entry
    def modify_content(self, element_id, mod_entry):
        with self.lock:
            self.content [element_id] = mod_entry
        return
    
    # delete entry
    def delete_entry(self, element_id):
        with self.lock:
            self.content.pop(element_id)
        return
        


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        super(Server, self).__init__()
        self.blackboard = Blackboard()
        self.id = int(ID)
        self.ip = str(IP)
        self.servers_list = servers_list
        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.index)
        self.get('/board', callback=self.get_board)
        self.post('/board', callback=self.post_board)
        # we give access to the templates elements
        self.get('/templates/<filename:path>', callback=self.get_template)
        self.post('/board/<element_id:int>/', callback=self.delete)
        self.post('/propagate', callback=self.post_propagate)
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
        time.sleep(delay) # in sec
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
            print("[ERROR] "+str(e))
        return success


    def propagate_to_all_servers(self, URI, req='POST', params_dict=None):
        for srv_ip in self.servers_list:
            if srv_ip != self.ip: # don't propagate to yourself
                success = self.contact_another_server(srv_ip, URI, req, params_dict)
                if not success:
                    print("[WARNING ]Could not contact server {}".format(srv_ip))
                    
    # post to ('/propagate')
    def post_propagate(self):
        action = request.forms.get('action')
        
        if action == 'submit':
            entry = request.forms.get('entry')
            self.blackboard.add_content(entry)
        elif action == 'delete':
            element_id = request.forms.get('element_id')
            print("delete request receieved: " + (element_id))
            self.blackboard.get_content().pop(int(element_id))
        elif action == 'modify':
            element_id = request.forms.get('element_id')
            mod_entry = request.forms.get('mod_entry')
            self.blackboard.get_content() [int(element_id)] = mod_entry


    # route to ('/')
    def index(self):
        board = dict()
        board = self.blackboard.get_content()
        return template('server/templates/index.tpl',
                        board_title='Server {} ({})'.format(self.id,
                                                            self.ip),
                        board_dict=board.items(),
                        members_name_string='INPUT YOUR NAME HERE')

    # get on ('/board')
    def get_board(self):
        board = dict()
        board = self.blackboard.get_content()
        print(board.items())
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
            # bottle.TEMPLATES.clear()
            self.blackboard.add_content(new_entry)
            
            self.do_parallel_task(self.propagate_to_all_servers,
                                  args=('/propagate', 'POST',
                                        {'action': 'submit', 'entry': new_entry}))
            
        except Exception as e:
            print("[ERROR] "+str(e))
        # self.get_board()
        
    def delete(self, element_id):
        d = request.forms.get('delete')
        if d== "1":
            self.blackboard.delete_entry(element_id)
            self.do_parallel_task(self.propagate_to_all_servers,
                                  args=('/propagate', 'POST',
                                        {'action': 'delete', 'element_id': element_id}))
        else:
            mod_entry = request.forms.get('entry')
            self.blackboard.modify_content(element_id, mod_entry)
            self.do_parallel_task(self.propagate_to_all_servers,
                                  args=('/propagate', 'POST',
                                        {'action': 'modify','element_id': element_id, 'mod_entry': mod_entry}))


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
        print("[ERROR] "+str(e))


# ------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
