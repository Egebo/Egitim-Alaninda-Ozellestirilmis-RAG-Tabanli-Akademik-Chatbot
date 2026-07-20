"""Flask route testleri: servis katmani mock'lanir, sadece HTTP katmani
(request/response, status kodlari, JSON sekli) dogrulanir. Gercek LLM cagrisi yapilmaz."""
import pytest

from services.conversations import _new_conv


@pytest.fixture
def client():
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_bos_mesaj_400_doner(client, fresh_state):
    conv_id = _new_conv()

    resp = client.post('/api/chat', json={'message': '', 'conv_id': conv_id})

    assert resp.status_code == 400


def test_basarili_sohbet_yaniti_200_doner(client, fresh_state, mocker, sahte_llm):
    conv_id = _new_conv()
    mocker.patch('services.chat._get_llm', return_value=sahte_llm())
    mocker.patch('services.chat.gorev_plani_olustur', return_value=[{'tool': 'GENERAL', 'soru': 'selam'}])
    mocker.patch('services.chat.adim_calistir', return_value={
        'tool': 'GENERAL', 'soru': 'selam', 'cevap': 'Merhaba! Nasıl yardımcı olabilirim?', 'kaynak': 'Sohbet'
    })

    resp = client.post('/api/chat', json={'message': 'selam', 'conv_id': conv_id, 'model': 'chatgpt'})

    assert resp.status_code == 200
    veri = resp.get_json()
    assert veri['niyet'] == 'GENERAL'
    assert veri['cevap'] == 'Merhaba! Nasıl yardımcı olabilirim?'


def test_stats_beklenen_alanlari_icerir(client, fresh_state):
    resp = client.get('/api/stats')

    assert resp.status_code == 200
    veri = resp.get_json()
    assert {'tokens', 'cost', 'documents', 'conversations'}.issubset(veri.keys())
