"""Natural online voices through Microsoft Edge's read-aloud service (edge-tts).

The network call runs on a dedicated asyncio loop thread. Audio arrives as MP3 and is
turned into 16-bit PCM WAV so it can travel through the existing gain/ducking/playback
pipeline unchanged. Any failure opens a 60 s circuit breaker so dubbing falls back to
Piper silently instead of retrying a dead connection line by line.
"""
import asyncio
import concurrent.futures
import io
import logging
import os
import tempfile
import threading
import time
import wave

logger = logging.getLogger(__name__)

EDGE_AVAILABLE = False
EDGE_IMPORT_ERROR = ''

try:
    import edge_tts
    EDGE_AVAILABLE = True
except Exception as _e:  # pragma: no cover - exercised only without the dependency
    EDGE_IMPORT_ERROR = str(_e)

# target language → (female voice, male voice)
VOICE_TABLE = {
    'tr': ('tr-TR-EmelNeural', 'tr-TR-AhmetNeural'),
    'en': ('en-US-JennyNeural', 'en-US-GuyNeural'),
    'de': ('de-DE-KatjaNeural', 'de-DE-ConradNeural'),
    'ru': ('ru-RU-SvetlanaNeural', 'ru-RU-DmitryNeural'),
    'fr': ('fr-FR-DeniseNeural', 'fr-FR-HenriNeural'),
    'es': ('es-ES-ElviraNeural', 'es-ES-AlvaroNeural'),
    'ar': ('ar-SA-ZariyahNeural', 'ar-SA-HamedNeural'),
    'ja': ('ja-JP-NanamiNeural', 'ja-JP-KeitaNeural'),
    'zh': ('zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural'),
}

_MALE_ALIASES = {'male', 'm', 'man', 'erkek'}
_FEMALE_ALIASES = {'female', 'f', 'woman', 'kadın', 'kadin'}


def ses_sec(hedef_dil: str | None, cinsiyet: str | None = 'female') -> str | None:
    """Edge voice id for a target language and gender; None when Edge has no voice (→ Piper)."""
    lang = str(hedef_dil or '').strip().lower().replace('_', '-').split('-')[0]
    voices = VOICE_TABLE.get(lang)
    if not voices:
        return None
    gender = str(cinsiyet or '').strip().lower()
    if gender in _MALE_ALIASES:
        return voices[1]
    if gender in _FEMALE_ALIASES:
        return voices[0]
    return voices[0]


def _mp3_to_wav(mp3_bytes: bytes) -> bytes:
    """Decode MP3 with pygame/SDL (already required for playback) and wrap it as WAV."""
    try:
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        import pygame
        import pygame.sndarray  # noqa: F401  (needs numpy)
    except Exception as e:
        raise RuntimeError(f'MP3 decoder unavailable: {e}') from e

    init = pygame.mixer.get_init()
    if not init:
        pygame.mixer.init(frequency=24000, size=-16, channels=1)
        init = pygame.mixer.get_init()
    if not init:
        raise RuntimeError('pygame mixer could not start')

    path = os.path.join(tempfile.gettempdir(), f'_edge_tts_{threading.get_ident()}_{time.monotonic_ns()}.mp3')
    try:
        with open(path, 'wb') as f:
            f.write(mp3_bytes)
        sound = pygame.mixer.Sound(path)
        samples = pygame.sndarray.array(sound)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    freq, _fmt, channels = pygame.mixer.get_init()
    channels = abs(channels)
    if getattr(samples, 'ndim', 1) == 1:
        samples = samples.reshape(-1, 1)
    if samples.shape[1] != channels:
        channels = samples.shape[1]
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(freq)
        wf.writeframes(samples.astype('int16').tobytes())
    return buf.getvalue()


class EdgeEngine:
    def __init__(
        self,
        first_chunk_timeout: float = 2.0,
        cooldown_seconds: float = 60.0,
        request_timeout: float = 15.0,
        communicate=None,
        converter=None,
        clock=None,
    ):
        self._first_chunk_timeout = first_chunk_timeout
        self._cooldown = cooldown_seconds
        self._request_timeout = request_timeout
        self._communicate = communicate
        self._converter = converter
        self._clock = clock or time.monotonic
        self._disabled_until = 0.0
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._loop_lock = threading.Lock()

    @property
    def available(self) -> bool:
        return EDGE_AVAILABLE and self._clock() >= self._disabled_until

    @property
    def disabled_for(self) -> float:
        """Seconds left on the circuit breaker (0 when closed)."""
        return max(0.0, self._disabled_until - self._clock())

    def _trip(self, reason) -> None:
        self._disabled_until = self._clock() + self._cooldown
        logger.warning('[EdgeTTS] Circuit open for %ss: %s', int(self._cooldown), reason)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._loop_lock:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=self._run_loop, args=(loop,), daemon=True, name='EdgeTTSLoop')
            self._loop, self._thread = loop, thread
            thread.start()
            return loop

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def submit(self, text: str, voice: str, rate: str = '+0%'):
        """Start synthesis on the loop thread; returns a Future (None when the circuit is open)."""
        if not self.available or not voice or not (text or '').strip():
            return None
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(self._collect(text.strip(), voice, rate), loop)

    def synthesize(self, text: str, voice: str, rate: str = '+0%', timeout: float | None = None):
        """Blocking convenience wrapper → (wav bytes | None, error | None). Never raises."""
        future = self.submit(text, voice, rate)
        if future is None:
            return None, 'edge-tts unavailable'
        try:
            return future.result(timeout=timeout or self._request_timeout + self._first_chunk_timeout), None
        except (concurrent.futures.TimeoutError, asyncio.TimeoutError):  # distinct classes before Python 3.11
            future.cancel()
            self._trip('request timed out')
            return None, 'edge-tts request timed out'
        except Exception as e:
            self._trip(e)
            return None, str(e)

    async def _collect(self, text: str, voice: str, rate: str) -> bytes:
        factory = self._communicate or getattr(edge_tts, 'Communicate', None)
        if factory is None:
            raise RuntimeError(f'edge-tts is not available: {EDGE_IMPORT_ERROR}')
        communicate = factory(text, voice, rate=rate)
        stream = communicate.stream()
        agen = stream.__aiter__()
        chunks: list[bytes] = []
        try:
            # First audible chunk must arrive within the fallback window (2.0 s by default).
            item = await asyncio.wait_for(agen.__anext__(), self._first_chunk_timeout)
            while item.get('type') != 'audio' or not item.get('data'):
                item = await asyncio.wait_for(agen.__anext__(), self._first_chunk_timeout)
            chunks.append(item['data'])
            async for item in agen:
                if item.get('type') == 'audio' and item.get('data'):
                    chunks.append(item['data'])
        finally:
            closer = getattr(agen, 'aclose', None)
            if closer is not None:
                try:
                    await closer()
                except Exception:
                    pass
        data = b''.join(chunks)
        if not data:
            raise RuntimeError('edge-tts returned no audio')
        convert = self._converter or _mp3_to_wav
        wav = convert(data)
        if not wav or not wav.startswith(b'RIFF'):
            raise RuntimeError('edge-tts audio could not be converted to WAV')
        return wav
