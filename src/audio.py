"""موسيقى خلفية للريل مُركّبة بالكود بالكامل (بلا عينات ولا ملفات صوتية، فلا حقوق نشر).

120 نبضة/دقيقة على شبكة المشاهد نفسها: طبل على كل نبضة، صنج خفيف بين النبضات،
خط باص وتآلفات ناعمة، و«ووش» قبل كل انتقال مشهد. حتمية تماماً: نفس المدخلات تعطي نفس الصوت.
"""
import math
import struct
import wave
from pathlib import Path

RATE = 22050
BPM = 120
BEAT = 60 / BPM

# تقدّم تآلفي هادئ (لا مينور ← فا ← دو ← صول) بترددات النغمات
CHORDS = [(220.00, 261.63, 329.63), (174.61, 220.00, 261.63), (196.00, 261.63, 329.63), (196.00, 246.94, 293.66)]


def _noise(n: int) -> float:
    """ضوضاء حتمية في [-1, 1] من رقم العيّنة."""
    x = math.sin(n * 12.9898 + 78.233) * 43758.5453
    return (x - math.floor(x)) * 2 - 1


def make_track(path: Path, duration: float, scene_starts: list[float] | None = None) -> Path:
    n_total = int(duration * RATE)
    starts = [s for s in (scene_starts or []) if s > 0.2]
    out = bytearray()
    peak = 0.0
    samples = []
    for n in range(n_total):
        t = n / RATE
        beat_pos = t / BEAT
        bt = (beat_pos % 1) * BEAT                     # الزمن منذ آخر نبضة
        bar = int(beat_pos // 4)
        chord = CHORDS[bar % len(CHORDS)]
        # طبل: موجة جيبية يهبط ترددها مع تلاشٍ سريع
        kick = math.sin(2 * math.pi * (45 + 90 * math.exp(-bt * 30)) * bt) * math.exp(-bt * 9) * 0.55
        # صنج بين النبضات
        ot = ((beat_pos + 0.5) % 1) * BEAT
        hat = _noise(n) * math.exp(-ot * 55) * 0.10
        # باص على النبضتين 1 و3 من كل مقياس
        bass_t = (beat_pos % 2) * BEAT
        bass = math.sin(2 * math.pi * chord[0] / 2 * t) * math.exp(-bass_t * 2.5) * 0.22
        # تآلفات ناعمة بتلاشٍ داخل كل مقياس
        bar_t = (beat_pos % 4) * BEAT
        env = min(1.0, bar_t / 0.25) * (0.75 + 0.25 * math.exp(-bar_t))
        pad = sum(math.sin(2 * math.pi * f * t) + 0.5 * math.sin(2 * math.pi * f * 1.003 * t) for f in chord) * 0.035 * env
        # ووش قبل كل انتقال مشهد
        whoosh = 0.0
        for s in starts:
            d = s - t
            if 0 < d < 0.35:
                whoosh += _noise(n * 7) * ((0.35 - d) / 0.35) ** 2 * 0.16
        v = kick + hat + bass + pad + whoosh
        samples.append(v)
        peak = max(peak, abs(v))
    fade = int(0.25 * RATE)
    scale = 0.85 / (peak or 1)
    for i, v in enumerate(samples):
        g = min(1.0, i / fade, (n_total - i) / fade)
        out += struct.pack("<h", int(max(-1.0, min(1.0, v * scale * g)) * 32767))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(bytes(out))
    return path
