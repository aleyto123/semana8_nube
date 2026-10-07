import json, tempfile, threading, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import app

class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.DB=app.ROOT/'test.db'
        app.DB.unlink(missing_ok=True)
        app.init()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); app.DB.unlink(missing_ok=True)
    def call(self,path,method='GET',data=None,token=''):
        req=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        try:
            with urlopen(req) as r: return r.status,json.load(r)
        except HTTPError as e: return e.code,json.load(e)
    def account(self,email,role='employee',store='Lima'):
        status,_=self.call('/api/register','POST',dict(email=email,name='Test',store=store,password='Password1!')); self.assertEqual(status,201)
        with app.connection() as c: c.execute('UPDATE users SET role=? WHERE email=?',(role,email))
        status,ch=self.call('/api/login','POST',dict(email=email,password='Password1!'));self.assertEqual(status,200);self.assertNotIn('token',ch)
        status,result=self.call('/api/mfa','POST',dict(challenge=ch['challenge'],code=app.totp(ch['secret'])));self.assertEqual(status,200)
        return result['token'],ch
    def test_registration_validation_and_duplicate(self):
        d=dict(email='duplicate@example.com',name='Test',store='Lima',password='weak')
        self.assertEqual(self.call('/api/register','POST',d)[0],400)
        d['password']='Password1!';self.assertEqual(self.call('/api/register','POST',d)[0],201);self.assertEqual(self.call('/api/register','POST',d)[0],400)
    def test_lock_after_five_failures(self):
        self.call('/api/register','POST',dict(email='lock@example.com',name='Test',store='Lima',password='Password1!'))
        for _ in range(5): self.assertEqual(self.call('/api/login','POST',dict(email='lock@example.com',password='bad'))[0],401)
        self.assertEqual(self.call('/api/login','POST',dict(email='lock@example.com',password='Password1!'))[0],429)
    def test_mfa_replay_and_three_attempts(self):
        _,ch=self.account('mfa@example.com')
        self.assertEqual(self.call('/api/mfa','POST',dict(challenge=ch['challenge'],code=app.totp(ch['secret'])))[0],400)
        _,new=self.call('/api/login','POST',dict(email='mfa@example.com',password='Password1!'));self.assertNotIn('secret',new)
        for _ in range(3):self.assertEqual(self.call('/api/mfa','POST',dict(challenge=new['challenge'],code='bad'))[0],401)
        self.assertEqual(self.call('/api/mfa','POST',dict(challenge=new['challenge'],code=app.totp(ch['secret'])))[0],400)
    def test_employee_and_auditor_permissions(self):
        employee,_=self.account('employee@example.com');auditor,_=self.account('auditor@example.com','auditor')
        self.assertEqual(self.call('/api/products/1','PATCH',{'price':1},employee)[0],403)
        self.assertEqual(self.call('/api/products/1','PATCH',{'stock':9},employee)[0],200)
        self.assertEqual(self.call('/api/products/2','PATCH',{'stock':9},employee)[0],403)
        self.assertEqual(self.call('/api/products/1','PATCH',{'stock':9},auditor)[0],403)
        self.assertEqual(self.call('/api/reports',token=auditor)[0],200)
        self.assertEqual(self.call('/api/users',token=employee)[0],403)
    def test_manager_scope_and_token_tampering(self):
        manager,_=self.account('manager@example.com','manager')
        status,rows=self.call('/api/products',token=manager);self.assertEqual(status,200);self.assertTrue(all(p['store']=='Lima' for p in rows))
        self.assertEqual(self.call('/api/products/2','DELETE',token=manager)[0],403)
        self.assertEqual(self.call('/api/products/1','PATCH',{'store':'Arequipa'},manager)[0],403)
        self.assertEqual(self.call('/api/products',token=manager+'x')[0],403)
        self.assertEqual(self.call('/api/products')[0],403)

if __name__=='__main__':unittest.main()
