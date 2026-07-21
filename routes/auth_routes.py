from flask import Blueprint, jsonify, request, session

from services.auth import kullanici_dogrula

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    veri = request.get_json(silent=True) or {}
    email = (veri.get('email') or '').strip()
    sifre = veri.get('sifre') or ''

    kullanici = kullanici_dogrula(email, sifre)
    if not kullanici:
        return jsonify({'error': 'E-posta veya şifre hatalı.'}), 401

    session['kullanici_id'] = kullanici['id']
    session['email'] = kullanici['email']
    return jsonify({'ok': True, 'email': kullanici['email']})


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


@auth_bp.route('/api/me', methods=['GET'])
def api_me():
    if 'kullanici_id' not in session:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True, 'email': session.get('email')})
