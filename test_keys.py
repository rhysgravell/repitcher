import sys
import tempfile
import shutil
sys.path.insert(0, '.')
from repitch import parse_key, semitone_distance, Key, output_name, claim_output, detect_engine, compressed_fallback, run_engine
from pathlib import Path

cases = [
 ("Chord_Stab_Gm_124.wav","Gm"), ("Pad Warm F#m 120.aif","F#m"),
 ("loop-Abmaj-90.wav","G#"), ("Dub_Chord_Cmin_128.wav","Cm"),
 ("Ambient_Texture.wav",None), ("Bass_Bb_m_70.wav","A#m"),
 ("stab_dm_140.wav","Dm"), ("Kick_01.wav",None),
 ("Sub_Gminor.wav","Gm"), ("track_A_take3.wav",None),
 ("Rhodes_Ebm_118.wav","D#m"), ("Amen_Break.wav",None),
]
fails=0
for name,exp in cases:
    got = parse_key(name)
    got = str(got) if got else None
    ok = got==exp
    fails += not ok
    print(f"{'ok ' if ok else 'FAIL'}  {name:32} -> {got!s:6} (want {exp})")

print()
for a,b,exp in [("Gm","Cm",5),("Gm","Am",2),("Cm","Gm",-5),("Am","Gm",-2),("Cm","F#m",6),("Gm","Gm",0)]:
    d = semitone_distance(parse_key(a,strict=True),parse_key(b,strict=True))
    ok = d==exp; fails += not ok
    print(f"{'ok ' if ok else 'FAIL'}  {a} -> {b} = {d:+d}st (want {exp:+d})")

print()
naming = [
 ("Chord_Stab_Gm_124.wav","Chord_Stab_Cm_124.wav"),
 ("Pad_Gminor.aif","Pad_Cm.aif"),
 # flat and unicode spellings name the same pitch class as the sharp one
 ("Bass_Bbm_70.wav","Bass_Cm_70.wav"),
 ("Bass_Bb_m_70.wav","Bass_Cm_70.wav"),
 ("Rhodes_Ebm_118.wav","Rhodes_Cm_118.wav"),
 ("loop-Abmaj-90.wav","loop-Cm-90.wav"),
 ("Stab_A♯m_128.wav","Stab_Cm_128.wav"),
]
# no key token in the name (--from override) -> append rather than replace
naming.append(("Sub_deep.wav","Sub_deep_Cm.wav"))
for src,exp in naming:
    src_key = parse_key(src) or parse_key("Gm",strict=True)
    out = output_name(Path(src), src_key, parse_key("Cm",strict=True), 5, Path("."))
    ok = out.name==exp; fails += not ok
    print(f"{'ok ' if ok else 'FAIL'}  {src} -> {out.name} (want {exp})")

print()
# Output claims: two sources must never race for the same destination, and a
# dry run has to reach the same verdicts as the real thing.
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d/"Pad_Cm_124.wav").touch()          # left over from an earlier run
    gm, am = d/"Pad_Gm_124.wav", d/"Pad_Am_124.wav"
    dst = d/"Pad_Cm_124.wav"
    claims = [
     # (label, src, dst, overwrite, expected name or None)
     ("existing output, no --overwrite", gm, dst, False, None),
     ("existing output, --overwrite",    gm, dst, True,  "Pad_Cm_124.wav"),
     ("second source, same name",        am, dst, True,  None),
     ("source is its own output",        gm, gm,  True,  "Pad_Gm_124_repitched.wav"),
    ]
    claimed = {}
    for label,src,want_dst,ow,exp in claims:
        got,reason = claim_output(src, want_dst, claimed, ow)
        got = got.name if got else None
        ok = got==exp; fails += not ok
        print(f"{'ok ' if ok else 'FAIL'}  {label:32} -> {got!s:26} (want {exp})")

print()
# Engine choice has to match the job: --tape is resampling, which rubberband
# does not do, and an engine that is not installed must not reach subprocess.
installed = set()
shutil.which = lambda name, *a, **k: f"/usr/bin/{name}" if name in installed else None
engines = [
 # (what is installed, --engine, --tape, expected engine or None for exit)
 ({"rubberband","ffmpeg","sox"}, "auto",       False, "rubberband"),
 ({"rubberband","ffmpeg","sox"}, "auto",       True,  "ffmpeg"),
 ({"rubberband"},                "auto",       False, "rubberband"),
 ({"rubberband"},                "auto",       True,  None),
 ({"sox"},                       "auto",       True,  "sox"),
 ({"rubberband","ffmpeg"},       "rubberband", True,  None),
 ({"ffmpeg"},                    "sox",        False, None),
 ({"ffmpeg"},                    "ffmpeg",     True,  "ffmpeg"),
]
for have,preferred,tape,exp in engines:
    installed = have
    try:
        got = detect_engine(preferred, tape)
    except SystemExit:
        got = None
    ok = got==exp; fails += not ok
    flags = f"--engine {preferred}{' --tape' if tape else ''}"
    print(f"{'ok ' if ok else 'FAIL'}  have {sorted(have)!s:36} {flags:26} -> {got!s:11} (want {exp})")

print()
# Compressed formats: libsndfile (so rubberband and sox) may not open them, so
# a failed render reaches for ffmpeg - or says why it cannot. Reuses the
# shutil.which stub above; `installed` decides what is on PATH.
fallbacks = [
 # (file, engine that failed, ffmpeg installed, retry engine, hint)
 ("Pad_Gm.m4a", "rubberband", True,  "ffmpeg", ""),
 ("Pad_Gm.mp3", "sox",        True,  "ffmpeg", ""),
 ("Pad_Gm.M4A", "rubberband", True,  "ffmpeg", ""),
 ("Pad_Gm.m4a", "rubberband", False, None, ".m4a needs ffmpeg to decode - brew install ffmpeg"),
 ("Pad_Gm.m4a", "ffmpeg",     True,  None, ""),   # ffmpeg already tried
 ("Pad_Gm.wav", "rubberband", True,  None, ""),   # nothing to do with format
]
for name,engine,have_ffmpeg,exp_alt,exp_hint in fallbacks:
    installed = {"ffmpeg"} if have_ffmpeg else set()
    alt,hint = compressed_fallback(Path(name), engine)
    ok = (alt,hint)==(exp_alt,exp_hint); fails += not ok
    print(f"{'ok ' if ok else 'FAIL'}  {name:12} {engine:11} ffmpeg={str(have_ffmpeg):5} -> {alt!s:7} {hint}")

print()
for cmd,exp_ok,exp_why in [
 (["true"],  True,  ""),
 (["false"], False, "unknown error"),
 (["definitely-not-a-real-binary"], False, "could not run"),
]:
    got_ok,why = run_engine(cmd)
    ok = got_ok==exp_ok and why.startswith(exp_why); fails += not ok
    print(f"{'ok ' if ok else 'FAIL'}  run_engine({cmd[0]}) -> {got_ok} {why!r} (want {exp_ok} {exp_why!r}...)")

print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
