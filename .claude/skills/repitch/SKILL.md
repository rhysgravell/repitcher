---
name: repitch
description: Transpose audio samples to a target key (or by a fixed number of semitones) using repitch.py, while preserving tempo. Use when the user wants to retune, transpose, pitch-shift, or key-match audio files or sample packs - e.g. "shift these loops to Cm", "retune this folder to match my track", "pitch this stab down 3 semitones".
---

# repitch

Wraps `repitch.py`, a dependency-free CLI that reads the key from a sample's
filename (or an explicit override), works out the semitone distance to a
target key, and renders a pitch-shifted copy with tempo preserved.

## Before running

Check one pitch-shifting engine is installed - the script auto-detects
whichever is present, in this order: rubberband > ffmpeg > sox.

```bash
which rubberband || which ffmpeg || which sox
```

If none are found, ask the user which to install (rubberband is recommended
for quality):

```bash
brew install rubberband
```

## Workflow

1. **Figure out the request**: a target key (`--to Cm`, `--to F#m`, `--to Amaj`)
   or a fixed shift (`--semitones -3`). If the source key can't be trusted or
   read from the filename, use `--from <key>`.

2. **Dry-run first** whenever operating on a folder, or whenever the shift
   amount isn't already obvious to the user. This prints the plan (per-file
   shift amounts, output filenames, warnings) without rendering anything:

   ```bash
   ./repitch.py <input> --to <key> --dry-run
   ```

   Review the output for `[large shift - expect artefacts]` or
   `[mode mismatch ...]` warnings and flag them to the user before rendering.

3. **Render for real** by dropping `--dry-run`. Use `-o <dir>` to keep
   originals untouched by writing elsewhere, and `-r` to recurse into
   subfolders.

   ```bash
   ./repitch.py <input> --to <key> -o ./out
   ```

4. Re-running on the same input is safe - existing outputs are skipped
   unless `--overwrite` is passed.

## Useful flags

| Flag | When to use it |
|---|---|
| `--direction up` / `down` | Override the default nearest-interval (max 6st) transposition |
| `--tape` | Varispeed mode - pitch and tempo move together. Good for dub techno / lo-fi character, bad when tempo must stay fixed |
| `--quality normal` | Faster, lower-quality render than the default `high` |
| `--engine rubberband\|ffmpeg\|sox` | Force a specific engine instead of auto-detect |
| `--max-shift N` | Change the semitone threshold for the "large shift" warning (default 7) |

## Notes to pass along

- A shift past ~5-6 semitones is audible - fine for pads/atmospheres, more
  obvious on vocals and acoustic percussion. Mention this if a requested
  shift is large.
- Transposing between major and minor only moves the root; it doesn't
  change the mode. Flag this if the user asks to go e.g. Gm -> C major.
- Filenames with no parseable key (no accidental, no mode marker) are
  skipped with an explanation - suggest `--from <key>` or `--semitones`.
