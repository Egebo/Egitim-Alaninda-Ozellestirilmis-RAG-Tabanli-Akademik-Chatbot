"""Sohbet (konuşma) oturumlarının oluşturulması ve yönetimi."""
from core.state import state
from core import conversation_store as depo


def _new_conv(isim=None):
    state.conv_counter += 1
    cid = str(state.conv_counter)
    isim = isim or f'Sohbet {state.conv_counter}'
    state.conversations[cid] = {
        'name': isim,
        'history': [],
        'tokens': 0,
        'cost': 0.0,
    }
    state.active_conv_id = cid
    depo.sohbet_ekle(cid, isim)
    return cid


def konusmalari_diskten_yukle():
    """
    Uygulama başlangıcında mevcut sohbetleri conversations.db'den belleğe
    yükler (sunucu yeniden başlasa da sohbetler kaybolmaz). Hiç kayıtlı sohbet
    yoksa (ilk çalıştırma) yeni boş bir sohbet oluşturur.
    """
    kayitli = depo.hepsini_yukle()
    if not kayitli:
        _new_conv()
        return
    state.conversations = kayitli
    state.conv_counter = max(int(cid) for cid in kayitli)
    state.active_conv_id = str(state.conv_counter)
