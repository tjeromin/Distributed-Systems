# coding=utf-8
import argparse
import byzantine_behavior
from threading import Lock, Thread
import time
import bottle
from bottle import Bottle, request, template, run, static_file
import requests

# constants for a given experiment
no_loyal = 3
no_total = 4
on_tie = True
k = 1


# ------------------------------------------------------------------------------------------------------
class Server(Bottle):

    def __init__(self, ID, IP, servers_list):
        super(Server, self).__init__()
        print("serverslist")
        print(servers_list)
        self.id = int(ID)
        self.ip = str(IP)
        self.servers_list = servers_list

        self.vote_counter = 0
        self.vote_vector = [False] * (no_total - 1)

        self.index_list = []
        self.vector_list = []

        # identity of node, determined by pressed button (in respective post method)
        self.legitimate = True

        self.result_string = ""
        # list all REST URIs
        # if you add new URIs to the server, you need to add them here
        self.route('/', callback=self.home)
        self.get('/vote/result', callback=self.get_vote)
        self.post('/vote/attack', callback=self.post_attack)
        self.post('/vote/retreat', callback=self.post_retreat)
        self.post('/vote/byzantine', callback=self.post_byzantine)
        self.post('/propagate/round1', callback=self.post_propagate1)
        self.post('/propagate/round2', callback=self.post_propagate2)

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

    # get on ('/vote/result')
    def get_vote(self):
        return template('server/templates/vote_result_template.tpl', s=self.result_string)

    # post to ('/propagate/round1')
    def post_propagate1(self):
        self.vote_counter += 1
        vote = request.forms.get('vote')
        from_id = request.forms.get('id')

        print("vote: " + vote)
        print("from_id: " + str(from_id))

        self.vote_vector[from_id - 1] = vote
        print("vector: " + self.vote_vector)
        # wait until all votes arrive before sending out the vectors
        if self.vote_counter == (no_total - 1) and self.legitimate:
            self.do_parallel_task(self.propagate_to_all_servers,
                                  args=('/propagate/round2', 'POST',
                                        {'vote_vector': self.vote_vector, 'id': self.id}))

    # post to ('/propagate/round2')
    def post_propagate2(self):
        vector = request.forms.get('vote_vector')
        from_id = request.forms.get('id')

        # need index_list to reference the vote that needs to be canceled in a row (because the
        # vector_list (a list of lists) could be unordered, so we can't use the index of that list)
        self.index_list.append(from_id - 1)
        self.vector_list.append(vector)
        if len(self.vector_list) == (no_total - 1):
            # append own vote vector, table complete
            self.vector_list.append(self.vote_vector)
            self.index_list.append(self.id - 1)

            # the actual, filtered, correct and consistent vector, whose vote majority makes the final decision
            result_vector = []

            # filtering for the original vote from each node
            for i in range(no_total):
                attack_vote_counter = 0
                for j in range(no_total):
                    if vector_list[j][i]:
                        # ignore the diagonal by canceling the value at the referenced index
                        if index_list[j] == i:
                            continue
                        attack_vote_counter += 1
                result_vector.append(attack_vote_counter >= (no_loyal - k))

            # calculating majority in result vector
            attack_vote_counter = 0
            for b in result_vector:
                if b:
                    attack_vote_counter += 1

            # final result based on the tying value (on_tie)
            if(on_tie):
                result = attack_vote_counter >= (no_total + 1) / 2
            else:
                result = attack_vote_counter > (no_total + 1) / 2

            # string to be displayed on screen
            self.result_string = "result vector: " + result_vector + "\nresult: " + result


    # makes a node an honest general
    def post_attack(self):
        vote = True
        self.vote_vector[self.id - 1] = vote
        self.do_parallel_task(self.propagate_to_all_servers,
                              args=('/propagate/round1', 'POST',
                                    {'vote': vote, 'id': self.id}))

    # makes a node an honest general
    def post_retreat(self):
        vote = False
        self.vote_vector[self.id - 1] = vote
        self.do_parallel_task(self.propagate_to_all_servers,
                              args=('/propagate/round1', 'POST',
                                    {'vote': vote, 'id': self.id}))

    # makes a node a byzantine general
    def post_byzantine(self):
        self.legitimate = False
        # byzantine node has to wait until it has gotten all votes to successfully manipulate
        while len(self.vote_vector) < (no_total - 1):
            time.sleep(1)

        #computing and sending the byzantine votes
        vote_list = byzantine_behavior.compute_byzantine_vote_round1(no_loyal, no_total, on_tie)
        for server_no in range(no_loyal):
            self.do_parallel_task(self.contact_another_server,
                                  args=(self.servers_list[server_no],
                                        '/propagate/round1', 'POST',
                                        {'vote': vote_list[server_no]}))

        #computing and sending the byzantine vectors
        vector_list = byzantine_behavior.compute_byzantine_vote_round2(no_loyal, no_total, on_tie)
        for server_no in range(no_loyal):
            self.do_parallel_task(self.contact_another_server,
                                  args=(self.servers_list[server_no],
                                        '/propagate/round2', 'POST',
                                        {'vote_vector': vector_list[server_no], 'id': self.id}))

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
