# Dağıtım Rehberi — DigitalOcean Droplet

Bu rehber, chatbotu jüri/işveren gibi üçüncü kişilerin erişebileceği kalıcı bir
public URL'de yayına almak için yazıldı (geçici tünel değil — sunucu kapalıyken
de link çalışır). Mimari: **Droplet (Ubuntu) → gunicorn (tek worker) → nginx
(reverse proxy + HTTPS) → Let's Encrypt**.

Login zaten var, bu yüzden herkes serbestçe giremiyor — ama aşağıdaki adımlar
tamamlanmadan (özellikle "Prod güvenlik" bölümü) sistemi internete açma.

## 0. Ön koşullar

- DigitalOcean hesabı (öğrenci kredisiyle — droplet ücreti oradan düşer, cepten
  çıkmaz)
- Domain **gerekmiyor**. Let's Encrypt sertifikası çıplak IP'ye verilmez ama
  gerçek bir domain almana da gerek yok: [sslip.io](https://sslip.io) IP'ni
  otomatik bir hostname'e çevirir (örn. droplet IP'n `164.90.12.34` ise
  hostname `164-90-12-34.sslip.io` olur) ve bu gerçek/çözümlenebilir bir DNS
  kaydı olduğu için certbot bu isme de ücretsiz sertifika verir. Bölüm 2 ve 8
  bunu kullanıyor — hiçbir yerde para ödemiyorsun.
- SSH anahtarın (yoksa: `ssh-keygen -t ed25519`)

## 1. Droplet oluştur (DO web konsolu)

1. Create → Droplets
2. Image: **Ubuntu 24.04 (LTS) x64**
3. Plan: Basic, en az **2 GB RAM / 1 vCPU** (~$12/ay). 1 GB'lık en ucuz plan,
   HuggingFace embedding modeli (`intfloat/multilingual-e5-small`) + LangChain +
   Chroma aynı anda bellekte açıldığında sıkışabilir — 2 GB ile aylarca $200
   kredin yeter (~16 ay).
4. Datacenter: sana/hedef kitleye en yakın region (örn. Frankfurt)
5. Authentication: SSH key (şifre değil) ekle
6. Hostname: `academic-chatbot` gibi bir isim ver, Create Droplet

Oluşunca bir public IP alacaksın (örn. `164.90.12.34`).

## 2. Hostname'ini belirle (domain almadan, ücretsiz)

Gerçek bir domain'in varsa onu kullan (bir A kaydıyla droplet IP'sine
yönlendir). Yoksa hiçbir şey kurman/satın alman gerekmiyor — IP'ni
`sslip.io` formatına çevir:

```
IP:       164.90.12.34
Hostname: 164-90-12-34.sslip.io
```

(Noktaları tire yap, sonuna `.sslip.io` ekle.) Bu, aşağıdaki bölümlerde
geçen `ALAN_ADIN` yerine kullanacağın değer — anında çalışır, DNS
yayılmasını beklemene bile gerek yok.

## 3. Sunucu temel kurulumu

```bash
ssh root@DROPLET_IP

# Uygulamayı root yerine ayrı bir kullanıcıyla çalıştır
adduser --disabled-password --gecos "" chatbot
usermod -aG sudo chatbot

# Güvenlik duvarı: sadece SSH/HTTP/HTTPS dışa açık, 5000 (Flask/gunicorn) KAPALI
apt update && apt install -y ufw
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

apt install -y python3.11 python3.11-venv python3-pip git nginx certbot python3-certbot-nginx
```

## 4. Kodu getir ve kur

```bash
su - chatbot
git clone <REPO_URL> /opt/academic-chatbot   # ya da: scp ile lokalden kopyala
cd /opt/academic-chatbot

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-deploy.txt
```

## 5. `.env` dosyası (gerçek sırlarla, gitignore'lu)

```bash
cp .env.example .env
nano .env
```

Doldur:

- `OPENAI_API_KEY` / `GOOGLE_API_KEY` — gerçek anahtarların
- `SECRET_KEY` — **mutlaka sabit bir değer ver** (üretmek için:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`).
  Boş bırakırsan her `systemctl restart`ta tüm oturumlar düşer.
- `DAILY_BUDGET_USD` — herkese açık demo için günlük OpenAI/Gemini harcama
  tavanı (örn. `3.0`). Aşılınca chatbot LLM'e hiç gitmeden "kota doldu" mesajı
  döner — bkz. `services/guardrails.py::gunluk_butce_asildi_mi`.
- `FLASK_DEBUG` — **boş bırak ya da `0` yap.** `1` yaparsan Werkzeug'un
  interaktif hata konsolu açılır (uzaktan kod çalıştırma riski). Zaten prod'da
  gunicorn kullanıldığı için bu değişken `app.py`'nin `app.run(...)` satırınca
  hiç okunmaz — sadece birinin yanlışlıkla `python app.py` çalıştırma ihtimaline
  karşı bir güvenlik ağı.

## 6. Demo giriş bilgileri hakkında

`admin@admin.com` / `123456` gibi demo hesaplar kasıtlı — jüri/işveren linke
girince deneyebilsin diye. Bunu login ekranında açıkça göstermek (örn. "Demo
hesap: ...") gayet normal bir demo pattern'i; sorun değil. İstersen
`demo_okul.db`'deki `kullanicilar` tablosunda şifreyi değiştirebilirsin
(`werkzeug.security.generate_password_hash` ile hash'le, düz metin yazma).

## 7. systemd servisi

```bash
sudo cp deploy/academic-chatbot.service /etc/systemd/system/
# Dosyadaki User/Group/WorkingDirectory zaten 'chatbot' / /opt/academic-chatbot
# varsayımıyla yazıldı — farklı kullanıcı/yol kullandıysan düzenle.
sudo systemctl daemon-reload
sudo systemctl enable --now academic-chatbot
sudo systemctl status academic-chatbot   # active (running) görmelisin
```

İlk açılış (embedding modelini indirme) birkaç dakika sürebilir —
`journalctl -u academic-chatbot -f` ile takip et.

## 8. nginx + HTTPS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/academic-chatbot
sudo nano /etc/nginx/sites-available/academic-chatbot
# ALAN_ADIN'i Bölüm 2'de belirlediğin hostname ile değiştir — gerçek bir
# domain'in yoksa bu, 164-90-12-34.sslip.io gibi görünecek (kendi IP'nle).
sudo ln -s /etc/nginx/sites-available/academic-chatbot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# HTTPS sertifikası (nginx config'ini otomatik günceller, 80->443 yönlendirmesi ekler)
# ALAN_ADIN yerine yine aynı hostname'i (sslip.io kullanıyorsan onu) yaz.
sudo certbot --nginx -d ALAN_ADIN
```

sslip.io ile de gerçek bir Let's Encrypt sertifikası alırsın — HTTP'ye düşmüyorsun,
login bilgileri şifreli kanaldan gider. Tek fark: link `164-90-12-34.sslip.io`
gibi görünür, `senin-adin.com` gibi değil. İş başvurusu/jüri linki için yeterli;
istersen ileride gerçek bir domain alıp sadece bu bölümü tekrar çalıştırman
yeterli.

## 9. Doğrulama

- `https://ALAN_ADIN` tarayıcıda açılmalı, login ekranı gelmeli
- Bir mesaj gönderip akış göstergesinin (adım adım) canlı çalıştığını doğrula
  (nginx SSE buffering kapalıysa çalışır — Bölüm 8'deki config bunu zaten sağlıyor)
- `DAILY_BUDGET_USD` tavanını test etmek istersen geçici olarak küçük bir değere
  (örn. `0.001`) çekip bir mesaj gönder, "kota doldu" mesajını görmelisin

## 10. Güncelleme akışı

```bash
su - chatbot
cd /opt/academic-chatbot
git pull
source venv/bin/activate
pip install -r requirements.txt -r requirements-deploy.txt   # bağımlılık değiştiyse
sudo systemctl restart academic-chatbot
```

## Kalıcılık ve bilinen sınırlamalar

- `conversations.db`, `demo_okul.db`, `chroma_db/`, `uploads/` droplet'in kendi
  diskinde yaşıyor — Render/Railway gibi PaaS'ların aksine deploy/restart'ta
  silinmez. Yine de düzenli **yedek** almak istersen: `scp` ile bu dosyaları
  periyodik indir ya da bir cron ile DO Spaces'e yükle (bu rehberin kapsamı
  dışında).
- `academic-chatbot.service`'te bilerek **tek gunicorn worker** kullanılıyor:
  uygulamanın paylaşılan durumu (`core/state.py::AppState` — sohbetler, günlük
  bütçe sayacı) process-içi bellekte tutuluyor; birden fazla worker açılırsa her
  biri kendi kopyasını tutar ve günlük bütçe tavanı gerçekte worker sayısı kadar
  katlanır. Bu projenin trafik hacminde (demo amaçlı) yeterli.
- SQLite düşük-orta eşzamanlılıkta sorunsuz; onlarca kişi aynı anda mesaj
  yazmıyorsa (ki bir demo linkinde olası değil) sorun çıkarmaz.
