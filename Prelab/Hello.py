from bottle import route, run


@route('/hello')
def hello():
    return "Tino Jeromin"


@route('/')
def index():
    return """<a href='./hello' target='_self'>Hello</a>
        <a href='./input' target='_self'>Input</a>"""

@route('/input')
def input():
    return


run(host='localhost', port=8080, debug=True)
