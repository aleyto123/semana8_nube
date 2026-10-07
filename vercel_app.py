"""Entrada WSGI para Vercel. Reutiliza la API del servidor local."""
from io import BytesIO
from flask import Flask, Response, request
from app import Handler

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16384

class RequestBridge(Handler):
    def __init__(self):
        self.command = request.method
        self.path = request.full_path.removesuffix('?')
        self.headers = request.headers
        self.rfile = BytesIO(request.get_data())
        self.wfile = BytesIO()
        self.status = 200
        self.response_headers = []

    def send_response(self, code, message=None):
        self.status = code
        self.response_headers = []
        self.wfile = BytesIO()

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        pass

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
def dispatch(path):
    bridge = RequestBridge()
    if request.method == 'HEAD':
        bridge.command = 'GET'
    bridge.handle_request()
    return Response(bridge.wfile.getvalue(), status=bridge.status, headers=bridge.response_headers)

@app.errorhandler(413)
def too_large(error):
    return {'error': 'Petición demasiado grande.'}, 413
