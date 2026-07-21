from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os

from core.state import state
from core.lazy_imports import ensure_imports
from core import document_store as belge_deposu
from services.crawler import website_to_rag

document_bp = Blueprint('documents', __name__)


@document_bp.route('/api/documents', methods=['GET'])
def api_list_documents():
    """Verilen sohbetin erişebildiği belgeleri (özel + global) döner —
    composer'daki 'N belge' popover'ı bunu kullanır. conv_id verilmezse
    (geriye dönük uyumluluk) tüm belgeler döner."""
    ensure_imports()
    conv_id = request.args.get('conv_id')
    izinli = state.rag_manager.erisilebilir_belgeler(conv_id)
    return jsonify({'documents': list(izinli.keys())})


@document_bp.route('/api/documents/all', methods=['GET'])
def api_list_all_documents():
    """Yönetim bölümü ('Yüklü Dosyalar') için: TÜM belgeleri kapsam bilgisiyle
    birlikte döner; özel belgeler için sahibi sohbetin adı da eklenir."""
    ensure_imports()
    kayitlar = belge_deposu.tum_kapsamlari_listele()
    sonuc = []
    for belge_adi in state.rag_manager.list_documents():
        kayit = kayitlar.get(belge_adi)
        if kayit is None:
            sonuc.append({'belge_adi': belge_adi, 'kapsam': 'global', 'sohbet_id': None, 'sohbet_adi': None})
        else:
            sohbet_adi = None
            if kayit['sohbet_id'] and kayit['sohbet_id'] in state.conversations:
                sohbet_adi = state.conversations[kayit['sohbet_id']]['name']
            sonuc.append({
                'belge_adi': belge_adi, 'kapsam': kayit['kapsam'],
                'sohbet_id': kayit['sohbet_id'], 'sohbet_adi': sohbet_adi
            })
    return jsonify({'documents': sonuc})


@document_bp.route('/api/documents/upload', methods=['POST'])
def api_upload():
    ensure_imports()
    if 'files' not in request.files:
        return jsonify({'error': 'Dosya seçilmedi'}), 400

    conv_id = request.form.get('conv_id')
    kapsam = request.form.get('kapsam', 'ozel')
    if kapsam == 'ozel' and not conv_id:
        return jsonify({'error': "'ozel' kapsam için conv_id gerekli"}), 400

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
            belge_deposu.kapsam_kaydet(doc_name, kapsam, conv_id if kapsam == 'ozel' else None)
            uploaded.append(doc_name)
        except Exception as e:
            errors.append(f'{filename}: {e}')

    izinli = state.rag_manager.erisilebilir_belgeler(conv_id)
    return jsonify({
        'uploaded': uploaded,
        'errors': errors,
        'documents': list(izinli.keys())
    })


@document_bp.route('/api/documents/<doc_name>', methods=['DELETE'])
def api_delete_doc(doc_name):
    ensure_imports()
    state.rag_manager.remove_document(doc_name)
    belge_deposu.belge_sil(doc_name)
    conv_id = request.args.get('conv_id')
    izinli = state.rag_manager.erisilebilir_belgeler(conv_id)
    return jsonify({'ok': True, 'documents': list(izinli.keys())})


@document_bp.route('/api/documents/<doc_name>/kapsam', methods=['POST'])
def api_belge_kapsamini_guncelle(doc_name):
    """Yönetim bölümünden bir belgenin kapsamını özel↔global değiştirir."""
    ensure_imports()
    if doc_name not in state.rag_manager.documents:
        return jsonify({'error': 'Belge bulunamadı'}), 404

    veri = request.get_json(silent=True) or {}
    kapsam = veri.get('kapsam')
    conv_id = veri.get('conv_id')
    if kapsam not in ('ozel', 'global'):
        return jsonify({'error': 'Geçersiz kapsam'}), 400
    if kapsam == 'ozel' and not conv_id:
        return jsonify({'error': "'ozel' kapsam için conv_id gerekli"}), 400

    belge_deposu.kapsam_kaydet(doc_name, kapsam, conv_id if kapsam == 'ozel' else None)
    return jsonify({'ok': True})


@document_bp.route('/api/crawl', methods=['POST'])
def api_crawl():
    ensure_imports()
    data = request.json or {}
    url = data.get('url', '').strip()
    max_pages = int(data.get('max_pages', 30))
    conv_id = data.get('conv_id')
    kapsam = data.get('kapsam', 'ozel')

    if not url or not url.startswith('http'):
        return jsonify({'error': 'Geçerli URL girin'}), 400
    if kapsam == 'ozel' and not conv_id:
        return jsonify({'error': "'ozel' kapsam için conv_id gerekli"}), 400

    result = website_to_rag(url, max_pages=max_pages)
    if not result['crawled']:
        return jsonify({'error': 'İçerik alınamadı'}), 400

    belge_deposu.kapsam_kaydet(result['doc_name'], kapsam, conv_id if kapsam == 'ozel' else None)

    izinli = state.rag_manager.erisilebilir_belgeler(conv_id)
    return jsonify({
        'ok': True,
        'crawled': result['crawled'],
        'doc_name': result['doc_name'],
        'documents': list(izinli.keys())
    })
