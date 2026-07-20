"""Demo akademik SQLite veritabanının ilk kurulumu (şema + tohum veri)."""
import sqlite3


def _setup_database(db_filename):
    """
    Uygulama ilk kez başlatıldığında veya veritabanı silindiğinde çalıştırılır.
    SQLite üzerinde akademik şemayı (Öğrenciler, Akademisyenler, Dersler, Notlar, Projeler) oluşturur
    ve tohum (seed) verilerini ekler.
    """
    conn = sqlite3.connect(db_filename)
    cur = conn.cursor()

    # Tablo Tanımlamaları:
    # 1. Kullanıcılar tablosu (Gelecekteki giriş/auth sistemleri için taslak)
    cur.execute('CREATE TABLE kullanicilar   (kullaniciid   INTEGER PRIMARY KEY, email TEXT, sifrehash TEXT)')
    # 2. Üniversite Bölümleri
    cur.execute('CREATE TABLE bolumler       (bolumid       INTEGER PRIMARY KEY, bolumadi TEXT)')
    # 3. Akademisyenler (Hocalar)
    cur.execute('CREATE TABLE akademisyenler (akademisyenid INTEGER PRIMARY KEY, ad TEXT, soyad TEXT, unvan TEXT, bolumid INTEGER, eposta TEXT)')
    # 4. Öğrenciler (Bölüm ve Danışman akademisyen ilişkili)
    cur.execute('CREATE TABLE ogrenciler     (ogrenciid     INTEGER PRIMARY KEY, ad TEXT, soyad TEXT, bolumid INTEGER, eposta TEXT, kayityili INTEGER, danismanid INTEGER)')
    # 5. Dersler (Bölüm, Dersi veren hoca ve AKTS kredisi ilişkili)
    cur.execute('CREATE TABLE dersler        (dersid        INTEGER PRIMARY KEY, dersadi TEXT, bolumid INTEGER, akademisyenid INTEGER, akts INTEGER)')
    # 6. Notlar (Vize, final notları ve hesaplanan ortalama, harf notu, geçme/kalma durumu)
    cur.execute('CREATE TABLE notlar         (notid         INTEGER PRIMARY KEY, ogrenciid INTEGER, dersid INTEGER, vize INTEGER, final INTEGER, ortalama REAL, harfnotu TEXT, basaridurumu TEXT)')
    # 7. Mezuniyet/Bitirme Projeleri (Öğrenci ve Danışman hoca ilişkili)
    cur.execute('CREATE TABLE projeler       (projeid       INTEGER PRIMARY KEY, baslik TEXT, konu TEXT, ogrenciid INTEGER, danismanid INTEGER)')

    cur.executemany('INSERT INTO kullanicilar VALUES (?,?,?)', [
        (1,'admin@admin.com','123456'),
        (2,'ogretmen@uni.com','pass123')
    ])

    cur.executemany('INSERT INTO bolumler VALUES (?,?)', [
        (1, 'Bilgisayar Mühendisliği'),
        (2, 'Yazılım Mühendisliği'),
        (3, 'Elektrik-Elektronik Mühendisliği'),
        (4, 'Endüstri Mühendisliği'),
        (5, 'Yapay Zeka Mühendisliği')
    ])

    cur.executemany('INSERT INTO akademisyenler VALUES (?,?,?,?,?,?)', [
        (1, 'Ahmet', 'Yılmaz', 'Prof. Dr.', 1, 'ahmet.yilmaz@uni.edu.tr'),
        (2, 'Fatma', 'Çelik', 'Doç. Dr.', 2, 'fatma.celik@uni.edu.tr'),
        (3, 'Mehmet', 'Demir', 'Dr. Öğr. Üyesi', 3, 'mehmet.demir@uni.edu.tr'),
        (4, 'Zeynep', 'Arslan', 'Prof. Dr.', 1, 'zeynep.arslan@uni.edu.tr'),
        (5, 'Hüseyin', 'Kaya', 'Doç. Dr.', 4, 'huseyin.kaya@uni.edu.tr'),
        (6, 'Elif', 'Şahin', 'Dr. Öğr. Üyesi', 2, 'elif.sahin@uni.edu.tr'),
        (7, 'Murat', 'Özkan', 'Prof. Dr.', 3, 'murat.ozkan@uni.edu.tr'),
        (8, 'Selin', 'Aktaş', 'Dr. Öğr. Üyesi', 5, 'selin.aktas@uni.edu.tr'),
        (9, 'Caner', 'Soylu', 'Prof. Dr.', 5, 'caner.soylu@uni.edu.tr'),
        (10, 'Aslı', 'Yurt', 'Doç. Dr.', 4, 'asli.yurt@uni.edu.tr')
    ])

    cur.executemany('INSERT INTO ogrenciler VALUES (?,?,?,?,?,?,?)', [
        (1, 'Ali', 'Kaya', 1, 'ali.kaya@std.uni.edu.tr', 2022, 1),
        (2, 'Ayşe', 'Demir', 2, 'ayse.demir@std.uni.edu.tr', 2021, 2),
        (3, 'Cemil', 'Arslan', 1, 'cemil.arslan@std.uni.edu.tr', 2023, 4),
        (4, 'Deniz', 'Yılmaz', 3, 'deniz.yilmaz@std.uni.edu.tr', 2022, 3),
        (5, 'Emre', 'Çelik', 1, 'emre.celik@std.uni.edu.tr', 2022, 1),
        (6, 'Fatma', 'Kara', 2, 'fatma.kara@std.uni.edu.tr', 2021, 6),
        (7, 'Gizem', 'Şahin', 4, 'gizem.sahin@std.uni.edu.tr', 2022, 5),
        (8, 'Hakan', 'Doğan', 4, 'hakan.dogan@std.uni.edu.tr', 2023, 10),
        (9, 'İrem', 'Polat', 2, 'irem.polat@std.uni.edu.tr', 2022, 6),
        (10, 'Kerem', 'Yıldız', 1, 'kerem.yildiz@std.uni.edu.tr', 2022, 4),
        (11, 'Lale', 'Erdoğan', 3, 'lale.erdogan@std.uni.edu.tr', 2021, 7),
        (12, 'Mert', 'Güneş', 4, 'mert.gunes@std.uni.edu.tr', 2022, 5),
        (13, 'Nisan', 'Aydın', 2, 'nisan.aydin@std.uni.edu.tr', 2021, 2),
        (14, 'Okan', 'Kurt', 4, 'okan.kurt@std.uni.edu.tr', 2023, 10),
        (15, 'Pınar', 'Bulut', 1, 'pinar.bulut@std.uni.edu.tr', 2022, 1),
        (16, 'Burak', 'Şen', 5, 'burak.sen@std.uni.edu.tr', 2022, 8),
        (17, 'Gamze', 'Tekin', 5, 'gamze.tekin@std.uni.edu.tr', 2022, 9),
        (18, 'Serkan', 'Ak', 5, 'serkan.ak@std.uni.edu.tr', 2023, 8),
        (19, 'Melis', 'Can', 3, 'melis.can@std.uni.edu.tr', 2022, 3),
        (20, 'Umut', 'Kılıç', 3, 'umut.kilic@std.uni.edu.tr', 2023, 7),
        (21, 'Ece', 'Koç', 2, 'ece.koc@std.uni.edu.tr', 2022, 2),
        (22, 'Yiğit', 'Öztürk', 1, 'yigit.ozturk@std.uni.edu.tr', 2021, 4),
        (23, 'Başak', 'Ay', 4, 'basak.ay@std.uni.edu.tr', 2022, 5),
        (24, 'Kaan', 'Taş', 5, 'kaan.tas@std.uni.edu.tr', 2022, 9),
        (25, 'Sinem', 'Yıldırım', 5, 'sinem.yildirim@std.uni.edu.tr', 2021, 8)
    ])

    cur.executemany('INSERT INTO dersler VALUES (?,?,?,?,?)', [
        (1, 'Yapay Zeka', 1, 1, 6),
        (2, 'Algoritma ve Veri Yapıları', 1, 4, 7),
        (3, 'Nesne Yönelimli Programlama', 2, 6, 5),
        (4, 'Web Programlama', 2, 2, 6),
        (5, 'Devre Teorisi', 3, 3, 6),
        (6, 'Sinyaller ve Sistemler', 3, 7, 7),
        (7, 'Statik', 4, 5, 5),
        (8, 'Yöneylem Araştırması', 4, 10, 7),
        (9, 'Derin Öğrenme', 5, 9, 7),
        (10, 'Doğal Dil İşleme', 5, 8, 6),
        (11, 'Veritabanı Yönetim Sistemleri', 1, 1, 5),
        (12, 'Yazılım Mühendisliği Temelleri', 2, 2, 6)
    ])

    raw_notlar = [
        (1, 1, 78, 88), (1, 2, 55, 49), (1, 11, 80, 85),
        (2, 3, 90, 95), (2, 4, 85, 78), (2, 12, 75, 80),
        (3, 1, 70, 75), (3, 2, 40, 35), (3, 11, 62, 58),
        (4, 5, 60, 65), (4, 6, 55, 50),
        (5, 1, 85, 90), (5, 2, 66, 70), (5, 11, 92, 95),
        (6, 3, 65, 70), (6, 4, 45, 40), (6, 12, 58, 62),
        (7, 7, 80, 78), (7, 8, 72, 68),
        (8, 7, 55, 48), (8, 8, 88, 92),
        (9, 3, 82, 85), (9, 4, 90, 88), (9, 12, 76, 72),
        (10, 1, 60, 55), (10, 2, 88, 91), (10, 11, 70, 72),
        (11, 5, 95, 98), (11, 6, 88, 90),
        (12, 7, 50, 45), (12, 8, 62, 58),
        (13, 3, 82, 86), (13, 4, 78, 80), (13, 12, 85, 88),
        (14, 7, 68, 72), (14, 8, 55, 60),
        (15, 1, 88, 92), (15, 2, 75, 78), (15, 11, 95, 97),
        (16, 9, 85, 90), (16, 10, 75, 70),
        (17, 9, 90, 92), (17, 10, 80, 85),
        (18, 9, 45, 52), (18, 10, 60, 58),
        (19, 5, 72, 76), (19, 6, 68, 70),
        (20, 5, 55, 48), (20, 6, 82, 80),
        (21, 3, 88, 85), (21, 4, 92, 95), (21, 12, 80, 82),
        (22, 1, 90, 92), (22, 2, 82, 85), (22, 11, 88, 90),
        (23, 7, 74, 78), (23, 8, 70, 72),
        (24, 9, 88, 85), (24, 10, 90, 92),
        (25, 9, 78, 82), (25, 10, 85, 88)
    ]

    notlar_data = []
    for idx, (oid, did, vize, final) in enumerate(raw_notlar, start=1):
        ortalama = vize * 0.4 + final * 0.6
        if ortalama >= 90: hn = 'AA'
        elif ortalama >= 85: hn = 'BA'
        elif ortalama >= 80: hn = 'BB'
        elif ortalama >= 75: hn = 'CB'
        elif ortalama >= 70: hn = 'CC'
        elif ortalama >= 60: hn = 'DC'
        elif ortalama >= 50: hn = 'DD'
        elif ortalama >= 40: hn = 'FD'
        else: hn = 'FF'
        bd = 'Geçti' if ortalama >= 50 else 'Kaldı'
        notlar_data.append((idx, oid, did, vize, final, round(ortalama, 2), hn, bd))

    cur.executemany('INSERT INTO notlar VALUES (?,?,?,?,?,?,?,?)', notlar_data)

    cur.executemany('INSERT INTO projeler VALUES (?,?,?,?,?)', [
        (1, "LLM Tabanlı Akademik Asistan", "Doğal Dil İşleme (NLP) ve RAG Mimarileri", 1, 1),
        (2, "Otonom Sürüş için Yapay Zeka Tabanlı Yol Tespiti", "Bilgisayarlı Görü ve Derin Öğrenme", 2, 2),
        (3, "Mikroservis Mimarisi ile E-Ticaret", "Yazılım Tasarımı ve Dağıtık Sistemler", 6, 6),
        (4, "IoT Tabanlı Akıllı Sera Sistemi", "Sensör Ağları ve Mikrodenetleyiciler", 4, 3),
        (5, "Veri Analitiği ile Müşteri Segmentasyonu", "Makine Öğrenmesi ve Kümeleme", 7, 5),
        (6, "Derin Öğrenme ile Tıbbi Görüntü Analizi", "Yapay Zeka Destekli CNN ve Medikal Görüntüleme", 17, 9),
        (7, "Transformatör Modelleri ile Türkçe Soru-Cevap", "BERT ve NLP Model İnce Ayar", 16, 8),
        (8, "Enerji Tüketimi Tahmini", "Zaman Serisi Analizi ve Regresyon", 11, 7)
    ])

    conn.commit()
    conn.close()
    print('✅ Zenginleştirilmiş Demo DB kuruldu.')
