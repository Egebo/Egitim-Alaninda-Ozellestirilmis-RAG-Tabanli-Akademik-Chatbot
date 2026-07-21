"""
Akademik RAG & Agentic Chatbot — Flask Uygulama Girişi

Flask app'i oluşturur, Blueprint'leri (routes/) kaydeder ve sunucuyu başlatır.
Asıl iş mantığı core/ (çekirdek altyapı) ve services/ (RAG, Text-to-SQL, orkestratör,
sohbet, konuşma yönetimi, web crawler) paketlerinde yaşıyor.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import os
import secrets
import logging
from flask import Flask, jsonify, request, session
from dotenv import load_dotenv

load_dotenv()

from core.logging_config import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from core.database import demo_db_hazirla
from services.conversations import konusmalari_diskten_yukle
from routes.pages import pages_bp
from routes.chat_routes import chat_bp
from routes.conversation_routes import conversation_bp
from routes.document_routes import document_bp
from routes.auth_routes import auth_bp

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Maksimum yüklenebilir dosya boyutu: 50MB
os.makedirs('uploads', exist_ok=True)

app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
if not os.environ.get('SECRET_KEY'):
    logger.warning('SECRET_KEY tanımlı değil, rastgele bir tane üretildi — sunucu her yeniden '
                    'başladığında oturumlar geçersiz olur. Kalıcı oturumlar için .env dosyasına '
                    'SECRET_KEY ekleyin.')

app.register_blueprint(pages_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(conversation_bp)
app.register_blueprint(document_bp)
app.register_blueprint(auth_bp)

# Login gerektirmeyen tek API yolu: giriş ekranının kendisi.
ACIK_API_YOLLARI = {'/api/login'}


@app.before_request
def girisi_kontrol_et():
    if not request.path.startswith('/api/') or request.path in ACIK_API_YOLLARI:
        return  # sayfalar (index.html) ve login endpoint'i serbest — giriş ekranı orada render olur
    if 'kullanici_id' not in session:
        return jsonify({'error': 'Giriş gerekli.'}), 401


demo_db_hazirla()  # kullanicilar tablosunun (login için) var olduğundan emin ol — ML kütüphaneleri gerektirmez
konusmalari_diskten_yukle()  # conversations.db'den mevcut sohbetleri yükle (yoksa yeni bir tane oluştur)

if __name__ == '__main__':
    logger.info('🚀 Akademik Chatbot başlatılıyor...')
    logger.info('📌 http://localhost:5000 adresinde çalışıyor')
    app.run(debug=True, host='0.0.0.0', port=5000)
