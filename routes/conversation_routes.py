from flask import Blueprint, jsonify

from core.state import state
from core import conversation_store as depo
from services.conversations import _new_conv

conversation_bp = Blueprint('conversations', __name__)


@conversation_bp.route('/api/conversations', methods=['GET'])
def api_conversations():
    return jsonify({
        'conversations': [
            {'id': cid, 'name': c['name'], 'tokens': c['tokens'], 'cost': f"${c['cost']:.5f}"}
            for cid, c in state.conversations.items()
        ],
        'active': state.active_conv_id
    })


@conversation_bp.route('/api/conversations/new', methods=['POST'])
def api_new_conv():
    cid = _new_conv()
    return jsonify({'id': cid, 'name': state.conversations[cid]['name']})


@conversation_bp.route('/api/conversations/<conv_id>', methods=['DELETE'])
def api_delete_conv(conv_id):
    if conv_id in state.conversations:
        del state.conversations[conv_id]
        depo.sohbet_sil(conv_id)
    if state.conversations:
        state.active_conv_id = list(state.conversations.keys())[-1]
    else:
        _new_conv()
    return jsonify({'ok': True, 'active': state.active_conv_id})


@conversation_bp.route('/api/conversations/<conv_id>/switch', methods=['POST'])
def api_switch_conv(conv_id):
    if conv_id not in state.conversations:
        return jsonify({'error': 'Geçersiz sohbet'}), 404
    state.active_conv_id = conv_id
    conv = state.conversations[conv_id]
    return jsonify({
        'ok': True,
        'history': conv['history'],
        'tokens': conv['tokens'],
        'cost': f"${conv['cost']:.5f}"
    })


@conversation_bp.route('/api/conversations/<conv_id>/reset', methods=['POST'])
def api_reset_conv(conv_id):
    if conv_id not in state.conversations:
        return jsonify({'error': 'Geçersiz sohbet'}), 404
    state.conversations[conv_id]['history'] = []
    state.conversations[conv_id]['tokens'] = 0
    state.conversations[conv_id]['cost'] = 0.0
    depo.sohbet_sifirla(conv_id)
    return jsonify({'ok': True})
