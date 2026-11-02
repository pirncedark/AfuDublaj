"""Update check, download and silent install (stdlib only).

The public API is frozen in AFULINGO_ORTAK.md; keep the signatures stable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

from afudublaj import UPDATE_REPO, __version__

API_URL = f'https://api.github.com/repos/{UPDATE_REPO}/releases/latest'
ZAMAN_ASIMI = 15
USER_AGENT = 'AfuDublaj-Updater'

GUNCELLEME_DIR = None  # set lazily below (imports paths only when needed)
AYAR_DOSYASI = None

VARSAYILAN_AYAR = {
    'acilista_kontrol': True,
    'bekleyen_zip': None,
    'bekleyen_surum': None,
}

_TAG_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z._-]+)?$')


class GuncellemeHatasi(Exception):
    """Güncelleme indirme/kurulum hatası (kullanıcıya tek cümle)."""


def _dizinler():
    from afudublaj.core.paths import APP_DATA_DIR, CONFIG_DIR
    return APP_DATA_DIR / 'guncelleme', CONFIG_DIR / 'guncelleme.json'


def _guncelleme_dizini() -> Path:
    global GUNCELLEME_DIR
    if GUNCELLEME_DIR is None:
        GUNCELLEME_DIR, _ = _dizinler()
    return Path(GUNCELLEME_DIR)


def _ayar_dosyasi() -> Path:
    global AYAR_DOSYASI
    if AYAR_DOSYASI is None:
        _, AYAR_DOSYASI = _dizinler()
    return Path(AYAR_DOSYASI)


def mevcut_surum() -> str:
    return __version__


def surum_ayristir(tag: str) -> tuple:
    """'v2.6.0-afu' -> (2, 6, 0); geçersiz -> (0, 0, 0)."""
    eslesme = _TAG_RE.match(str(tag or '').strip())
    if not eslesme:
        return (0, 0, 0)
    return tuple(int(parca) for parca in eslesme.groups())


def daha_yeni_mi(mevcut: str, tag: str) -> bool:
    return surum_ayristir(tag) > surum_ayristir(mevcut)


def _veri_al(url: str, get=None) -> bytes:
    if get is not None:
        veri = get(url)
        return veri.encode('utf-8') if isinstance(veri, str) else bytes(veri)
    istek = urllib.request.Request(
        url,
        headers={'User-Agent': USER_AGENT, 'Accept': 'application/vnd.github+json'},
    )
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
        return yanit.read()


def kontrol_et(get=None) -> dict | None:
    """Return release info when a strictly newer numeric version exists; never raises."""
    try:
        veri = json.loads(_veri_al(API_URL, get).decode('utf-8'))
        tag = str(veri.get('tag_name') or '').strip()
        if not tag or not daha_yeni_mi(mevcut_surum(), tag):
            return None
        zip_adi = f'AfuDublaj-{tag}-windows-x64.zip'
        sha_adi = zip_adi + '.sha256'
        zip_url = None
        sha_url = None
        for varlik in veri.get('assets') or []:
            ad = str(varlik.get('name') or '')
            if ad == zip_adi:
                zip_url = varlik.get('browser_download_url') or None
            elif ad == sha_adi:
                sha_url = varlik.get('browser_download_url') or None
        return {
            'tag': tag,
            'surum': surum_ayristir(tag),
            'zip_url': zip_url,
            'sha_url': sha_url,
            'notlar': veri.get('body') or '',
        }
    except Exception:
        return None


def _sha256_dosya(yol: Path) -> str:
    ozet = hashlib.sha256()
    with open(yol, 'rb') as dosya:
        for parca in iter(lambda: dosya.read(1024 * 1024), b''):
            ozet.update(parca)
    return ozet.hexdigest()


def _zip_verisi(bilgi: dict, hedef: Path, ilerleme, get) -> None:
    if get is None:
        istek = urllib.request.Request(
            bilgi['zip_url'],
            headers={'User-Agent': USER_AGENT, 'Accept': '*/*'},
        )
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            toplam = int(yanit.headers.get('Content-Length') or 0)
            okunan = 0
            with open(hedef, 'wb') as dosya:
                for parca in iter(lambda: yanit.read(65536), b''):
                    dosya.write(parca)
                    okunan += len(parca)
                    if ilerleme is not None and toplam:
                        ilerleme(min(99, okunan * 100 // toplam))
    else:
        hedef.write_bytes(_veri_al(bilgi['zip_url'], get))
    if ilerleme is not None:
        ilerleme(100)


def indir(bilgi: dict, hedef=None, ilerleme=None, get=None) -> Path:
    """Download the release zip, verify its .sha256, return the final path.

    A partial download lives in ``<hedef>.part`` and is renamed on success.
    Verification failure deletes the archive and raises GuncellemeHatasi.
    """
    onek = 'https://github.com/' + UPDATE_REPO + '/releases/download/'
    if not bilgi or not str(bilgi.get('zip_url') or '').startswith(onek) or not str(bilgi.get('sha_url') or '').startswith(onek):
        raise GuncellemeHatasi('Update file could not be found.')
    tag = bilgi.get('tag') or 'latest'
    if hedef is None:
        hedef = _guncelleme_dizini() / f'AfuDublaj-{tag}-windows-x64.zip'
    hedef = Path(hedef)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = Path(str(hedef) + '.part')

    def temizle():
        for yol in (gecici, hedef):
            try:
                yol.unlink()
            except FileNotFoundError:
                pass

    try:
        _zip_verisi(bilgi, gecici, ilerleme, get)
        if not bilgi.get('sha_url'):
            raise GuncellemeHatasi('Update file could not be verified.')
        sha_metni = _veri_al(bilgi['sha_url'], get).decode('utf-8', 'replace').strip()
        parcalar = sha_metni.split()
        beklenen = parcalar[0].lower() if parcalar else ''
        if len(beklenen) != 64 or _sha256_dosya(gecici) != beklenen:
            raise GuncellemeHatasi('Update file could not be verified.')
        os.replace(gecici, hedef)
        return hedef
    except GuncellemeHatasi:
        temizle()
        raise
    except Exception as hata:
        temizle()
        raise GuncellemeHatasi('Update file could not be downloaded.') from hata


def arsiv_guvenli(zip_yolu: Path) -> bool:
    """False when any archive member would escape the extraction directory (zip-slip)."""
    try:
        kok = os.path.abspath(str(zip_yolu.parent))
        with zipfile.ZipFile(zip_yolu) as arsiv:
            for ad in arsiv.namelist():
                hedef = os.path.abspath(os.path.join(kok, ad))
                if hedef != kok and not hedef.startswith(kok + os.sep):
                    return False
        return True
    except Exception:
        return False


_KURUCU_BETIGI = r'''param(
    [Parameter(Mandatory=$true)][string]$AppDir,
    [Parameter(Mandatory=$true)][string]$ZipPath,
    [Parameter(Mandatory=$true)][string]$ExeName,
    [Parameter(Mandatory=$true)][int]$AppPid
)
$ErrorActionPreference = 'Stop'
$bekle = 0
while ((Get-Process -Id $AppPid -ErrorAction SilentlyContinue) -and $bekle -lt 120) {
    Start-Sleep -Seconds 1
    $bekle++
}
$tmp = Join-Path $env:TEMP ('AfuDublaj_' + [Guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $kok = [IO.Path]::GetFullPath($tmp)
    $kokAyrac = $kok + [IO.Path]::DirectorySeparatorChar
    $arsiv = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($girdi in $arsiv.Entries) {
            $hedef = [IO.Path]::GetFullPath([IO.Path]::Combine($tmp, $girdi.FullName))
            if (($hedef -ne $kok) -and (-not $hedef.StartsWith($kokAyrac, [StringComparison]::OrdinalIgnoreCase))) {
                throw 'Gecersiz arsiv yolu.'
            }
        }
    } finally {
        $arsiv.Dispose()
    }
    [IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $tmp)
    $kaynak = $tmp
    $icerik = @(Get-ChildItem -LiteralPath $tmp -Force)
    if (($icerik.Count -eq 1) -and $icerik[0].PSIsContainer) {
        $kaynak = $icerik[0].FullName
    }
    $eski = $AppDir + '.eski'
    if (Test-Path -LiteralPath $eski) { Remove-Item -LiteralPath $eski -Recurse -Force }
    if (Test-Path -LiteralPath $AppDir) { Move-Item -LiteralPath $AppDir -Destination $eski -Force }
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    Copy-Item -Path (Join-Path $kaynak '*') -Destination $AppDir -Recurse -Force
    $eskiModeller = Join-Path $eski 'models'
    if (Test-Path -LiteralPath $eskiModeller) {
        Copy-Item -Path $eskiModeller -Destination (Join-Path $AppDir 'models') -Recurse -Force
    }
    $yeniExe = Join-Path $AppDir $ExeName
    $surec = $null
    try { $surec = Start-Process -FilePath $yeniExe -PassThru } catch { $surec = $null }
    Start-Sleep -Seconds 8
    if ((-not $surec) -or (-not (Get-Process -Id $surec.Id -ErrorAction SilentlyContinue))) {
        if (Test-Path -LiteralPath $AppDir) { Remove-Item -LiteralPath $AppDir -Recurse -Force }
        if (Test-Path -LiteralPath $eski) { Move-Item -LiteralPath $eski -Destination $AppDir -Force }
        Start-Process -FilePath (Join-Path $AppDir $ExeName)
    }
} finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
}
'''


def kurulum_baslat(zip_yolu: Path, uygulama_klasoru=None, exe_adi='AfuDublaj.exe') -> bool:
    """Spawn the hidden updater script. False in dev or when the archive is unsafe."""
    if not getattr(sys, 'frozen', False):
        return False
    zip_yolu = Path(zip_yolu)
    if not arsiv_guvenli(zip_yolu):
        return False
    if uygulama_klasoru is None:
        uygulama_klasoru = Path(sys.executable).parent
    uygulama_klasoru = Path(uygulama_klasoru)
    betik = _guncelleme_dizini() / 'kurucu.ps1'
    betik.parent.mkdir(parents=True, exist_ok=True)
    betik.write_text(_KURUCU_BETIGI, encoding='utf-8')
    bayraklar = 0
    if sys.platform == 'win32':
        # DETACHED_PROCESS would start powershell without a console and it silently exits (verified e2e)
        bayraklar = (
            getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x00000200)
        )
    subprocess.Popen(
        [
            'powershell', '-NoProfile', '-WindowStyle', 'Hidden',
            '-ExecutionPolicy', 'Bypass', '-File', str(betik),
            str(uygulama_klasoru), str(zip_yolu), exe_adi, str(os.getpid()),
        ],
        creationflags=bayraklar,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return True


def ayarlar() -> dict:
    varsayilan = dict(VARSAYILAN_AYAR)
    try:
        veri = json.loads(_ayar_dosyasi().read_text(encoding='utf-8'))
    except Exception:
        return varsayilan
    if not isinstance(veri, dict):
        return varsayilan
    for anahtar in varsayilan:
        if anahtar in veri:
            varsayilan[anahtar] = veri[anahtar]
    return varsayilan


def ayar_yaz(**kv) -> None:
    guncel = ayarlar()
    for anahtar, deger in kv.items():
        if anahtar in VARSAYILAN_AYAR:
            guncel[anahtar] = deger
    yol = _ayar_dosyasi()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = None
    try:
        with tempfile.NamedTemporaryFile(
            'w', encoding='utf-8', dir=str(yol.parent), delete=False,
        ) as dosya:
            gecici = Path(dosya.name)
            json.dump(guncel, dosya, indent=2, ensure_ascii=False)
        os.replace(gecici, yol)
    finally:
        if gecici is not None:
            try:
                gecici.unlink()
            except FileNotFoundError:
                pass


class ArkaPlanKontrol:
    """Qt-free background polling thread: callback(bilgi) on a new release only."""

    def __init__(self, geri_cagri, ilk_bekleme=30, aralik=6 * 3600, get=None):
        self.geri_cagri = geri_cagri
        self.ilk_bekleme = ilk_bekleme
        self.aralik = aralik
        self.get = get
        self._dur = threading.Event()
        self._thread = None
        self._son_tag = None

    def baslat(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._dur.clear()
        self._thread = threading.Thread(
            target=self._calis, name='AfuDublajGuncelleme', daemon=True,
        )
        self._thread.start()

    def durdur(self) -> None:
        self._dur.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _calis(self) -> None:
        if self._dur.wait(self.ilk_bekleme):
            return
        while not self._dur.is_set():
            bilgi = kontrol_et(self.get)
            if bilgi and bilgi.get('tag') != self._son_tag:
                self._son_tag = bilgi.get('tag')
                try:
                    self.geri_cagri(bilgi)
                except Exception:
                    pass
            if self._dur.wait(self.aralik):
                return
