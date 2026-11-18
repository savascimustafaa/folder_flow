import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
from datetime import datetime
from PIL import Image
import hashlib
import threading
import queue
import json
import sys

# Windows'un pencereyi bulanıklaştırmasını engellemek için (Windows dışında hata vermesin)
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def resource_path(relative_path):
    """ PyInstaller geçici klasöründeki dosyaların yolunu bulur """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def ayar_klasorunu_bul():
    """
    Ayarlar dosyasının kalıcı olarak saklanacağı klasörü döndürür.
    - PyInstaller (--onefile) ile paketlenmişse __file__ geçici (_MEI...) klasörü gösterir
      ve her çalıştırmada silinir; bu yüzden .exe'nin yanındaki klasör kullanılır.
    - Klasör yazılabilir değilse (ör. Program Files) AppData'ya düşülür.
    """
    if getattr(sys, "frozen", False):
        taban = os.path.dirname(sys.executable)
    else:
        taban = os.path.dirname(os.path.abspath(__file__))

    if os.access(taban, os.W_OK):
        return taban

    alternatif = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "DosyaDuzenleyici"
    )
    os.makedirs(alternatif, exist_ok=True)
    return alternatif


class DosyaDüzenleyiciApp:
    def __init__(self, fileapp):
        self.fileapp = fileapp
        self.fileapp.title("Dosya Düzenleyici")

        # --- PENCEREYİ EKRANA ORTALAMA KODLARI ---
        pencere_genislik = 1150
        pencere_yukseklik = 600

        ekran_genislik = self.fileapp.winfo_screenwidth()
        ekran_yukseklik = self.fileapp.winfo_screenheight()

        x = int((ekran_genislik / 2) - (pencere_genislik / 2))
        y = int((ekran_yukseklik / 2) - (pencere_yukseklik / 2))

        self.fileapp.geometry(f"{pencere_genislik}x{pencere_yukseklik}+{x}+{y}")
        self.fileapp.minsize(900, 500)
        self.fileapp.resizable(1, 1)

        # İkon yoksa program çökmesin
        try:
            ikon_yolu = resource_path("filediting.ico")
            self.fileapp.iconbitmap(ikon_yolu)
        except Exception:
            pass

        # ---------- RENK PALETİ (Profesyonel / Koyu-Açık) ----------
        self.renkler_koyu = {
            "bg": "#11151C",
            "panel": "#1A2230",
            "panel_alt": "#212B3D",
            "border": "#2D3A4F",
            "text": "#E8ECF2",
            "muted": "#8B97A8",
            "accent": "#3B82F6",
            "accent_hover": "#2563EB",
            "success": "#22C55E",
            "danger": "#EF4444",
            "warning": "#F59E0B",
            "info": "#38BDF8",
            "purple": "#A78BFA",
        }
        self.renkler_acik = {
            "bg": "#F3F4F6",
            "panel": "#FFFFFF",
            "panel_alt": "#F0F2F5",
            "border": "#D6DBE3",
            "text": "#1F2937",
            "muted": "#6B7280",
            "accent": "#2563EB",
            "accent_hover": "#1D4ED8",
            "success": "#16A34A",
            "danger": "#DC2626",
            "warning": "#D97706",
            "info": "#0284C7",
            "purple": "#7C3AED",
        }

        self.tema_dosyasi = os.path.join(ayar_klasorunu_bul(), "tema.json")
        self.su_anki_tema = self.tema_yukle()
        self.renk = self.renkler_koyu if self.su_anki_tema == "Koyu" else self.renkler_acik

        self.background = self.renk["bg"]
        self.panel_bg = self.renk["panel"]
        self.fontground = self.renk["text"]

        self.fnt = ("Segoe UI", 11)
        self.fnt_baslik = ("Segoe UI", 12, "bold")
        self.fnt_kucuk = ("Segoe UI", 9)

        self.fileapp.configure(background=self.background)

        self.uzanti_kurallari = {}
        self.tasima_gecmis = []
        self.son_konum = None

        self.videoUzantilari = {".mp4", ".avi", ".mkv", ".flv", ".mov", ".wmv"}
        self.fotografUzantilari = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".webp"}
        self.yoksayilan_dosyalar = {"desktop.ini", "thumbs.db"}

        # Arka plan iş parçacığından arayüze güvenli erişim için kuyruk
        self.ui_kuyrugu = queue.Queue()

        self.ayarlari_yükle()
        self.arayüz_oluştur()
        self._kuyruk_isle()

    # ------------------------------------------------------------------
    # İŞ PARÇACIĞI -> ARAYÜZ KÖPRÜSÜ
    # ------------------------------------------------------------------
    def _ui(self, fonksiyon, *args, **kwargs):
        """Herhangi bir iş parçacığından arayüz işlemini ana iş parçacığına sıraya koyar."""
        self.ui_kuyrugu.put((fonksiyon, args, kwargs))

    def _kuyruk_isle(self):
        try:
            while True:
                fonksiyon, args, kwargs = self.ui_kuyrugu.get_nowait()
                try:
                    fonksiyon(*args, **kwargs)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.fileapp.after(50, self._kuyruk_isle)

    # ------------------------------------------------------------------
    # LOG
    # ------------------------------------------------------------------
    def log_yaz(self, mesaj):
        """Log mesajı yazar (her iş parçacığından çağrılabilir)."""
        if threading.current_thread() is threading.main_thread():
            self._log_yaz_ui(mesaj)
        else:
            self._ui(self._log_yaz_ui, mesaj)

    def _log_yaz_ui(self, mesaj):
        self.log_ekrani.config(state=tk.NORMAL)

        # Etiket yalnızca mesajın başındaki işarete göre belirlenir
        # (dosya adında "[+]" gibi şeyler olsa bile renk karışmaz)
        baslangic = mesaj.lstrip()
        etiket = ""
        if baslangic.startswith("[+]"):
            etiket = "basari"
        elif baslangic.startswith("[-]"):
            etiket = "hata"
        elif baslangic.startswith("[*]"):
            etiket = "bilgi"
        elif baslangic.startswith("[!]"):
            etiket = "uyari"
        elif baslangic.startswith("[<-]"):
            etiket = "geri_al"

        if etiket:
            self.log_ekrani.insert(tk.END, mesaj + "\n", etiket)
        else:
            self.log_ekrani.insert(tk.END, mesaj + "\n")

        self.log_ekrani.see(tk.END)
        self.log_ekrani.config(state=tk.DISABLED)

    def _progress_ayarla(self, deger=None, maksimum=None):
        if maksimum is not None:
            self.progress["maximum"] = maksimum
        if deger is not None:
            self.progress["value"] = deger

    def _butonlari_ayarla(self, durum):
        self.btn_duzenle.config(state=durum)
        self.btn_geri_al.config(state=durum)

    # ------------------------------------------------------------------
    # KLASÖR / DOSYA YARDIMCILARI
    # ------------------------------------------------------------------
    def klasörSecme(self):
        klasör = filedialog.askdirectory()
        if klasör:
            self.entry_yol.delete(0, tk.END)
            self.entry_yol.insert(0, klasör)
            self.log_yaz(f"[*] Seçilen Klasör: {klasör}")

    def dosyaHashiniAl(self, dosyaYolu):
        hasher = hashlib.md5()
        try:
            with open(dosyaYolu, "rb") as f:
                buf = f.read(65536)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(65536)
            return hasher.hexdigest()
        except Exception:
            return None

    def dosyaTarihiniAl(self, dosyaYolu, is_image=False):
        """Dosyanın çekilme (EXIF) ya da değiştirilme tarihini döndürür."""
        if is_image:
            try:
                with Image.open(dosyaYolu) as img:
                    exif = img.getexif()
                    deger = None
                    try:
                        # 0x8769 = Exif alt dizini; 36867 = DateTimeOriginal, 36868 = DateTimeDigitized
                        ifd = exif.get_ifd(0x8769)
                        deger = ifd.get(36867) or ifd.get(36868)
                    except Exception:
                        pass
                    if not deger:
                        deger = exif.get(306)  # DateTime
                    if deger:
                        return datetime.strptime(str(deger).strip()[:19], "%Y:%m:%d %H:%M:%S")
            except Exception:
                pass

        saniye = os.path.getmtime(dosyaYolu)
        return datetime.fromtimestamp(saniye)

    @staticmethod
    def klasor_adi_temizle(ad):
        """Windows'ta klasör adında geçemeyen karakterleri temizler."""
        ad = re.sub(r'[<>:"/\\|?*]', "", ad).strip().rstrip(".")
        return ad

    @staticmethod
    def benzersiz_yol(yol):
        """Yol zaten varsa sonuna _1, _2 ... ekleyerek çakışmayan bir yol üretir."""
        if not os.path.exists(yol):
            return yol
        klasor = os.path.dirname(yol)
        isim, uz = os.path.splitext(os.path.basename(yol))
        sayac = 1
        while True:
            aday = os.path.join(klasor, f"{isim}_{sayac}{uz}")
            if not os.path.exists(aday):
                return aday
            sayac += 1

    @staticmethod
    def ayni_yol_mu(a, b):
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))

    def bos_klasorleri_sil(self, klasorler, taban):
        """
        Verilen klasörler (ve taban klasöre kadar olan üstleri) boşsa siler.
        Kullanıcının önceden var olan, işleme hiç karışmamış boş klasörlerine dokunmaz.
        """
        silinen = 0
        taban_norm = os.path.normcase(os.path.abspath(taban))
        # En derin klasörler önce
        for klasor in sorted(set(klasorler), key=lambda k: len(k), reverse=True):
            mevcut = klasor
            while True:
                mevcut_norm = os.path.normcase(os.path.abspath(mevcut))
                if mevcut_norm == taban_norm or not mevcut_norm.startswith(taban_norm):
                    break
                try:
                    if os.path.isdir(mevcut) and not os.listdir(mevcut):
                        os.rmdir(mevcut)
                        silinen += 1
                    else:
                        break
                except Exception:
                    break
                mevcut = os.path.dirname(mevcut)
        return silinen

    # ------------------------------------------------------------------
    # ANA İŞLEM
    # ------------------------------------------------------------------
    def islemBaslat(self):
        konum = self.entry_yol.get().strip()
        if not konum:
            messagebox.showwarning(
                "Hata", "Lütfen önce düzenlemek istediğiniz klasörü seçin veya bir yol girin!"
            )
            return

        konum = os.path.normpath(konum)
        if not os.path.isdir(konum):
            messagebox.showerror("Hata", "Klasör bulunamadı. Lütfen geçerli bir yol giriniz.")
            self.entry_yol.delete(0, tk.END)
            return

        alt_tara = self.alt_klasör_tara_var.get()
        self._butonlari_ayarla(tk.DISABLED)
        threading.Thread(
            target=self._tariheGöreDüzenle_wrapper, args=(konum, alt_tara), daemon=True
        ).start()

    def _tariheGöreDüzenle_wrapper(self, konum, alt_tara):
        try:
            self.tariheGöreDüzenle(konum, alt_tara)
        except Exception as e:
            self.log_yaz(f"[-] HATA: Beklenmeyen bir sorun oluştu: {e}")
        finally:
            self._ui(self._butonlari_ayarla, tk.NORMAL)

    def hedef_klasoru_belirle(self, uzanti, tamYol, kopya_mi):
        """Dosyanın gideceği (göreli) klasörü döndürür."""
        if kopya_mi:
            return "Kopya Dosyalar"

        # Kullanıcının tanımladığı kurallar önceliklidir
        if uzanti in self.uzanti_kurallari:
            ad = self.klasor_adi_temizle(self.uzanti_kurallari[uzanti])
            if ad:
                return ad

        if uzanti in self.fotografUzantilari:
            tarih = self.dosyaTarihiniAl(tamYol, is_image=True)
            return os.path.join("Fotoğraflar", tarih.strftime("%Y.%m.%d"))

        if uzanti in self.videoUzantilari:
            tarih = self.dosyaTarihiniAl(tamYol, is_image=False)
            return os.path.join("Videolar", tarih.strftime("%Y.%m"))

        # Kuralı tanımlanmamış uzantılar "Diğer" altında uzantısına göre toplanır
        temiz_uzanti = uzanti.replace(".", "").upper() if uzanti else "Uzantısız"
        temiz_uzanti = self.klasor_adi_temizle(temiz_uzanti) or "Uzantısız"
        return os.path.join("Diğer", temiz_uzanti)

    def tariheGöreDüzenle(self, konum, alt_tara):
        self.tasima_gecmis = []
        self.son_konum = konum

        dosyaSayisi = 0
        hataSayisi = 0
        kopyaSayisi = 0
        atlananSayisi = 0

        self.log_yaz("\n[*] Düzenleme işlemi başlıyor...")

        dosyaListesi = []

        if alt_tara:
            for root, dirs, files in os.walk(konum):
                for dosya in files:
                    dosyaListesi.append(os.path.join(root, dosya))
        else:
            for dosya in os.listdir(konum):
                tamYol = os.path.join(konum, dosya)
                if os.path.isfile(tamYol):
                    dosyaListesi.append(tamYol)

        # Programın kendi ayar dosyasını ve sistem dosyalarını taşıma
        dosyaListesi = [
            y for y in dosyaListesi
            if os.path.basename(y).lower() not in self.yoksayilan_dosyalar
            and not self.ayni_yol_mu(y, self.ayarlar_dosyasi)
        ]

        toplam_dosya = len(dosyaListesi)
        self._ui(self._progress_ayarla, 0, max(toplam_dosya, 1))

        # Hız için: yalnızca aynı boyutta başka dosyası olan dosyalar hash'lenir.
        # (Boyutu farklı iki dosya zaten aynı olamaz.)
        boyut_sayac = {}
        boyutlar = {}
        for y in dosyaListesi:
            try:
                b = os.path.getsize(y)
            except Exception:
                b = None
            boyutlar[y] = b
            if b:
                boyut_sayac[b] = boyut_sayac.get(b, 0) + 1

        gorulen_hashlar = set()
        kaynak_klasorler = set()

        for sira, tamYol in enumerate(dosyaListesi, start=1):
            dosya = os.path.basename(tamYol)
            uzanti = os.path.splitext(dosya)[1].lower()
            try:
                kopya_mi = False
                b = boyutlar.get(tamYol)
                # Boş (0 bayt) dosyalar birbirinin kopyası sayılmaz
                if b and boyut_sayac.get(b, 0) > 1:
                    dosya_hash = self.dosyaHashiniAl(tamYol)
                    if dosya_hash:
                        if dosya_hash in gorulen_hashlar:
                            kopya_mi = True
                        else:
                            gorulen_hashlar.add(dosya_hash)

                hedefklasörAdi = self.hedef_klasoru_belirle(uzanti, tamYol, kopya_mi)
                yeniklasör = os.path.join(konum, hedefklasörAdi)

                # Dosya zaten olması gereken klasördeyse dokunma
                # (aksi halde yeniden çalıştırınca her dosya gereksiz yere yeniden adlandırılırdı)
                if self.ayni_yol_mu(os.path.dirname(tamYol), yeniklasör):
                    atlananSayisi += 1
                    continue

                os.makedirs(yeniklasör, exist_ok=True)

                eski_tam_yol = tamYol
                yeni_tam_yol = self.benzersiz_yol(os.path.join(yeniklasör, dosya))

                shutil.move(eski_tam_yol, yeni_tam_yol)
                self.tasima_gecmis.append((eski_tam_yol, yeni_tam_yol))
                kaynak_klasorler.add(os.path.dirname(eski_tam_yol))

                if kopya_mi:
                    kopyaSayisi += 1
                    self.log_yaz(f"[!] KOPYA DOSYA: {dosya} -> Kopya Dosyalar")
                else:
                    self.log_yaz(f"[+] Taşındı: {dosya} -> {hedefklasörAdi}")
                    dosyaSayisi += 1

            except Exception as e:
                self.log_yaz(f"[-] HATA ({dosya}): {e}")
                hataSayisi += 1
            finally:
                if sira % 5 == 0 or sira == toplam_dosya:
                    self._ui(self._progress_ayarla, sira)

        self.klösörTemizleme(kaynak_klasorler, konum)

        self.log_yaz(
            f"\n[*] İşlem Tamamlandı! Toplam {dosyaSayisi} dosya düzenlendi, "
            f"{kopyaSayisi} kopya ayrıldı, {hataSayisi} hata oluştu."
        )
        self._ui(self.entry_yol.delete, 0, tk.END)
        self._ui(self._progress_ayarla, 0)

        mesaj = (
            f"Düzenleme tamamlandı!\n\nTaşınan: {dosyaSayisi}\nKopya: {kopyaSayisi}\n"
            f"Zaten yerinde: {atlananSayisi}\nHata: {hataSayisi}"
        )
        self._ui(messagebox.showinfo, "Başarılı", mesaj)

    def geri_al(self):
        if not self.tasima_gecmis:
            messagebox.showinfo("Geri Al", "Geri alınacak işlem bulunamadı.")
            return
        self.log_yaz("\n[*] Geri alma işlemi başlıyor...")

        geri_al_sayisi = 0
        hedef_klasorler = set()

        for eski_tam_yol, yeni_tam_yol in reversed(self.tasima_gecmis):
            try:
                if os.path.exists(yeni_tam_yol):
                    os.makedirs(os.path.dirname(eski_tam_yol), exist_ok=True)
                    # Orijinal yerde aynı adlı başka bir dosya varsa üzerine yazma
                    geri_yol = self.benzersiz_yol(eski_tam_yol)
                    hedef_klasorler.add(os.path.dirname(yeni_tam_yol))
                    shutil.move(yeni_tam_yol, geri_yol)
                    dosya_adi = os.path.basename(geri_yol)
                    self.log_yaz(f"[<-] Geri alındı: {dosya_adi}")
                    geri_al_sayisi += 1
            except Exception as e:
                self.log_yaz(f"[-] Geri alma hatası ({os.path.basename(eski_tam_yol)}): {e}")

        # Geri alma sonrası boşalan hedef klasörleri (Fotoğraflar/2024.05.01 gibi) temizle
        if self.son_konum:
            temizlenen = self.bos_klasorleri_sil(hedef_klasorler, self.son_konum)
            if temizlenen > 0:
                self.log_yaz(f"[*] {temizlenen} boş klasör temizlendi.")

        self.log_yaz(f"\n[*] Geri alma tamamlandı! Toplam {geri_al_sayisi} dosya geri alındı.")
        messagebox.showinfo("Geri Al", f"Geri alma tamamlandı! Toplam {geri_al_sayisi} dosya geri alındı.")

        self.tasima_gecmis = []

    def klösörTemizleme(self, kaynak_klasorler, anakonum):
        """Yalnızca bu işlem sırasında boşalan klasörleri siler."""
        temizlenen = self.bos_klasorleri_sil(kaynak_klasorler, anakonum)
        if temizlenen > 0:
            self.log_yaz(f"\n[*] Temizleme tamamlandı! Toplam {temizlenen} boş klasör silindi.")

    # ------------------------------------------------------------------
    # AYARLAR (uzantı -> klasör kuralları)
    # ------------------------------------------------------------------
    def ayarlari_yükle(self):
        # Ayarlar dosyası programın (veya .exe'nin) bulunduğu kalıcı klasöre sabitlenir.
        self.ayarlar_dosyasi = os.path.join(ayar_klasorunu_bul(), "ayarlar.json")

        if not os.path.exists(self.ayarlar_dosyasi):
            varsayılan_ayarlar = {
                ".pdf": "PDF Dosyaları",
                ".doc": "Word Dosyaları", ".docx": "Word Dosyaları",
                ".xls": "Excel Dosyaları", ".xlsx": "Excel Dosyaları", ".csv": "Excel Dosyaları",
                ".ppt": "PowerPoint Dosyaları", ".pptx": "PowerPoint Dosyaları",
                ".txt": "Metin Dosyaları", ".odt": "OpenDocument Dosyaları", ".rtf": "Zengin Metin Dosyaları",
                ".zip": "Sıkıştırılmış Dosyalar", ".rar": "Sıkıştırılmış Dosyalar", ".7z": "Sıkıştırılmış Dosyalar",
                ".exe": "Kurulum Dosyaları", ".msi": "Kurulum Dosyaları", ".apk": "Kurulum Dosyaları",
                ".py": "Kod Dosyaları", ".js": "Kod Dosyaları", ".html": "Kod Dosyaları", ".css": "Kod Dosyaları",
                ".mp3": "Müzik Dosyaları", ".wav": "Müzik Dosyaları", ".flac": "Müzik Dosyaları",
            }
            try:
                with open(self.ayarlar_dosyasi, "w", encoding="utf-8") as f:
                    json.dump(varsayılan_ayarlar, f, ensure_ascii=False, indent=4)
            except Exception:
                pass
            self.uzanti_kurallari = dict(varsayılan_ayarlar)
            return

        try:
            with open(self.ayarlar_dosyasi, "r", encoding="utf-8") as f:
                veri = json.load(f)
            if not isinstance(veri, dict):
                raise ValueError("Geçersiz ayar formatı")
            # Anahtarları normalize et (küçük harf + baştaki nokta)
            self.uzanti_kurallari = {}
            for k, v in veri.items():
                k = str(k).strip().lower()
                if not k.startswith("."):
                    k = "." + k
                self.uzanti_kurallari[k] = str(v)
        except Exception:
            # Bozuk dosyayı yedekle ki bir sonraki kayıtta tüm kurallar sessizce silinmesin
            try:
                shutil.copy2(self.ayarlar_dosyasi, self.ayarlar_dosyasi + ".bak")
            except Exception:
                pass
            self.uzanti_kurallari = {}

    def _ayarlari_diske_yaz(self):
        with open(self.ayarlar_dosyasi, "w", encoding="utf-8") as f:
            json.dump(self.uzanti_kurallari, f, ensure_ascii=False, indent=4)

    def ayarlari_kaydet(self, yeni_uzanti, yeni_klasör):
        yeni_uzanti = yeni_uzanti.strip().lower().replace(" ", "")
        if not yeni_uzanti.startswith("."):
            yeni_uzanti = "." + yeni_uzanti

        yeni_klasör = self.klasor_adi_temizle(yeni_klasör)
        if len(yeni_uzanti) < 2 or not yeni_klasör:
            messagebox.showwarning(
                "Geçersiz Değer",
                "Uzantı ya da klasör adı geçersiz.\nKlasör adında \\ / : * ? \" < > | karakterleri kullanılamaz.",
                parent=getattr(self, "ayar_penceresi", None),
            )
            return False

        self.uzanti_kurallari[yeni_uzanti] = yeni_klasör
        try:
            self._ayarlari_diske_yaz()
            return True
        except Exception as e:
            messagebox.showerror("Hata", f"Kural kaydedilemedi:\n{e}")
            return False

    def kural_sil(self, uzanti):
        if uzanti in self.uzanti_kurallari:
            del self.uzanti_kurallari[uzanti]
            try:
                self._ayarlari_diske_yaz()
            except Exception as e:
                messagebox.showerror("Hata", f"Kural silinemedi:\n{e}")

    def ayarlar_penceresi_ac(self):
        r = self.renk
        self.ayar_penceresi = tk.Toplevel(self.fileapp)
        self.ayar_penceresi.title("Ayarlar ve Kurallar")

        pencere_genislik = 580
        pencere_yukseklik = 600

        ekran_genislik = self.ayar_penceresi.winfo_screenwidth()
        ekran_yukseklik = self.ayar_penceresi.winfo_screenheight()

        x = int((ekran_genislik / 2) - (pencere_genislik / 2))
        y = int((ekran_yukseklik / 2) - (pencere_yukseklik / 2))

        self.ayar_penceresi.geometry(f"{pencere_genislik}x{pencere_yukseklik}+{x}+{y}")
        self.ayar_penceresi.minsize(480, 350)
        self.ayar_penceresi.configure(bg=r["bg"])
        self.ayar_penceresi.resizable(1, 1)
        self.ayar_penceresi.grab_set()

        # --- Tüm pencere içeriğini dikey kaydırılabilir yapan dış iskelet ---
        dis_canvas = tk.Canvas(self.ayar_penceresi, bg=r["bg"], highlightthickness=0)
        dis_scrollbar = ttk.Scrollbar(self.ayar_penceresi, orient="vertical", command=dis_canvas.yview)
        dis_canvas.configure(yscrollcommand=dis_scrollbar.set)

        dis_canvas.pack(side="left", fill="both", expand=True)
        dis_scrollbar.pack(side="right", fill="y")

        ic_govde = tk.Frame(dis_canvas, bg=r["bg"])
        govde_pencere_id = dis_canvas.create_window((0, 0), window=ic_govde, anchor="nw")

        def govde_boyut_guncelle(event=None):
            dis_canvas.configure(scrollregion=dis_canvas.bbox("all"))

        def canvas_genislik_guncelle(event):
            dis_canvas.itemconfig(govde_pencere_id, width=event.width)

        ic_govde.bind("<Configure>", govde_boyut_guncelle)
        dis_canvas.bind("<Configure>", canvas_genislik_guncelle)

        def _mousewheel(event):
            delta = -1 * (event.delta // 120) if event.delta else (-1 if event.num == 4 else 1)
            dis_canvas.yview_scroll(int(delta), "units")

        dis_canvas.bind_all("<MouseWheel>", _mousewheel)
        dis_canvas.bind_all("<Button-4>", _mousewheel)
        dis_canvas.bind_all("<Button-5>", _mousewheel)

        def pencere_kapanirken():
            dis_canvas.unbind_all("<MouseWheel>")
            dis_canvas.unbind_all("<Button-4>")
            dis_canvas.unbind_all("<Button-5>")
            self.ayar_penceresi.destroy()

        self.ayar_penceresi.protocol("WM_DELETE_WINDOW", pencere_kapanirken)

        # --- Başlık + Tema butonu ---
        ust = tk.Frame(ic_govde, bg=r["bg"])
        ust.pack(fill=tk.X, padx=20, pady=(18, 5))

        tk.Label(
            ust, text="Ayarlar ve Kurallar", font=("Segoe UI", 14, "bold"),
            bg=r["bg"], fg=r["text"]
        ).pack(side=tk.LEFT)

        tema_metni = "☀️ Açık Tema" if self.su_anki_tema == "Koyu" else "🌙 Koyu Tema"

        def yerel_tema_degistir():
            self.tema_buton_tetikle()
            pencere_kapanirken()
            self.ayarlar_penceresi_ac()

        btn_ayar_tema = tk.Button(
            ust, text=tema_metni, command=yerel_tema_degistir, font=("Segoe UI", 9, "bold"),
            fg="white", bg=r["accent"], activebackground=r["accent_hover"], activeforeground="white",
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        btn_ayar_tema.pack(side=tk.RIGHT)

        tk.Frame(ic_govde, height=1, bg=r["border"]).pack(fill=tk.X, padx=20, pady=(8, 12))

        # --- Mevcut kurallar listesi ---
        tk.Label(
            ic_govde, text="Mevcut Kurallar (uzantı → klasör)",
            bg=r["bg"], fg=r["muted"], font=self.fnt_kucuk
        ).pack(anchor="w", padx=20)

        liste_cerceve = tk.Frame(ic_govde, bg=r["panel"], highlightbackground=r["border"], highlightthickness=1)
        liste_cerceve.pack(fill=tk.BOTH, expand=True, padx=20, pady=(5, 15))

        self.kural_listesi_frame = tk.Frame(liste_cerceve, bg=r["panel"])
        self.kural_listesi_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._kural_listesini_doldur()

        # --- Yeni kural ekleme bölümü ---
        ekle_frame = tk.Frame(ic_govde, bg=r["panel_alt"], highlightbackground=r["border"], highlightthickness=1)
        ekle_frame.pack(fill=tk.X, padx=20, pady=(0, 18))

        ic = tk.Frame(ekle_frame, bg=r["panel_alt"])
        ic.pack(fill=tk.X, padx=15, pady=12)

        tk.Label(ic, text="Yeni Kural Ekle", font=("Segoe UI", 10, "bold"), bg=r["panel_alt"], fg=r["text"]).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        tk.Label(ic, text="Uzantı (örn: .psd)", bg=r["panel_alt"], fg=r["muted"], font=self.fnt_kucuk).grid(
            row=1, column=0, sticky="w"
        )
        tk.Label(ic, text="Hedef Klasör (örn: Tasarım)", bg=r["panel_alt"], fg=r["muted"], font=self.fnt_kucuk).grid(
            row=1, column=1, sticky="w"
        )

        entry_uzanti = tk.Entry(ic, font=self.fnt, bg=r["panel"], fg=r["text"], insertbackground=r["text"], relief="flat")
        entry_uzanti.grid(row=2, column=0, sticky="ew", padx=(0, 8), ipady=4)

        entry_klasor = tk.Entry(ic, font=self.fnt, bg=r["panel"], fg=r["text"], insertbackground=r["text"], relief="flat")
        entry_klasor.grid(row=2, column=1, sticky="ew", ipady=4)

        ic.grid_columnconfigure(0, weight=1)
        ic.grid_columnconfigure(1, weight=1)

        def kaydet_ve_temizle():
            uzt = entry_uzanti.get().strip()
            kls = entry_klasor.get().strip()
            if not uzt or not kls:
                messagebox.showwarning("Eksik Bilgi", "Lütfen hem uzantı hem de klasör adı girin.", parent=self.ayar_penceresi)
                return
            if self.ayarlari_kaydet(uzt, kls):
                entry_uzanti.delete(0, tk.END)
                entry_klasor.delete(0, tk.END)
                self._kural_listesini_doldur()
                self.log_yaz(f"[*] Yeni kural eklendi: {uzt} -> {kls}")

        btn_kaydet = tk.Button(
            ic, text="+ Kuralı Ekle", command=kaydet_ve_temizle, font=("Segoe UI", 10, "bold"),
            bg=r["success"], fg="white", relief="flat", padx=15, pady=6, cursor="hand2"
        )
        btn_kaydet.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _kural_listesini_doldur(self):
        r = self.renk
        for widget in self.kural_listesi_frame.winfo_children():
            widget.destroy()

        if not self.uzanti_kurallari:
            tk.Label(
                self.kural_listesi_frame, text="Henüz tanımlı kural yok.",
                bg=r["panel"], fg=r["muted"], font=self.fnt_kucuk
            ).pack(pady=10)
            return

        for uzanti, klasör in sorted(self.uzanti_kurallari.items()):
            satir = tk.Frame(self.kural_listesi_frame, bg=r["panel_alt"])
            satir.pack(fill=tk.X, padx=8, pady=3)

            tk.Label(
                satir, text=uzanti, font=("Consolas", 10, "bold"), bg=r["panel_alt"],
                fg=r["accent"], width=10, anchor="w"
            ).pack(side=tk.LEFT, padx=(8, 0), pady=6)

            tk.Label(
                satir, text="→", bg=r["panel_alt"], fg=r["muted"]
            ).pack(side=tk.LEFT, padx=5)

            tk.Label(
                satir, text=klasör, font=self.fnt_kucuk, bg=r["panel_alt"], fg=r["text"], anchor="w"
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

            def yap_sil(u=uzanti):
                if messagebox.askyesno("Kuralı Sil", f"'{u}' kuralı silinsin mi?", parent=self.ayar_penceresi):
                    self.kural_sil(u)
                    self._kural_listesini_doldur()
                    self.log_yaz(f"[!] Kural silindi: {u}")

            tk.Button(
                satir, text="✕", command=yap_sil, font=("Segoe UI", 9, "bold"),
                bg=r["panel_alt"], fg=r["danger"], activebackground=r["border"],
                relief="flat", padx=8, cursor="hand2", bd=0
            ).pack(side=tk.RIGHT, padx=8)

    # ------------------------------------------------------------------
    # TEMA
    # ------------------------------------------------------------------
    def tema_degistir(self, tema):
        self.renk = self.renkler_koyu if tema == "Koyu" else self.renkler_acik
        r = self.renk

        self.background = r["bg"]
        self.panel_bg = r["panel"]
        self.fontground = r["text"]

        self.fileapp.configure(background=self.background)
        self.ust_frame.configure(bg=self.background)
        self.alt_araclar_frame.configure(bg=self.background)
        self.alt_frame.configure(bg=self.background)
        self.baslik_frame.configure(bg=self.background)

        self.lbl_baslik.configure(bg=self.background, fg=r["text"])
        self.lbl_alt_baslik.configure(bg=self.background, fg=r["muted"])
        self.lbl_bilgi.configure(bg=self.background, fg=self.fontground)
        self.lbl_log.configure(bg=self.background, fg=self.fontground)

        self.giris_cercevesi.configure(bg=r["panel"], highlightbackground=r["border"])
        self.entry_yol.configure(bg=r["panel"], fg=self.fontground, insertbackground=self.fontground)

        self.chk_alt_klasor.configure(
            bg=self.background, fg=self.fontground, selectcolor=r["panel"],
            activebackground=self.background, activeforeground=self.fontground
        )

        self.btn_sec.configure(
            bg=r["panel_alt"], fg=r["text"], activebackground=r["border"], activeforeground=r["text"]
        )
        self.btn_geri_al.configure(
            bg=r["danger"], fg="white", activebackground=r["danger"], activeforeground="white"
        )
        self.btn_ayarlar.configure(
            bg=r["panel_alt"], fg=r["text"], activebackground=r["border"], activeforeground=r["text"]
        )
        self.btn_duzenle.configure(
            bg=r["accent"], fg="white", activebackground=r["accent_hover"], activeforeground="white"
        )

        self.log_cerceve.configure(bg=r["panel"], highlightbackground=r["border"])
        self.log_ekrani.configure(bg=r["panel"], fg=self.fontground)

        # Log renk etiketleri de temaya göre güncellenmeli (önceden güncellenmiyordu)
        self._log_etiketlerini_ayarla()

        stil = ttk.Style()
        stil.theme_use("default")
        stil.configure(
            "TProgressbar", troughcolor=r["panel_alt"], background=r["accent"],
            bordercolor=r["panel_alt"], lightcolor=r["accent"], darkcolor=r["accent"]
        )

    def _log_etiketlerini_ayarla(self):
        r = self.renk
        self.log_ekrani.tag_config("basari", foreground=r["success"])
        self.log_ekrani.tag_config("hata", foreground=r["danger"])
        self.log_ekrani.tag_config("bilgi", foreground=r["info"])
        self.log_ekrani.tag_config("uyari", foreground=r["warning"])
        self.log_ekrani.tag_config("geri_al", foreground=r["purple"])

    def tema_yukle(self):
        """Kaydedilmiş temayı okur; dosya yoksa ya da bozuksa Koyu döner."""
        try:
            with open(self.tema_dosyasi, "r", encoding="utf-8") as f:
                tema = json.load(f).get("tema")
                return tema if tema in ("Koyu", "Açık") else "Koyu"
        except Exception:
            return "Koyu"

    def tema_kaydet(self):
        try:
            with open(self.tema_dosyasi, "w", encoding="utf-8") as f:
                json.dump({"tema": self.su_anki_tema}, f, ensure_ascii=False)
        except Exception:
            pass

    def tema_buton_tetikle(self):
        self.su_anki_tema = "Açık" if self.su_anki_tema == "Koyu" else "Koyu"
        self.tema_degistir(self.su_anki_tema)
        self.tema_kaydet()

    # ------------------------------------------------------------------
    # ARAYÜZ
    # ------------------------------------------------------------------
    def arayüz_oluştur(self):
        r = self.renk

        # --- Başlık ---
        self.baslik_frame = tk.Frame(self.fileapp, bg=self.background)
        self.baslik_frame.pack(fill=tk.X, padx=20, pady=(18, 0))

        self.lbl_baslik = tk.Label(
            self.baslik_frame, text="📁 Dosya Düzenleyici", font=("Segoe UI", 18, "bold"),
            fg=self.fontground, bg=self.background
        )
        self.lbl_baslik.pack(anchor="w")

        self.lbl_alt_baslik = tk.Label(
            self.baslik_frame, text="Klasörünüzü tarayın, dosyaları türüne ve tarihine göre otomatik düzenleyin.",
            font=self.fnt_kucuk, fg=r["muted"], bg=self.background
        )
        self.lbl_alt_baslik.pack(anchor="w", pady=(2, 0))

        # --- Üst Panel (Giriş ve Butonlar) ---
        self.ust_frame = tk.Frame(self.fileapp, bg=self.background)
        self.ust_frame.pack(pady=15, padx=20, fill=tk.X)

        self.lbl_bilgi = tk.Label(
            self.ust_frame, text="Düzenlenecek Klasör Yolu:", font=self.fnt,
            fg=self.fontground, bg=self.background
        )
        self.lbl_bilgi.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self.giris_cercevesi = tk.Frame(self.ust_frame, bg=r["panel"], highlightbackground=r["border"], highlightthickness=1)
        self.giris_cercevesi.grid(row=1, column=0, rowspan=2, padx=(0, 15), sticky="nsew")

        self.entry_yol = tk.Entry(
            self.giris_cercevesi, width=55, font=self.fnt, bg=r["panel"], fg=self.fontground,
            insertbackground=self.fontground, relief="flat", bd=0
        )
        self.entry_yol.pack(fill=tk.BOTH, expand=True, padx=10, ipady=8)

        self.btn_sec = tk.Button(
            self.ust_frame, text="🔎 Klasör Seç", command=self.klasörSecme, font=self.fnt,
            fg=r["text"], bg=r["panel_alt"], activebackground=r["border"], activeforeground=r["text"],
            relief="flat", cursor="hand2"
        )
        self.btn_sec.grid(row=2, column=1, padx=5, pady=(0, 5), sticky="ew")

        self.btn_duzenle = tk.Button(
            self.ust_frame, text="🛠️ Düzenle", command=self.islemBaslat, font=self.fnt,
            fg="white", bg=r["accent"], activebackground=r["accent_hover"], activeforeground="white",
            relief="flat", cursor="hand2"
        )
        self.btn_duzenle.grid(row=2, column=2, padx=5, pady=(0, 5), sticky="ew")

        self.btn_geri_al = tk.Button(
            self.ust_frame, text="🔄️ Geri Al", command=self.geri_al, font=self.fnt,
            fg="white", bg=r["danger"], activebackground=r["danger"], activeforeground="white",
            relief="flat", cursor="hand2"
        )
        self.btn_geri_al.grid(row=0, column=1, padx=5, pady=(0, 5), sticky="ew")

        self.btn_ayarlar = tk.Button(
            self.ust_frame, text="⚙️ Ayarlar", command=self.ayarlar_penceresi_ac, font=self.fnt,
            fg=r["text"], bg=r["panel_alt"], activebackground=r["border"], activeforeground=r["text"],
            relief="flat", cursor="hand2"
        )
        self.btn_ayarlar.grid(row=0, column=2, padx=5, pady=(0, 5), sticky="ew")

        self.ust_frame.grid_columnconfigure(0, weight=1)

        # --- Alt araçlar (checkbox + progressbar) ---
        self.alt_araclar_frame = tk.Frame(self.ust_frame, bg=self.background)
        self.alt_araclar_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(20, 0))

        self.alt_klasör_tara_var = tk.BooleanVar(value=False)
        self.chk_alt_klasor = tk.Checkbutton(
            self.alt_araclar_frame, text="Alt Klasörleri Tara", variable=self.alt_klasör_tara_var,
            font=self.fnt, fg=self.fontground, bg=self.background, selectcolor=r["panel"],
            activebackground=self.background, activeforeground=self.fontground, cursor="hand2"
        )
        self.chk_alt_klasor.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(self.alt_araclar_frame, orient=tk.HORIZONTAL, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(30, 0), ipady=4)

        self.entry_yol.focus()

        # --- Log Ekranı ---
        self.alt_frame = tk.Frame(self.fileapp, bg=self.background)
        self.alt_frame.pack(padx=20, pady=(5, 20), fill=tk.BOTH, expand=True)

        self.lbl_log = tk.Label(
            self.alt_frame, text="İşlem Geçmişi ve Hatalar:", font=self.fnt,
            fg=self.fontground, bg=self.background
        )
        self.lbl_log.pack(anchor="w", pady=(0, 5))

        self.log_cerceve = tk.Frame(self.alt_frame, bg=r["panel"], highlightbackground=r["border"], highlightthickness=1)
        self.log_cerceve.pack(fill=tk.BOTH, expand=True)

        self.log_ekrani = scrolledtext.ScrolledText(
            self.log_cerceve, wrap=tk.WORD, font=("Consolas", 10), bg=r["panel"], fg=self.fontground,
            state=tk.DISABLED, relief="flat", borderwidth=12
        )
        self.log_ekrani.pack(fill=tk.BOTH, expand=True)

        self._log_etiketlerini_ayarla()

        # ttk progressbar stilini başlangıçta da uygula
        stil = ttk.Style()
        stil.theme_use("default")
        stil.configure(
            "TProgressbar", troughcolor=r["panel_alt"], background=r["accent"],
            bordercolor=r["panel_alt"], lightcolor=r["accent"], darkcolor=r["accent"]
        )

        self.log_yaz("[*] Sistem hazır. Lütfen bir klasör seçin.")


if __name__ == "__main__":
    fileapp = tk.Tk()
    app = DosyaDüzenleyiciApp(fileapp)
    fileapp.mainloop()