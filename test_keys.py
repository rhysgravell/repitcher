import sys
sys.path.insert(0, '.')
from repitch import parse_key, semitone_distance, Key, output_name
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

print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
