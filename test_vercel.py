"""Comprueba las rutas y autenticación usando la entrada WSGI de Vercel."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app as backend
from api.index import app

class VercelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db, self.old_initialized = backend.DB, backend._initialized
        backend.DB = Path(self.temp.name) / 'test.db'
        backend._initialized = False
        self.client = app.test_client()

    def tearDown(self):
        backend.DB, backend._initialized = self.old_db, self.old_initialized
        self.temp.cleanup()

    def test_direct_frontend_routes_and_assets(self):
        for route in ('/', '/register', '/login', '/auth/mfa', '/dashboard', '/products/1', '/styles.css', '/screens.js'):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_registration_mfa_and_persistence_across_clients(self):
        data = dict(email='cloud@example.com', name='Cloud', store='Lima', password='Password1!')
        self.assertEqual(self.client.post('/api/register', json=data).status_code, 201)
        duplicate = self.client.post('/api/register', json=data)
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('ya está registrado', duplicate.json['error'])
        challenge = self.client.post('/api/login', json=data).json
        result = self.client.post('/api/mfa', json={'challenge': challenge['challenge'], 'code': backend.totp(challenge['secret'])})
        self.assertEqual(result.status_code, 200)
        headers = {'Authorization': 'Bearer ' + result.json['token']}
        backend._initialized = False
        another = app.test_client()
        self.assertEqual(another.get('/api/me', headers=headers).json['email'], data['email'])
        self.assertEqual(another.get('/api/products', headers=headers).status_code, 200)
        self.assertEqual(another.get('/api/health').json['status'], 'ok')

    def test_cloud_rejects_temporary_database_and_keeps_pages_available(self):
        with patch.dict(os.environ, {'VERCEL': '1', 'DATABASE_URL': '', 'POSTGRES_URL': ''}), patch.object(backend, 'KEY', b'x' * 32):
            self.assertEqual(self.client.get('/register').status_code, 200)
            response = self.client.get('/api/health')
            self.assertEqual(response.status_code, 503)
            self.assertIn('DATABASE_URL', response.json['error'])
            self.assertFalse(backend.DB.exists())

if __name__ == '__main__':
    unittest.main()
