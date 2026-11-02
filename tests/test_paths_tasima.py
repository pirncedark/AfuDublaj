"""Veri klasörü AfuDublaj'a taşınır; eski Lingolay klasörü varsa içeriğiyle birlikte aktarılır."""
from afudublaj.core import paths


def test_eski_klasor_tasinir(tmp_path):
    eski = tmp_path / 'Lingolay'
    (eski / 'config').mkdir(parents=True)
    (eski / 'config' / 'settings.json').write_text('{"a": 1}', encoding='utf-8')
    yeni = paths._migrate_legacy(tmp_path)
    assert yeni == tmp_path / 'AfuDublaj'
    assert (yeni / 'config' / 'settings.json').read_text(encoding='utf-8') == '{"a": 1}'
    assert not eski.exists()


def test_yeni_klasor_varsa_dokunulmaz(tmp_path):
    (tmp_path / 'Lingolay').mkdir()
    (tmp_path / 'AfuDublaj').mkdir()
    assert paths._migrate_legacy(tmp_path) == tmp_path / 'AfuDublaj'
    assert (tmp_path / 'Lingolay').exists()


def test_tasima_olmazsa_eski_kullanilir(tmp_path, monkeypatch):
    (tmp_path / 'Lingolay').mkdir()
    from pathlib import Path

    def hata(self, hedef):
        raise PermissionError('kilitli')
    monkeypatch.setattr(Path, 'rename', hata)
    assert paths._migrate_legacy(tmp_path) == tmp_path / 'Lingolay'


def test_hic_klasor_yoksa_yeni_ad(tmp_path):
    assert paths._migrate_legacy(tmp_path) == tmp_path / 'AfuDublaj'
