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


def post(server_id, msg_id):
    res = requests.post('http://10.1.0.{}{}'.format(server_id, '/board'),
                        {'entry': "hello from script (msg_id: " + str(msg_id) + ") at server " + str(server_id)})


def do_parallel_task(method, args=None):
    thread = Thread(target=method,
                    args=args)
    thread.daemon = False
    thread.start()


def post_from_all_servers(n):
    for msg in range(n):
        for server in range(4):
            do_parallel_task(post, args=(server + 1, msg + 1))

f = open("server/time.txt", "a")
f.write("start" + str(time.time()) + "\n")
f.close()

post_from_all_servers(4)
