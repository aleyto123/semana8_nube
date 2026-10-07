"""TechStore: servidor local y API compartida con el despliegue de Vercel."""
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, struct, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from pathlib import Path
from contextlib import contextmanager
import threading
from storage import connect, ConfigurationError, is_integrity_error

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'techstore.db'
KEY_FILE = ROOT / '.jwt-secret'
KEY = os.getenv('JWT_SECRET', '').encode()
if not KEY and not os.getenv('VERCEL'):
    if not KEY_FILE.exists(): KEY_FILE.write_text(secrets.token_hex(32))
    KEY = KEY_FILE.read_bytes()
production_domain = os.getenv('VERCEL_PROJECT_PRODUCTION_URL') or os.getenv('VERCEL_URL')
BASE = os.getenv('BASE_URL') or ('https://' + production_domain if os.getenv('VERCEL') and production_domain else 'http://localhost:8000')
BASE = BASE.rstrip('/')
_initialized = False
_init_lock = threading.Lock()

def connection():
    return connect(DB)

def ensure_initialized():
    global _initialized
    if os.getenv('VERCEL') and len(KEY) < 32:
        raise ConfigurationError('Configura JWT_SECRET en Vercel con al menos 32 caracteres y vuelve a desplegar.')
    if not _initialized:
        with _init_lock:
            if not _initialized:
                init()
                _initialized = True

def init():
    with connection() as c:
        if c.postgres:
            # Serializa la creación inicial entre distintas instancias de Vercel.
            c.execute('SELECT pg_advisory_xact_lock(845208)')
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,name TEXT,store TEXT,role TEXT,password TEXT,totp TEXT,failures INTEGER DEFAULT 0,locked REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS challenges(id TEXT PRIMARY KEY,"user" INTEGER,expires REAL,attempts INTEGER DEFAULT 0,enroll INTEGER);
CREATE TABLE IF NOT EXISTS oauth_states(id TEXT PRIMARY KEY,provider TEXT,expires REAL);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT,store TEXT,price REAL CHECK(price>=0),stock INTEGER CHECK(stock>=0));''')
        if not c.execute('SELECT 1 FROM products').fetchone():
            c.executemany('INSERT INTO products(name,store,price,stock) VALUES(?,?,?,?)',[('Laptop Lenovo','Lima',2500,12),('Mouse Logitech','Arequipa',80,30)])
        # El administrador se crea solo por configuración del operador.
        email, password = os.getenv('ADMIN_EMAIL'), os.getenv('ADMIN_PASSWORD')
        if email and password:
            validate_password(password)
            c.execute('INSERT INTO users(email,name,store,role,password,totp) VALUES(?,?,?,?,?,?) ON CONFLICT(email) DO NOTHING',(email.lower(),'Administrador','Lima','admin',password_hash(password),new_totp()))
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b'=').decode()
def password_hash(p, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(p.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def validate_password(p):
    if not isinstance(p,str) or len(p)<8 or not re.search('[A-Z]',p) or not re.search('[0-9]',p) or not re.search('[^A-Za-z0-9]',p): raise ValueError('Contraseña: mínimo 8 caracteres, mayúscula, número y carácter especial.')
def new_totp(): return base64.b32encode(secrets.token_bytes(20)).decode()
def totp(secret, now=None):
    counter = int((time.time() if now is None else now)//30)
    digest = hmac.new(base64.b32decode(secret),struct.pack('>Q',counter),hashlib.sha1).digest(); offset=digest[-1]&15
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)
def token(user):
    data={'sub':str(user['id']),'exp':int(time.time())+3600,'iss':'techstore','aud':'techstore-web'}
    body=b64(b'{"alg":"HS256","typ":"JWT"}')+'.'+b64(json.dumps(data).encode())
    return body+'.'+b64(hmac.new(KEY,body.encode(),hashlib.sha256).digest())
def identity(auth, database=None):
    try:
        body,sig=auth.removeprefix('Bearer ').rsplit('.',1)
        if not hmac.compare_digest(sig,b64(hmac.new(KEY,body.encode(),hashlib.sha256).digest())): raise ValueError()
        payload=json.loads(base64.urlsafe_b64decode(body.split('.')[1]+'=='))
        if payload['exp']<time.time() or payload['iss']!='techstore' or payload['aud']!='techstore-web': raise ValueError()
        if database is not None:
            user=database.execute('SELECT * FROM users WHERE id=?',(int(payload['sub']),)).fetchone()
        else:
            with connection() as c: user=c.execute('SELECT * FROM users WHERE id=?',(int(payload['sub']),)).fetchone()
        if not user: raise ValueError()
        return user
    except Exception: raise PermissionError('Sesión inválida o vencida.')
def public(u): return {k:u[k] for k in ('id','email','name','store','role')}
def challenge(c,u):
    cid=secrets.token_urlsafe(32)
    # La configuración se ofrece una sola vez tras credenciales válidas.
    # La marca persistente de enrolamiento está en el prefijo del secreto.
    setup=not u['totp'].startswith('ok:')
    c.execute('DELETE FROM challenges WHERE "user"=?',(u['id'],))
    c.execute('INSERT INTO challenges VALUES(?,?,?,0,?)',(cid,u['id'],time.time()+300,int(setup)))
    result={'challenge':cid,'requires_mfa':True}
    if setup:
        result['secret']=u['totp']; result['uri']='otpauth://totp/'+u['email']+'?'+urlencode({'secret':u['totp'],'issuer':'TechStore','digits':6,'period':30})
    return result
def remote(url,data=None,headers=None):
    req=Request(url,data=urlencode(data).encode() if data else None,headers=headers or {})
    with urlopen(req,timeout=15) as r: return json.load(r)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,status,data,ctype='application/json'):
        raw=json.dumps(data).encode() if ctype=='application/json' else data.encode()
        self.send_response(status); self.send_header('Content-Type',ctype+'; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def do_PATCH(self): self.handle_request()
    def do_DELETE(self): self.handle_request()
    def handle_request(self):
        try:
            path=urlparse(self.path).path
            if path.startswith('/api/') or path.startswith(('/auth/google', '/auth/github')):
                ensure_initialized()
            self.dispatch()
        except ConfigurationError as e: self.respond(503,{'error':str(e)})
        except PermissionError as e: self.respond(403,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e: self.respond(400,{'error':str(e) or 'Datos inválidos'})
        except Exception as e:
            if is_integrity_error(e):
                self.respond(400,{'error':'Este correo ya está registrado. Inicia sesión.' if urlparse(self.path).path=='/api/register' else 'Los datos no cumplen los requisitos del registro.'})
            else:
                # No devuelve credenciales, consultas SQL ni detalles de conexión.
                self.respond(500,{'error':'No se pudo completar la operación. Revisa la conexión de la base de datos en Vercel.'})
    def dispatch(self):
        path=urlparse(self.path).path; method=self.command
        length=int(self.headers.get('Content-Length','0'))
        if length>16384: raise ValueError('Petición demasiado grande')
        data=json.loads(self.rfile.read(length)) if length else {}
        if path=='/api/health' and method=='GET':
            with connection() as c: c.execute('SELECT 1').fetchone()
            return self.respond(200,{'status':'ok','storage':'postgresql' if os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL') else 'sqlite'})
        # Archivos estáticos explícitos y rutas del frontend.
        if method=='GET' and path in ('/styles.css','/app.js','/screens.js','/data.js','/favicon.svg'):
            kind={'.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml'}
            return self.respond(200,(ROOT/path[1:]).read_text(encoding='utf-8'),kind[Path(path).suffix])
        frontend_routes=('/', '/login', '/register', '/auth/mfa', '/dashboard', '/products', '/inventory', '/movements', '/stores', '/users', '/reports', '/audit', '/profile', '/settings')
        if method=='GET' and (path in frontend_routes or re.fullmatch(r'/products/\d+',path)):
            return self.respond(200,(ROOT/'index.html').read_text(encoding='utf-8'),'text/html')
        with connection() as c:
            if path=='/api/register' and method=='POST':
                email=data['email'].strip().lower(); name=data['name'].strip(); store=data['store']; validate_password(data['password'])
                if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not name or len(name)>100 or store not in ('Lima','Arequipa'): raise ValueError('Email, nombre o tienda inválidos')
                c.execute('INSERT INTO users(email,name,store,role,password,totp) VALUES(?,?,?,?,?,?)',(email,name,store,'employee',password_hash(data['password']),new_totp()))
                return self.respond(201,{'message':'Registro completado. Inicia sesión y configura MFA.'})
            if path=='/api/login' and method=='POST':
                u=c.execute('SELECT * FROM users WHERE email=?',(data['email'].strip().lower(),),for_update=True).fetchone()
                if u and u['locked']>time.time(): return self.respond(429,{'error':'Cuenta bloqueada durante 15 minutos.'})
                good=u and u['password'] and hmac.compare_digest(u['password'],password_hash(data['password'],u['password'].split(':')[0]))
                if not good:
                    if u:
                        count=(0 if u['locked'] else u['failures'])+1
                        c.execute('UPDATE users SET failures=?,locked=? WHERE id=?',(count,time.time()+900 if count>=5 else 0,u['id']))
                    return self.respond(401,{'error':'Credenciales inválidas.'})
                c.execute('UPDATE users SET failures=0,locked=0 WHERE id=?',(u['id'],))
                return self.respond(200,challenge(c,u))
            if path=='/api/mfa' and method=='POST':
                ch=c.execute('SELECT * FROM challenges WHERE id=?',(data['challenge'],),for_update=True).fetchone()
                if not ch or ch['expires']<time.time() or ch['attempts']>=3: raise ValueError('Desafío vencido o bloqueado. Inicia sesión otra vez.')
                u=c.execute('SELECT * FROM users WHERE id=?',(ch['user'],)).fetchone(); secret=u['totp'].removeprefix('ok:')
                if not re.fullmatch(r'\d{6}',str(data['code'])) or not any(hmac.compare_digest(str(data['code']),totp(secret,time.time()+delta)) for delta in (-30,0,30)):
                    c.execute('UPDATE challenges SET attempts=attempts+1 WHERE id=?',(ch['id'],)); return self.respond(401,{'error':'Código inválido. Máximo 3 intentos.'})
                c.execute('UPDATE users SET totp=? WHERE id=?',('ok:'+secret,u['id'])); c.execute('DELETE FROM challenges WHERE id=?',(ch['id'],))
                return self.respond(200,{'token':token(u),'user':public(u)})
            if path.startswith('/auth/') and method=='GET':
                parts=path.strip('/').split('/'); provider=parts[1]
                if provider not in ('google','github'): raise ValueError('Proveedor inválido')
                client=os.getenv(provider.upper()+'_CLIENT_ID'); client_secret=os.getenv(provider.upper()+'_CLIENT_SECRET')
                if not client or not client_secret: return self.respond(503,{'error':'Configura '+provider.upper()+'_CLIENT_ID y '+provider.upper()+'_CLIENT_SECRET.'})
                callback=BASE+'/auth/'+provider+'/callback'
                if len(parts)==2:
                    state=secrets.token_urlsafe(32); c.execute('INSERT INTO oauth_states VALUES(?,?,?)',(state,provider,time.time()+300))
                    auth='https://accounts.google.com/o/oauth2/v2/auth' if provider=='google' else 'https://github.com/login/oauth/authorize'
                    self.send_response(302); self.send_header('Set-Cookie','oauth_state='+state+'; HttpOnly; SameSite=Lax; Path=/auth; Max-Age=300'+('; Secure' if BASE.startswith('https:') else '')); self.send_header('Location',auth+'?'+urlencode({'client_id':client,'redirect_uri':callback,'response_type':'code','scope':'openid email profile' if provider=='google' else 'read:user user:email','state':state})); self.end_headers(); return
                query=parse_qs(urlparse(self.path).query); state=query.get('state',[''])[0]
                valid=c.execute('SELECT * FROM oauth_states WHERE id=? AND provider=? AND expires>?',(state,provider,time.time())).fetchone()
                cookies=dict(x.strip().split('=',1) for x in self.headers.get('Cookie','').split(';') if '=' in x)
                if not valid or not hmac.compare_digest(cookies.get('oauth_state',''),state): raise ValueError('Estado OAuth inválido')
                c.execute('DELETE FROM oauth_states WHERE id=?',(state,))
                result=remote('https://oauth2.googleapis.com/token' if provider=='google' else 'https://github.com/login/oauth/access_token',{'client_id':client,'client_secret':client_secret,'code':query['code'][0],'redirect_uri':callback,'grant_type':'authorization_code'},{'Accept':'application/json'})
                headers={'Authorization':'Bearer '+result['access_token'],'Accept':'application/json','User-Agent':'TechStore'}
                profile=remote('https://openidconnect.googleapis.com/v1/userinfo' if provider=='google' else 'https://api.github.com/user',headers=headers)
                if provider=='google':
                    if not profile.get('email_verified'): raise ValueError('Email no verificado')
                    email=profile['email'].lower()
                else:
                    emails=remote('https://api.github.com/user/emails',headers=headers); email=next((e['email'].lower() for e in emails if e['primary'] and e['verified']),None)
                    if not email: raise ValueError('Email principal no verificado')
                u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                if not u:
                    c.execute('INSERT INTO users(email,name,store,role,password,totp) VALUES(?,?,?,?,?,?)',(email,profile.get('name') or email,'Lima','employee','',new_totp())); u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                if u['locked']>time.time(): raise PermissionError('Cuenta bloqueada')
                result=challenge(c,u); encoded=b64(json.dumps(result).encode())
                self.send_response(302); self.send_header('Location','/#mfa='+encoded); self.end_headers(); return
            u=identity(self.headers.get('Authorization',''),c)
            if path=='/api/me': return self.respond(200,public(u))
            if path=='/api/users':
                if u['role']!='admin': raise PermissionError('Solo administrador')
                if method=='GET': return self.respond(200,[public(x) for x in c.execute('SELECT * FROM users')])
                if method=='PATCH':
                    if data['role'] not in ('admin','manager','employee','auditor') or data['store'] not in ('Lima','Arequipa'): raise ValueError('Rol o tienda inválidos')
                    target=c.execute('SELECT * FROM users WHERE id=?',(data['id'],)).fetchone()
                    if not target: raise ValueError('Usuario inexistente')
                    if target['role']=='admin' and data['role']!='admin' and c.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]<=1: raise ValueError('Debe quedar un administrador')
                    c.execute('UPDATE users SET role=?,store=? WHERE id=?',(data['role'],data['store'],data['id'])); return self.respond(200,{'message':'Usuario actualizado'})
            if path in ('/api/products','/api/reports') or path.startswith('/api/products/'):
                if path=='/api/reports' and u['role']=='employee': raise PermissionError('No tienes permiso para reportes')
                if method=='GET':
                    rows=c.execute('SELECT * FROM products WHERE store=?',(u['store'],)) if u['role']=='manager' else c.execute('SELECT * FROM products')
                    return self.respond(200,[dict(x) for x in rows])
                if u['role']=='auditor': raise PermissionError('Auditor: solo lectura')
                if method=='POST' and path=='/api/products':
                    if u['role'] not in ('admin','manager'): raise PermissionError('No puedes crear productos')
                    store=data['store'] if u['role']=='admin' else u['store']; self.validate_product(data,store)
                    c.execute('INSERT INTO products(name,store,price,stock) VALUES(?,?,?,?)',(data['name'].strip(),store,data['price'],data['stock'])); return self.respond(201,{'message':'Producto creado'})
                pid=int(path.rsplit('/',1)[-1]); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
                if not p: raise ValueError('Producto inexistente')
                if u['role'] in ('manager','employee') and p['store']!=u['store']: raise PermissionError('Producto de otra tienda')
                if method=='DELETE':
                    if u['role'] not in ('admin','manager'): raise PermissionError('No puedes eliminar')
                    c.execute('DELETE FROM products WHERE id=?',(pid,)); return self.respond(200,{'message':'Producto eliminado'})
                if method=='PATCH':
                    if u['role']=='employee' and set(data)!={'stock'}: raise PermissionError('Empleado: solo puede actualizar stock')
                    merged=dict(p); merged.update(data)
                    if u['role']=='manager' and merged['store']!=u['store']: raise PermissionError('No puedes trasladar productos a otra tienda')
                    self.validate_product(merged,merged['store'])
                    c.execute('UPDATE products SET name=?,store=?,price=?,stock=? WHERE id=?',(merged['name'].strip(),merged['store'],merged['price'],merged['stock'],pid)); return self.respond(200,{'message':'Producto actualizado'})
            self.respond(404,{'error':'Ruta inexistente'})
    def validate_product(self,d,store):
        if store not in ('Lima','Arequipa') or not isinstance(d['name'],str) or not d['name'].strip() or len(d['name'])>100 or type(d['stock']) is not int or d['stock']<0 or type(d['price']) not in (int,float) or not 0<=d['price']<1e10: raise ValueError('Producto inválido')
if __name__=='__main__':
    init(); print('TechStore disponible en '+BASE,flush=True); ThreadingHTTPServer(('127.0.0.1',int(os.getenv('PORT','8000'))),Handler).serve_forever()
