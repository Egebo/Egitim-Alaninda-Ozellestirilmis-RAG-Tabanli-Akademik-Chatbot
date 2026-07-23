# Dağıtım Rehberi — Oracle Cloud Always Free

Bu rehber, chatbotu jüri/işveren gibi üçüncü kişilerin erişebileceği kalıcı bir
public URL'de yayına almak için yazıldı (geçici tünel değil — sunucu kapalıyken
de link çalışır). Mimari: **Oracle Cloud VM (Ubuntu, ARM) → gunicorn (tek
worker) → nginx (reverse proxy + HTTPS) → Let's Encrypt**.

Oracle Cloud'un "Always Free" katmanı süresiz ücretsiz (DigitalOcean'ın
GitHub Student Pack kredisinin aksine, bu bir promosyon değil — hesap
yaşadığı sürece geçerli). Kart doğrulaması istiyor ama Always Free kaynakları
kullandığın sürece fatura kesmiyor.

Login zaten var, bu yüzden herkes serbestçe giremiyor — ama aşağıdaki adımlar
tamamlanmadan (özellikle "Prod güvenlik" bölümü) sistemi internete açma.

## 0. Ön koşullar

- Oracle Cloud hesabı ([cloud.oracle.com](https://www.oracle.com/cloud/free/) →
  "Start for free"). Kart bilgisi istiyor (doğrulama için), Always Free
  kaynaklar için ücret çekmiyor.
- Domain **gerekmiyor**. Let's Encrypt sertifikası çıplak IP'ye verilmez ama
  gerçek bir domain almana da gerek yok: [sslip.io](https://sslip.io) IP'ni
  otomatik bir hostname'e çevirir (örn. sunucu IP'n `164.90.12.34` ise
  hostname `164-90-12-34.sslip.io` olur) ve bu gerçek/çözümlenebilir bir DNS
  kaydı olduğu için certbot bu isme de ücretsiz sertifika verir. Bölüm 2 ve 8
  bunu kullanıyor — hiçbir yerde para ödemiyorsun.
- SSH anahtarın (yoksa: `ssh-keygen -t ed25519`)

## 1. VM oluştur (Oracle Cloud konsolu)

1. Konsolda hamburger menü → **Compute → Instances → Create Instance**
2. Name: `academic-chatbot`
3. Image and shape → **Change Image** → **Canonical Ubuntu 24.04** (Ampere/ARM
   sürümünü seç, "aarch64" yazan)
4. **Change Shape** → **Ampere** (ARM) ailesi → **VM.Standard.A1.Flex** →
   "Always Free eligible" etiketli olanı seç. OCPU/RAM'i **2 OCPU / 12 GB**
   yap (2026 ortası itibarıyla Always Free ARM limiti bu — hesabına göre daha
   fazla gösterebilir, göstermiyorsa 2/12 yeterli, bu proje için bolca).
5. Networking: varsayılan VCN'i kullan, **"Assign a public IPv4 address"**
   işaretli kalsın.
6. SSH keys: public key'ini yapıştır (`~/.ssh/id_ed25519.pub` içeriği) ya da
   "Generate a key pair" ile Oracle'a ürettir ve private key'i indir.
7. Create.

Oluşunca **Instance Details** sayfasında bir public IP göreceksin (örn.
`164.90.12.34`).

⚠️ **Oracle'a özgü bir tuzak:** DigitalOcean'ın aksine, Oracle'da dışarıdan
gelen trafiğe izin vermek için **iki ayrı** güvenlik duvarı katmanını açman
gerekiyor — biri bulut tarafında (VCN Security List), biri sunucunun kendi
iptables kuralları. Bölüm 3'te ikisi de var, atlama.

**VCN Security List'i aç:** Instance Details → Subnet linkine tıkla → Security
Lists → varsayılan listeye tıkla → **Add Ingress Rules** → Source CIDR
`0.0.0.0/0`, IP Protocol TCP, Destination Port `80` ekle; aynı şekilde bir
tane daha `443` için ekle. (`22`/SSH zaten varsayılanda açık gelir.)

## 2. Hostname'ini belirle (domain almadan, ücretsiz)

Gerçek bir domain'in varsa onu kullan (bir A kaydıyla sunucu IP'sine
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
ssh ubuntu@SUNUCU_IP   # Oracle'ın Ubuntu image'inde varsayılan kullanıcı 'ubuntu', 'root' değil

# Uygulamayı ayrı bir kullanıcıyla çalıştır
sudo adduser --disabled-password --gecos "" chatbot
sudo usermod -aG sudo chatbot

# 1) Sunucunun KENDİ güvenlik duvarı (iptables) — Oracle'ın Ubuntu image'i
# varsayılan olarak 80/443'ü bile bloklar, Bölüm 1'deki VCN kuralı tek başına
# yetmez. ufw, iptables üzerine kurulu, ikisini birlikte kullanmak sorun değil.
sudo apt update && sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

sudo apt install -y python3.11 python3.11-venv python3-pip git nginx certbot python3-certbot-nginx
```

Kurulumdan sonra `curl -I http://SUNUCU_IP` (henüz nginx'te site tanımlı
olmadığı için 404/502 dönebilir, önemli olan bağlantının reddedilmemesi)
ile iki katmanlı güvenlik duvarının gerçekten açık olduğunu doğrulayabilirsin.

## 4. Kodu getir ve kur

```bash
su - chatbot
git clone <REPO_URL> /opt/academic-chatbot   # ya da: scp ile lokalden kopyala
cd /opt/academic-chatbot

python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-deploy.txt
```

Bu bir ARM sunucu (aarch64) — çoğu paket (torch, chromadb, sentence-transformers
dahil) önceden derlenmiş ARM wheel'leri sağlıyor, ama ilk `pip install` yine de
bazı paketleri kaynaktan derlemek zorunda kalırsa normalden (birkaç dakika)
uzun sürebilir. Hata almadan bitmesi yeterli, süresi önemli değil.

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

- `conversations.db`, `demo_okul.db`, `chroma_db/`, `uploads/` sunucunun kendi
  diskinde (Always Free ile gelen 200 GB blok depolamanın içinde) yaşıyor —
  Render/Railway gibi PaaS'ların aksine deploy/restart'ta silinmez. Yine de
  düzenli **yedek** almak istersen: `scp` ile bu dosyaları periyodik indir ya
  da bir cron ile Oracle Object Storage'a yükle (Always Free'de 20 GB dahil;
  bu rehberin kapsamı dışında).
- `academic-chatbot.service`'te bilerek **tek gunicorn worker** kullanılıyor:
  uygulamanın paylaşılan durumu (`core/state.py::AppState` — sohbetler, günlük
  bütçe sayacı) process-içi bellekte tutuluyor; birden fazla worker açılırsa her
  biri kendi kopyasını tutar ve günlük bütçe tavanı gerçekte worker sayısı kadar
  katlanır. Bu projenin trafik hacminde (demo amaçlı) yeterli.
- SQLite düşük-orta eşzamanlılıkta sorunsuz; onlarca kişi aynı anda mesaj
  yazmıyorsa (ki bir demo linkinde olası değil) sorun çıkarmaz.
