from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os

from core.state import state
from core.lazy_imports import ensure_imports
from services.crawler import website_to_rag

document_bp = Blueprint('documents', __name__)


@document_bp.route('/api/documents', methods=['GET'])
def api_list_documents():
    ensure_imports()
    return jsonify({'documents': state.rag_manager.list_documents()})


@document_bp.route('/api/documents/upload', methods=['POST'])
def api_upload():
    ensure_imports()
    if 'files' not in request.files:
        return jsonify({'error': 'Dosya seçilmedi'}), 400

    files = request.files.getlist('files')
    uploaded = []
    errors = []

    for f in files:
        if f.filename == '':
            continue
        filename = secure_filename(f.filename)
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        f.save(path)
        try:
            doc_name = state.rag_manager.add_document(path)
            uploaded.append(doc_name)
        except Exception as e:
            errors.append(f'{filename}: {e}')

    return jsonify({
        'uploaded': uploaded,
        'errors': errors,
        'documents': state.rag_manager.list_documents()
    })


@document_bp.route('/api/documents/<doc_name>', methods=['DELETE'])
def api_delete_doc(doc_name):
    ensure_imports()
    state.rag_manager.remove_document(doc_name)
    return jsonify({'ok': True, 'documents': state.rag_manager.list_documents()})


@document_bp.route('/api/crawl', methods=['POST'])
def api_crawl():
    ensure_imports()
    data = request.json
    url = data.get('url', '').strip()
    max_pages = int(data.get('max_pages', 30))

    if not url or not url.startswith('http'):
        return jsonify({'error': 'Geçerli URL girin'}), 400

    result = website_to_rag(url, max_pages=max_pages)
    if not result['crawled']:
        return jsonify({'error': 'İçerik alınamadı'}), 400

    return jsonify({
        'ok': True,
        'crawled': result['crawled'],
        'doc_name': result['doc_name'],
        'documents': state.rag_manager.list_documents()
    })
