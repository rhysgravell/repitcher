# repitch

Transpose audio samples to a target key, preserving tempo.

## Install

The script has no Python dependencies. It needs one audio engine:

```bash
brew install rubberband    # best quality, recommended
# or
brew install ffmpeg        # also fine - has Rubber Band built in
```

`repitch.py` auto-detects whichever is present (rubberband > ffmpeg > sox).

`--tape` is the exception: varispeed is resampling, not time-stretching, and
rubberband has no mode for it, so tape mode needs ffmpeg or sox.

## Use

```bash
chmod +x repitch.py

# Key read from the filename
./repitch.py Chord_Stab_Gm_124.wav --to Cm
#   -> Chord_Stab_Cm_124.wav   (+5st, same length)

# Whole folder
./repitch.py ~/Samples/Loops --to Cm -o ./out

# Filename has no key
./repitch.py weird_name.wav --from Gm --to Cm

# Forget keys, just shift
./repitch.py loop.wav --semitones -3

# Preview without rendering
./repitch.py ~/Samples --to Cm --dry-run
```

## Options

| Flag | What it does |
|---|---|
| `--to KEY` | Target key: `Cm`, `F#m`, `Bbm`, `Amaj` |
| `--from KEY` | Source key override (skips filename parsing) |
| `--semitones N` | Fixed shift, ignores keys entirely |
| `-o, --out DIR` | Output folder (default: next to the input) |
| `-r, --recursive` | Recurse into subfolders |
| `--direction` | `nearest` (default, max 6st), `up`, `down` |
| `--tape` | Varispeed - pitch and tempo move together |
| `--formants` | Preserve formants (less "chipmunk" effect on vocals) - rubberband/ffmpeg only |
| `--quality` | `high` (default) or `normal` |
| `--dry-run` | Print the plan, render nothing |
| `--overwrite` | Replace existing outputs |

## Filename parsing

Recognised: `Gm`, `G#m`, `Gbm`, `Gmin`, `Gminor`, `Gmaj`, `Bb_m`, `F#`.
Scans right-to-left, since packs usually put the key near the end.

A bare letter with no accidental and no mode (`A`, `F`) is **ignored** on
purpose - otherwise `Ambient_Pad.wav` parses as A minor. Use `--from` for those.

Keys without an explicit mode default to **minor**.

## Notes

- **Nearest direction wins by default.** Gm -> Cm goes up 5, not down 7.
  Use `--direction down` if you want the sample to sit lower.
- **Mode is not transposable.** Gm -> C major only moves the root; the
  script warns and does the transpose anyway. Turning minor into major needs
  MIDI, not audio.
- **Past about 5-6 semitones** you start hearing it. Fine on pads and
  atmospheres, obvious on vocals and acoustic percussion.
- `--tape` is often the better choice for dub techno - the artefacts are
  the point, and it keeps the transient character intact. It runs on ffmpeg
  or sox; a rubberband-only install will tell you so rather than trying.
- `--formants` helps on vocals and other formant-heavy sources when shifting
  more than a couple of semitones. It's ignored by sox, and mutually
  exclusive with `--tape` (varispeed shifts formants by design).
- **Two samples can want the same output name.** `Pad_Gm_124` and
  `Pad_Am_124` both transpose to `Pad_Cm_124`. The second one is skipped
  instead of overwriting the first - `--overwrite` only covers files left
  over from an earlier run, not this run's own renders.
- **`--dry-run` reports the same skips the real run would**, existing files
  and name clashes included.

## Tests

```bash
python3 test_keys.py    # filename parsing + interval maths
```
