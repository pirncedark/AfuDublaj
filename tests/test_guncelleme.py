import hashlib
import io
import json
import threading
import time
import zipfile

import pytest

from afudublaj.core import guncelleme
from afudublaj.core.guncelleme import (
    ArkaPlanKontrol,
    GuncellemeHatasi,
    daha_yeni_mi,
    indir,
    kontrol_et,
    kurulum_baslat,
    surum_ayristir,
)


@pytest.fixture(autouse=True)
def izole_dizinler(tmp_path, monkeypatch):
    monkeypatch.setattr(guncelleme, 'GUNCELLEME_DIR', tmp_path / 'guncelleme')
    monkeypatch.setattr(guncelleme, 'AYAR_DOSYASI', tmp_path / 'config' / 'guncelleme.json')
    return tmp_path


def _payload(tag, assets=None, body='Notlar'):
    return json.dumps({
        'tag_name': tag,
        'body': body,
        'assets': assets if assets is not None else [
            {
                'name': f'AfuDublaj-{tag}-windows-x64.zip',
                'browser_download_url': f'https://github.com/pirncedark/AfuDublaj/releases/download/x/{tag}.zip',
            },
            {
                'name': f'AfuDublaj-{tag}-windows-x64.zip.sha256',
                'browser_download_url': f'https://github.com/pirncedark/AfuDublaj/releases/download/x/{tag}.zip.sha256',
            },
        ],
    }).encode('utf-8')


def _zip_bytes(ad='AfuDublaj.exe', icerik=b'x'):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w') as arsiv:
        arsiv.writestr(ad, icerik)
    return tampon.getvalue()


def test_surum_ayristir_ve_karsilastirma():
    assert surum_ayristir('v2.6.0-afu') == (2, 6, 0)
    assert surum_ayristir('2.6.0') == (2, 6, 0)
    assert surum_ayristir('v2.6.0') == (2, 6, 0)
    assert surum_ayristir('gecersiz') == (0, 0, 0)
    assert surum_ayristir('') == (0, 0, 0)
    assert daha_yeni_mi('2.9.0', 'v2.10.0') is True
    assert daha_yeni_mi('2.10.0', 'v2.10.0-afu') is False
    assert daha_yeni_mi('2.6.0', 'v2.5.9') is False


def test_kontrol_et_yeni_surum():
    bilgi = kontrol_et(get=lambda _url: _payload('v2.7.0-afu', body='Yenilikler'))
    assert bilgi is not None
    assert bilgi['tag'] == 'v2.7.0-afu'
    assert bilgi['surum'] == (2, 7, 0)
    assert bilgi['zip_url'] == 'https://github.com/pirncedark/AfuDublaj/releases/download/x/v2.7.0-afu.zip'
    assert bilgi['sha_url'] == 'https://github.com/pirncedark/AfuDublaj/releases/download/x/v2.7.0-afu.zip.sha256'
    assert bilgi['notlar'] == 'Yenilikler'


def test_kontrol_et_ayni_ve_eski_surum_none():
    assert kontrol_et(get=lambda _url: _payload('v2.6.0-afu')) is None
    assert kontrol_et(get=lambda _url: _payload('v2.5.9-afu')) is None


def test_kontrol_et_gecersiz_tag_none():
    assert kontrol_et(get=lambda _url: _payload('en-son')) is None


def test_kontrol_et_asset_yoksa_urller_none():
    bilgi = kontrol_et(get=lambda _url: _payload('v3.0.0-afu', assets=[]))
    assert bilgi is not None
    assert bilgi['zip_url'] is None
    assert bilgi['sha_url'] is None


def test_kontrol_et_ag_hatasi_sessiz_none():
    def patla(_url):
        raise OSError('ag yok')

    assert kontrol_et(get=patla) is None


def test_kontrol_et_bozuk_json_none():
    assert kontrol_et(get=lambda _url: b'<html>') is None


def test_indir_dogru_sha(tmp_path):
    zip_verisi = _zip_bytes()
    sha = hashlib.sha256(zip_verisi).hexdigest()
    indirmeler = {'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip': zip_verisi,
                  'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip.sha256': f'{sha}  Afu Dublaj.zip'.encode()}
    ilerleme = []
    hedef = tmp_path / 'a.zip'
    sonuc = indir(
        {'tag': 'v3.0.0', 'zip_url': 'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip',
         'sha_url': 'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip.sha256'},
        hedef=hedef, ilerleme=ilerleme.append, get=indirmeler.__getitem__,
    )
    assert sonuc == hedef
    assert hedef.read_bytes() == zip_verisi
    assert not (tmp_path / 'a.zip.part').exists()
    assert ilerleme[-1] == 100


def test_indir_bozuk_sha_dosyayi_siler(tmp_path):
    zip_verisi = _zip_bytes()
    yanlis = hashlib.sha256(b'baska').hexdigest()
    indirmeler = {'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip': zip_verisi,
                  'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip.sha256': yanlis.encode()}
    hedef = tmp_path / 'a.zip'
    with pytest.raises(GuncellemeHatasi, match='could not be verified'):
        indir(
            {'tag': 'v3.0.0', 'zip_url': 'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip',
             'sha_url': 'https://github.com/pirncedark/AfuDublaj/releases/download/x/v3.0.0.zip.sha256'},
            hedef=hedef, get=indirmeler.__getitem__,
        )
    assert not hedef.exists()
    assert not (tmp_path / 'a.zip.part').exists()


def test_indir_sha_url_yoksa_siler(tmp_path):
    hedef = tmp_path / 'a.zip'
    with pytest.raises(GuncellemeHatasi):
        indir(
            {'tag': 'v3.0.0', 'zip_url': 'https://github.com/pirncedark/AfuDublaj/releases/download/x/a.zip', 'sha_url': None},
            hedef=hedef, get=lambda _url: _zip_bytes(),
        )
    assert not hedef.exists()


def test_ayarlar_bozuk_dosya_varsayilan(tmp_path):
    yol = guncelleme.AYAR_DOSYASI
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text('{bozuk', encoding='utf-8')
    assert guncelleme.ayarlar() == {
        'acilista_kontrol': True, 'bekleyen_zip': None, 'bekleyen_surum': None,
    }


def test_ayar_yaz_atomik_ve_okunur():
    guncelleme.ayar_yaz(acilista_kontrol=False, bekleyen_surum='v3.0.0')
    veri = json.loads(guncelleme.AYAR_DOSYASI.read_text(encoding='utf-8'))
    assert veri['acilista_kontrol'] is False
    assert veri['bekleyen_surum'] == 'v3.0.0'
    assert veri['bekleyen_zip'] is None
    assert guncelleme.ayarlar() == veri


def test_zip_slip_reddedilir(tmp_path):
    kotu = tmp_path / 'kotu.zip'
    with zipfile.ZipFile(kotu, 'w') as arsiv:
        arsiv.writestr('../../kacak.txt', b'x')
    assert guncelleme.arsiv_guvenli(kotu) is False

    iyi = tmp_path / 'iyi.zip'
    iyi.write_bytes(_zip_bytes('AfuDublaj.exe'))
    assert guncelleme.arsiv_guvenli(iyi) is True


def test_arka_plan_kontrol_tek_bildirim():
    bildirimler = []
    olay = threading.Event()

    def geri(bilgi):
        bildirimler.append(bilgi)
        olay.set()

    denetleyici = ArkaPlanKontrol(
        geri, ilk_bekleme=0, aralik=0.05,
        get=lambda _url: _payload('v9.9.9-afu'),
    )
    denetleyici.baslat()
    assert olay.wait(2)
    time.sleep(0.3)
    denetleyici.durdur()
    assert len(bildirimler) == 1
    assert bildirimler[0]['tag'] == 'v9.9.9-afu'


def test_arka_plan_kontrol_geri_cagri_hatasi_thread_oldurmez():
    bildirimler = []

    def geri(bilgi):
        bildirimler.append(bilgi)
        raise RuntimeError('ui hatasi')

    denetleyici = ArkaPlanKontrol(
        geri, ilk_bekleme=0, aralik=0.05,
        get=lambda _url: _payload('v9.9.9-afu'),
    )
    denetleyici.baslat()
    time.sleep(0.3)
    denetleyici.durdur()
    assert bildirimler


def test_kurulum_baslat_frozen_degilse_false(tmp_path):
    assert kurulum_baslat(tmp_path / 'a.zip') is False


def test_kurulum_baslat_betik_ve_popen(tmp_path, monkeypatch):
    import subprocess

    zip_yolu = tmp_path / 'a.zip'
    zip_yolu.write_bytes(_zip_bytes('AfuDublaj.exe'))
    uygulama = tmp_path / 'uygulama'
    uygulama.mkdir()
    cagrilar = []

    class SahtePopen:
        def __init__(self, args, **kwargs):
            cagrilar.append((args, kwargs))

    monkeypatch.setattr(guncelleme.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(guncelleme.subprocess, 'Popen', SahtePopen)

    assert kurulum_baslat(zip_yolu, uygulama_klasoru=uygulama) is True
    assert len(cagrilar) == 1
    argumanlar, secenekler = cagrilar[0]
    assert argumanlar[:5] == ['powershell', '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy']
    assert '-File' in argumanlar
    betik = guncelleme.GUNCELLEME_DIR / 'kurucu.ps1'
    assert str(betik) in argumanlar
    assert str(uygulama) in argumanlar
    assert str(zip_yolu) in argumanlar
    if guncelleme.sys.platform == 'win32':
        assert secenekler['creationflags'] & subprocess.CREATE_NO_WINDOW
        assert secenekler['creationflags'] & subprocess.CREATE_NEW_PROCESS_GROUP
        assert not secenekler['creationflags'] & subprocess.DETACHED_PROCESS

    metin = betik.read_text(encoding='utf-8')
    for parca in ('Get-Process', '120', '.eski', 'models', 'Start-Process',
                  'ZipFile', 'StartsWith', 'Start-Sleep -Seconds 8',
                  'ExtractToDirectory'):
        assert parca in metin
