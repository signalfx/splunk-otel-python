import json

import falcon
from wsgiref import simple_server


class HelloWorldResource(object):
    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        resp.body = json.dumps({"hello": "world"})


class ErrorResource(object):
    def on_get(self, req, resp):
        print(non_existent_var)


app = falcon.API()

app.add_route('/hello', HelloWorldResource())
app.add_route('/error', ErrorResource())

if __name__ == '__main__':
    port = 8000
    print('starting server: ', port)
    httpd = simple_server.make_server('127.0.0.1', port, app)
    httpd.serve_forever()
