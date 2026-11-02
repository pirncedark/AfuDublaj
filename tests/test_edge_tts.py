import asyncio
import io
import wave

import pytest

from lingolay.tts import edge_engine as ee
from lingolay.tts import fast_dubbing as fd


def _wav(frames=24, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b'\x01\x00' * frames)
    return buf.getvalue()


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class _FakeCommunicate:
    def __init__(self, text, voice, rate='+0%', **kwargs):
        self.text, self.voice, self.rate = text, voice, rate
        self.calls = 0
        self.delay = kwargs.pop('delay', 0.0)
        _FakeCommunicate.instances.append(self)

    instances = []

    def stream(self):
        self.calls += 1

        async def gen():
            if self.delay:
                await asyncio.sleep(self.delay)
            yield {'type': 'audio', 'data': b'fake-mp3'}

        return gen()


class _BrokenCommunicate(_FakeCommunicate):
    def stream(self):
        async def gen():
            raise OSError('network down')
            yield  # pragma: no cover

        return gen()


def _converter(data):
    return _wav()


@pytest.fixture(autouse=True)
def _edge_available(monkeypatch):
    monkeypatch.setattr(ee, 'EDGE_AVAILABLE', True)
    _FakeCommunicate.instances = []


@pytest.mark.parametrize(
    'lang, female, male',
    [
        ('tr', 'tr-TR-EmelNeural', 'tr-TR-AhmetNeural'),
        ('en', 'en-US-JennyNeural', 'en-US-GuyNeural'),
        ('de', 'de-DE-KatjaNeural', 'de-DE-ConradNeural'),
        ('ru', 'ru-RU-SvetlanaNeural', 'ru-RU-DmitryNeural'),
        ('fr', 'fr-FR-DeniseNeural', 'fr-FR-HenriNeural'),
        ('es', 'es-ES-ElviraNeural', 'es-ES-AlvaroNeural'),
        ('ar', 'ar-SA-ZariyahNeural', 'ar-SA-HamedNeural'),
        ('ja', 'ja-JP-NanamiNeural', 'ja-JP-KeitaNeural'),
        ('zh', 'zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural'),
    ],
)
def test_voice_table_picks_the_gender(lang, female, male):
    assert ee.ses_sec(lang, 'female') == female
    assert ee.ses_sec(lang, 'male') == male
    assert ee.ses_sec(f'{lang}-XX', 'kadın') == female
    assert ee.ses_sec(f'{lang}-XX', 'erkek') == male


def test_unknown_language_has_no_edge_voice():
    assert ee.ses_sec('ko', 'female') is None
    assert ee.ses_sec('', 'male') is None
    assert ee.ses_sec(None, None) is None


def test_successful_generation_runs_on_the_loop_thread_and_returns_wav():
    engine = ee.EdgeEngine(communicate=_FakeCommunicate, converter=_converter)
    wav, err = engine.synthesize('Merhaba dünya.', 'tr-TR-EmelNeural', rate='+20%')
    assert err is None and wav.startswith(b'RIFF')
    call = _FakeCommunicate.instances[0]
    assert (call.text, call.voice, call.rate) == ('Merhaba dünya.', 'tr-TR-EmelNeural', '+20%')
    assert engine._thread is not None and engine._thread.name == 'EdgeTTSLoop'
    assert engine.available


def test_network_error_opens_the_circuit_for_60_seconds():
    clock = _Clock()
    engine = ee.EdgeEngine(communicate=_BrokenCommunicate, converter=_converter, clock=clock)
    wav, err = engine.synthesize('Hola.', 'es-ES-ElviraNeural')
    assert wav is None and err
    assert not engine.available
    assert engine.disabled_for == pytest.approx(60.0)
    assert engine.synthesize('Otra.', 'es-ES-ElviraNeural')[0] is None
    assert len(_FakeCommunicate.instances) == 1  # no retry while the circuit is open
    clock.now += 61
    assert engine.available


def test_first_chunk_timeout_opens_the_circuit():
    clock = _Clock()
    engine = ee.EdgeEngine(communicate=_FakeCommunicate, converter=_converter, first_chunk_timeout=0.05, clock=clock)
    # Slow first chunk: 200 ms > the 50 ms fallback window.
    slow = lambda text, voice, rate='+0%', **kw: _FakeCommunicate(text, voice, rate=rate, delay=0.2)
    engine._communicate = slow
    wav, err = engine.synthesize('Merhaba.', 'tr-TR-EmelNeural')
    assert wav is None and 'timed out' in err
    assert not engine.available


# ── fast_dubbing integration ────────────────────────────────────────────────────

class _FakePiper:
    is_ready = True
    init_error = None

    def __init__(self):
        self.calls = []

    def synthesize(self, text, rate='+35%', speaker_id=None, sentence_pause_ms=0):
        self.calls.append((text, rate, speaker_id))
        return _wav(), None


class _FakeEdge:
    def __init__(self, result=None):
        self.calls = []
        self.result = result if result is not None else (_wav(), None)

    def synthesize(self, text, voice, rate='+0%'):
        self.calls.append((text, voice, rate))
        return self.result


class _Matcher:
    def __init__(self, gender):
        self.gender = gender

    def snapshot(self):
        return 'audio'

    def decide(self, audio):
        return self.gender


def _engine(edge=None, natural=True):
    eng = fd.FastDubbingEngine(duck_enabled=False, natural_voice=natural, target_lang='tr', edge_engine=edge)
    eng._is_enabled = True
    piper = _FakePiper()
    eng._get_piper = lambda voice_key=None: piper
    return eng, piper


def test_edge_success_uses_natural_voice_and_skips_piper():
    edge = _FakeEdge()
    eng, piper = _engine(edge)
    audio = eng._synthesize_text('Merhaba.', None, None, None, '+35%', 0)
    assert audio.startswith(b'RIFF')
    assert edge.calls == [('Merhaba.', 'tr-TR-EmelNeural', '+35%')]
    assert piper.calls == []


def test_edge_failure_falls_back_to_the_same_line_with_piper():
    edge = _FakeEdge(result=(None, 'network down'))
    eng, piper = _engine(edge)
    audio = eng._synthesize_text('Merhaba.', None, None, None, '+35%', 0)
    assert audio.startswith(b'RIFF')
    assert edge.calls and piper.calls == [('Merhaba.', '+35%', None)]


def test_edge_timeout_falls_back_to_piper():
    slow = lambda text, voice, rate='+0%', **kw: _FakeCommunicate(text, voice, rate=rate, delay=0.2)
    edge = ee.EdgeEngine(communicate=slow, converter=_converter, first_chunk_timeout=0.05, clock=_Clock())
    eng, piper = _engine(edge)
    audio = eng._synthesize_text('Merhaba.', None, None, None, '+35%', 0)
    assert audio.startswith(b'RIFF')
    assert piper.calls == [('Merhaba.', '+35%', None)]


def test_cache_hit_does_not_touch_the_network():
    edge = _FakeEdge()
    eng, _piper = _engine(edge)
    first = eng._synthesize_text('Aynı cümle.', None, None, None, '+35%', 0)
    second = eng._synthesize_text('Aynı cümle.', None, None, None, '+35%', 0)
    assert first == second
    assert len(edge.calls) == 1


def test_natural_voice_off_never_calls_edge():
    edge = _FakeEdge()
    eng, piper = _engine(edge, natural=False)
    audio = eng._synthesize_text('Merhaba.', None, None, None, '+35%', 0)
    assert audio.startswith(b'RIFF')
    assert edge.calls == []
    assert piper.calls == [('Merhaba.', '+35%', None)]


def test_speaker_gender_selects_the_edge_voice_and_ignores_pitch_transform(monkeypatch):
    edge = _FakeEdge()
    eng, piper = _engine(edge)
    eng.set_speaker_matching(_Matcher('male'), {'male': object(), 'female': object()})
    audio = eng._synthesize_text('Merhaba.', None, None, 'female-shift', '+35%', 0)
    assert audio.startswith(b'RIFF')
    assert edge.calls == [('Merhaba.', 'tr-TR-AhmetNeural', '+35%')]
    assert piper.calls == []
    assert eng._edge_voice_for('x') == 'tr-TR-AhmetNeural'


def test_edge_makes_dubbing_ready_without_the_piper_model(monkeypatch):
    edge = _FakeEdge()
    eng, _piper = _engine(edge)
    monkeypatch.setattr(fd, 'PYGAME_AVAILABLE', True)
    monkeypatch.setattr(fd, 'model_is_downloaded', lambda voice_key=None: False)
    assert eng.voice_missing is False
    assert eng.is_ready is True
    assert eng.init_error is None


def test_unknown_language_stays_on_piper():
    edge = _FakeEdge()
    eng = fd.FastDubbingEngine(duck_enabled=False, natural_voice=True, target_lang='ko', edge_engine=edge)
    piper = _FakePiper()
    eng._get_piper = lambda voice_key=None: piper
    eng._synthesize_text('안녕.', None, None, None, '+35%', 0)
    assert edge.calls == []
    assert piper.calls == [('안녕.', '+35%', None)]
