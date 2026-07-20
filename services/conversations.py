"""Sohbet (konuşma) oturumlarının oluşturulması ve yönetimi."""
from core.state import state


def _new_conv(isim=None):
    state.conv_counter += 1
    cid = str(state.conv_counter)
    state.conversations[cid] = {
        'name': isim or f'Sohbet {state.conv_counter}',
        'history': [],
        'tokens': 0,
        'cost': 0.0,
    }
    state.active_conv_id = cid
    return cid
