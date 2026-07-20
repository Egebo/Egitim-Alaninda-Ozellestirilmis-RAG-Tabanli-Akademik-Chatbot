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
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

from services.conversations import _new_conv
from routes.pages import pages_bp
from routes.chat_routes import chat_bp
from routes.conversation_routes import conversation_bp
from routes.document_routes import document_bp

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Maksimum yüklenebilir dosya boyutu: 50MB
os.makedirs('uploads', exist_ok=True)

app.register_blueprint(pages_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(conversation_bp)
app.register_blueprint(document_bp)

_new_conv()  # Uygulama açılışında ilk (varsayılan) sohbeti oluştur

if __name__ == '__main__':
    print('🚀 Akademik Chatbot başlatılıyor...')
    print('📌 http://localhost:5000 adresinde çalışıyor')
    app.run(debug=True, host='0.0.0.0', port=5000)
