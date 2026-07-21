"""Login/logout/me endpoint'lerinin ve /api/* route korumasinin HTTP
davranisini dogrular. Gercek demo_okul.db'yi (sabit tohum verisiyle) kullanir,
gercek LLM cagrisi yapmaz."""
import pytest


@pytest.fixture
def client():
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_me_giris_yapmadan_401_doner(client):
    resp = client.get('/api/me')
    assert resp.status_code == 401


def test_dogru_bilgilerle_login_basarili(client):
    resp = client.post('/api/login', json={'email': 'admin@admin.com', 'sifre': '123456'})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True


def test_yanlis_sifreyle_login_401_doner(client):
    resp = client.post('/api/login', json={'email': 'admin@admin.com', 'sifre': 'yanlis'})
    assert resp.status_code == 401


def test_login_sonrasi_me_dogru_bilgiyi_doner(client):
    client.post('/api/login', json={'email': 'ogretmen@uni.com', 'sifre': 'pass123'})
    resp = client.get('/api/me')
    assert resp.status_code == 200
    assert resp.get_json() == {'authenticated': True, 'email': 'ogretmen@uni.com'}


def test_login_yapmadan_korumali_route_401_doner(client):
    resp = client.get('/api/stats')
    assert resp.status_code == 401


def test_login_sonrasi_korumali_route_erisilebilir(client):
    client.post('/api/login', json={'email': 'admin@admin.com', 'sifre': '123456'})
    resp = client.get('/api/stats')
    assert resp.status_code == 200


def test_logout_sonrasi_oturum_temizlenir(client):
    client.post('/api/login', json={'email': 'admin@admin.com', 'sifre': '123456'})
    client.post('/api/logout')
    resp = client.get('/api/me')
    assert resp.status_code == 401


def test_sayfa_route_u_login_gerektirmez(client):
    resp = client.get('/')
    assert resp.status_code == 200
