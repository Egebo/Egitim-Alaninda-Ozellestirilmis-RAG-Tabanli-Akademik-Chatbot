import json

from flask import Blueprint, request, jsonify, Response, stream_with_context

from core.state import state
from core.lazy_imports import ensure_imports
from services.chat import chat_yanit_uret, chat_yanit_uret_stream

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/api/init', methods=['POST'])
def api_init():
    try:
        ensure_imports()
        return jsonify({'ok': True, 'message': 'Sistem hazır!'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@chat_bp.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    soru = data.get('message', '').strip()
    conv_id = data.get('conv_id', state.active_conv_id)
    model = data.get('model', 'chatgpt')
    karsilastir = data.get('karsilastir', False)

    if not soru:
        return jsonify({'error': 'Mesaj boş olamaz'}), 400

    result = chat_yanit_uret(soru, conv_id, model, karsilastir)
    return jsonify(result)


@chat_bp.route('/api/chat/stream', methods=['POST'])
def api_chat_stream():
    """
    /api/chat ile aynı işi yapar ama Server-Sent Events (SSE) ile orkestratörün
    adım adım ilerlemesini canlı yayınlar (görev planı -> her adım başladı/bitti ->
    gerekirse birleştiriliyor -> final). Frontend fetch + ReadableStream ile tüketir.
    """
    data = request.json
    soru = data.get('message', '').strip()
    conv_id = data.get('conv_id', state.active_conv_id)
    model = data.get('model', 'chatgpt')
    karsilastir = data.get('karsilastir', False)

    if not soru:
        return jsonify({'error': 'Mesaj boş olamaz'}), 400

    def event_stream():
        for olay in chat_yanit_uret_stream(soru, conv_id, model, karsilastir):
            yield f'data: {json.dumps(olay, ensure_ascii=False)}\n\n'

    return Response(stream_with_context(event_stream()), mimetype='text/event-stream')


@chat_bp.route('/api/stats', methods=['GET'])
def api_stats():
    return jsonify({
        'tokens': state.global_tokens,
        'cost': f'${state.global_cost_usd:.5f}',
        'documents': state.rag_manager.list_documents() if state.rag_manager else [],
        'conversations': len(state.conversations)
    })
