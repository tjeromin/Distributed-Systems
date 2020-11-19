from bottle import route, run, template, request


@route('/')
def index():
    return "<a href='/hello'>go to hello</a><br>" \
           "<a href='/input'>go to input</a>"

@route('/hello')
def hello():
    return "Tino and Lorenz"

@route('/input')
def input():
    return '''
        <form action="/input" method="post">
            Username: <input name="username" type="text" />
            Favorite Bird: <input name="bird" type="text" />
            Password: <input name="password" type="password" />
            <input value="Submit" type="submit" />
        </form>
    '''

@route('/input', method='POST')
def do_input():
    username = request.forms.get('username')
    bird = request.forms.get('bird')
    password = request.forms.get('password')
    return "Welcome " + username + ", your password was correct (" + password + "), here is a picture of a " + bird + " for you."

run(host='localhost', port=8080, debug=True)