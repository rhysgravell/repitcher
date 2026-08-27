#!/usr/bin/env python3
"""
repitch.py - transpose audio samples to a target key, preserving tempo.

Reads the source key from the filename (e.g. "Chord_Stab_Gm_124.wav"), works out
the semitone distance to the target key, and renders a pitch-shifted copy.

Examples
--------
    # Single file, key read from filename
    ./repitch.py Chord_Stab_Gm_124.wav --to Cm

    # Whole folder into ./out
    ./repitch.py ~/Samples/Loops --to Cm -o ./out

    # Filename has no key, or you don't trust it
    ./repitch.py weird_name.wav --from Gm --to Cm

    # Skip keys entirely
    ./repitch.py loop.wav --semitones -3

    # See what it would do without rendering
    ./repitch.py ~/Samples --to Cm --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg", ".m4a"}

# ---------------------------------------------------------------------------
# Key parsing
# ---------------------------------------------------------------------------

PITCH_CLASS = {
    "C": 0, "B#": 0,
    "C#": 1, "DB": 1,
    "D": 2,
    "D#": 3, "EB": 3,
    "E": 4, "FB": 4,
    "F": 5, "E#": 5,
    "F#": 6, "GB": 6,
    "G": 7,
    "G#": 8, "AB": 8,
    "A": 9,
    "A#": 10, "BB": 10,
    "B": 11, "CB": 11,
}

# Preferred spelling when we name the output file.
SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass(frozen=True)
class Key:
    pc: int          # pitch class 0-11
    minor: bool

    def __str__(self) -> str:
        return SHARP_NAMES[self.pc] + ("m" if self.minor else "")

    @property
    def mode(self) -> str:
        return "minor" if self.minor else "major"


# Matches a key token: root + optional accidental + optional mode.
# Anchored to separators so "Ambient" or "Fm_Radio" don't produce false hits.
_KEY_TOKEN = re.compile(
    r"""
    (?P<root>[A-Ga-g])
    (?P<acc>[#b♯♭]|s(?=[^a-zA-Z]|$)|sharp|flat)?
    (?P<mode>minor|major|min|maj|m|M)?
    """,
    re.VERBOSE,
)

_SEP = r"[^A-Za-z0-9#♯♭]"


def parse_key(text: str, *, strict: bool = False) -> Key | None:
    """Parse a key from a string.

    strict=True is used for --from/--to where the whole string should be a key.
    strict=False scans a filename for a plausible key token.
    """
    text = text.strip()
    if strict:
        m = _KEY_TOKEN.fullmatch(text)
        return _build_key(m) if m else None

    # Scan filename tokens, right to left. Sample packs usually put the key near
    # the end ("Pad_Warm_Gm_124.wav"), and later tokens are less likely to be
    # words like "Ambient" that start with a note letter.
    stem = Path(text).stem
    candidates = [t for t in re.split(_SEP, stem) if t]
    for token in reversed(candidates):
        m = _KEY_TOKEN.fullmatch(token)
        if not m:
            continue
        key = _build_key(m)
        if key is None:
            continue
        # A bare letter with no accidental and no mode ("A", "F") is too weak on
        # its own - too many false positives from track numbers and initials.
        if not m.group("acc") and not m.group("mode"):
            continue
        return key
    return None


def _build_key(m: re.Match | None) -> Key | None:
    if m is None:
        return None
    root = m.group("root").upper()
    acc = (m.group("acc") or "").lower()
    if acc in ("#", "♯", "s", "sharp"):
        root += "#"
    elif acc in ("b", "♭", "flat"):
        root += "B"
    pc = PITCH_CLASS.get(root)
    if pc is None:
        return None

    mode = m.group("mode")
    # Default to minor - it is by far the more common convention in sample packs
    # and in dub techno in particular. "Gm" and "G" both read as minor unless
    # explicitly marked major.
    minor = mode not in ("major", "maj", "M")
    return Key(pc, minor)


# ---------------------------------------------------------------------------
# Transposition
# ---------------------------------------------------------------------------

def semitone_distance(src: Key, dst: Key, direction: str = "nearest") -> int:
    """Semitones from src to dst.

    direction: "nearest" (default, within -6..+6), "up" (0..11), "down" (-11..0)
    """
    up = (dst.pc - src.pc) % 12
    down = up - 12
    if direction == "up":
        return up
    if direction == "down":
        return down
    return up if up <= 6 else down


# ---------------------------------------------------------------------------
# Pitch shifting engines
# ---------------------------------------------------------------------------

# In preference order. Varispeed is resampling rather than time-stretching,
# and rubberband has no mode for it, so --tape is served by ffmpeg or sox only.
ENGINES = ["rubberband", "ffmpeg", "sox"]
TAPE_ENGINES = ["ffmpeg", "sox"]


def detect_engine(preferred: str | None = None, tape: bool = False) -> str:
    candidates = TAPE_ENGINES if tape else ENGINES
    if preferred and preferred != "auto":
        if preferred not in candidates:
            sys.exit(f"--engine {preferred} has no varispeed mode; --tape needs "
                     f"{' or '.join(TAPE_ENGINES)}.")
        if not shutil.which(preferred):
            sys.exit(f"--engine {preferred}: not on PATH. Install it, or drop "
                     f"--engine to use whatever is available.")
        return preferred
    for name in candidates:
        if shutil.which(name):
            return name
    installs = {
        "rubberband": "  brew install rubberband   (best quality, recommended)",
        "ffmpeg": "  brew install ffmpeg",
        "sox": "  brew install sox",
    }
    sys.exit(
        f"No engine found for {'--tape (varispeed)' if tape else 'pitch shifting'}.\n"
        "Install one of:\n" + "\n".join(installs[c] for c in candidates)
    )


def probe_samplerate(src: Path) -> int:
    """Read the sample rate, falling back to 44100 if we can't."""
    if src.suffix.lower() == ".wav":
        try:
            with wave.open(str(src), "rb") as wf:
                return wf.getframerate()
        except (wave.Error, OSError, EOFError):
            pass
    if shutil.which("ffprobe"):
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate", "-of", "csv=p=0", str(src)],
            capture_output=True, text=True,
        )
        val = proc.stdout.strip()
        if val.isdigit():
            return int(val)
    print(f"        warning: could not read sample rate for {src.name}, "
          f"assuming 44100 Hz - install ffprobe (ffmpeg) for accurate "
          f"--tape shifts on non-44.1kHz sources", file=sys.stderr)
    return 44100


def build_command(engine: str, src: Path, dst: Path, semitones: float,
                  tape: bool, quality: str, formants: bool = False) -> list[str]:
    if tape:
        # Varispeed: pitch and speed move together, like a tape machine.
        ratio = 2 ** (semitones / 12)
        if engine == "sox":
            return ["sox", str(src), str(dst), "speed", f"{ratio:.9f}",
                    "rate", "-v", "-s"]
        # ffmpeg: reinterpret the sample rate, then resample back to the
        # original rate. asetrate needs a literal value, not an expression.
        sr = probe_samplerate(src)
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
            "-af", f"asetrate={int(round(sr * ratio))},"
                   f"aresample={sr}:resampler=soxr:precision=28",
            str(dst),
        ]

    if engine == "rubberband":
        cmd = ["rubberband", "-p", f"{semitones:g}"]
        if quality == "high":
            cmd += ["--fine", "--pitch-hq"]
        if formants:
            cmd += ["--formant"]
        cmd += [str(src), str(dst)]
        return cmd

    if engine == "ffmpeg":
        formant_opt = ":formant=preserved" if formants else ""
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
            "-af", f"rubberband=pitch={2 ** (semitones / 12):.9f}:pitchq=quality{formant_opt}",
            str(dst),
        ]

    if engine == "sox":
        return ["sox", str(src), str(dst), "pitch", f"{semitones * 100:g}"]

    raise ValueError(f"unknown engine: {engine}")


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

_ACC_ALTS = {
    "#": r"(?:#|♯|s|sharp)",
    "B": r"(?:b|♭|flat)",
}


def key_token_pattern(key: Key) -> re.Pattern:
    """Match any spelling of this key's root in a filename.

    A#m may be written "A#m", "Bbm", "Bb_m", "Bbminor", "Asharp"... - all of
    them name the same pitch class, so all of them should be replaced.
    """
    spellings = sorted(
        (name for name, pc in PITCH_CLASS.items() if pc == key.pc),
        key=len, reverse=True,   # try "BB" before "B", or "B" eats the flat
    )
    alts = []
    for spelling in spellings:
        letter, acc = spelling[0], spelling[1:]
        # A natural must not swallow the letter of an accidental spelling:
        # with src_key B, "Bb_124" is B-flat, not B followed by junk.
        alts.append(letter + (_ACC_ALTS[acc] if acc else r"(?![#b♯♭])"))
    return re.compile(
        rf"(?<![A-Za-z0-9])"
        rf"(?:{'|'.join(alts)})"
        rf"(?:[ _-]?(?:minor|major|min|maj|m))?"
        rf"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def output_name(src: Path, src_key: Key | None, dst_key: Key | None,
                semitones: float, out_dir: Path) -> Path:
    stem = src.stem
    if src_key and dst_key:
        # Replace the old key token in place if we can find it, so
        # "Pad_Gm_124" becomes "Pad_Cm_124" rather than "Pad_Gm_124_Cm".
        new_stem, n = key_token_pattern(src_key).subn(str(dst_key), stem, count=1)
        stem = new_stem if n else f"{stem}_{dst_key}"
    else:
        sign = "+" if semitones >= 0 else ""
        stem = f"{stem}_{sign}{semitones:g}st"
    return out_dir / f"{stem}{src.suffix}"


def claim_output(src: Path, dst: Path, claimed: dict[Path, Path],
                 overwrite: bool) -> tuple[Path | None, str]:
    """Decide whether we may write dst, recording the claim if we may.

    Returns (path, "") to go ahead, or (None, reason) to skip this source.

    Two inputs can transpose to the same name - "Pad_Gm_124" and "Pad_Am_124"
    both become "Pad_Cm_124" - and the second render would quietly destroy the
    first. The second one always loses, --overwrite or not: that flag is about
    files from an earlier run, not about eating this run's own output.
    """
    if dst.resolve() == src.resolve():
        # Renaming in place would read and write the same file.
        dst = dst.with_name(f"{src.stem}_repitched{src.suffix}")
    key = dst.resolve()
    if key in claimed:
        return None, f"would overwrite {dst.name} from {claimed[key].name}"
    if dst.exists() and not overwrite:
        return None, f"{dst.name} exists - use --overwrite"
    claimed[key] = src
    return dst, ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def collect_files(target: Path, recursive: bool) -> list[Path]:
    if target.is_file():
        return [target]
    pattern = "**/*" if recursive else "*"
    return sorted(
        p for p in target.glob(pattern)
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Transpose audio samples to a target key, preserving tempo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples\n--------\n")[-1],
    )
    ap.add_argument("input", type=Path, help="audio file or folder")
    ap.add_argument("--from", dest="from_key",
                    help="source key override (default: read from filename)")
    shift_group = ap.add_mutually_exclusive_group()
    shift_group.add_argument("--to", dest="to_key",
                             help="target key, e.g. Cm, F#m, Amaj")
    shift_group.add_argument("--semitones", type=float,
                             help="shift by a fixed number of semitones, ignoring keys")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="output folder (default: alongside the input)")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="recurse into subfolders")
    ap.add_argument("--direction", choices=["nearest", "up", "down"],
                    default="nearest",
                    help="which way to transpose (default: nearest, max 6st)")
    mode_group = ap.add_mutually_exclusive_group()
    mode_group.add_argument("--tape", action="store_true",
                            help="varispeed - pitch and tempo move together")
    mode_group.add_argument("--formants", action="store_true",
                            help="preserve formants when pitch-shifting - less "
                                 "'chipmunk' effect on vocals (rubberband/ffmpeg only)")
    ap.add_argument("--engine", choices=["auto"] + ENGINES, default="auto")
    ap.add_argument("--quality", choices=["normal", "high"], default="high")
    ap.add_argument("--max-shift", type=float, default=7.0,
                    help="warn above this many semitones (default: 7)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would happen, render nothing")
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite existing output files")
    args = ap.parse_args()

    if args.semitones is None and not args.to_key:
        ap.error("give either --to <key> or --semitones <n>")
    if not args.input.exists():
        ap.error(f"not found: {args.input}")

    dst_key = None
    if args.to_key:
        dst_key = parse_key(args.to_key, strict=True)
        if dst_key is None:
            ap.error(f"could not parse target key: {args.to_key!r}")

    from_key_override = None
    if args.from_key:
        from_key_override = parse_key(args.from_key, strict=True)
        if from_key_override is None:
            ap.error(f"could not parse source key: {args.from_key!r}")

    engine = detect_engine(args.engine, args.tape)
    if args.formants and engine == "sox":
        print("note: sox has no formant preservation - shifting without it.\n")

    files = collect_files(args.input, args.recursive)
    if not files:
        print("No audio files found.", file=sys.stderr)
        return 1

    print(f"engine: {engine}   files: {len(files)}"
          f"{'   (dry run)' if args.dry_run else ''}\n")

    input_root = args.input if args.input.is_dir() else args.input.parent

    done = skipped = failed = 0
    claimed: dict[Path, Path] = {}   # resolved output -> the source writing it
    for src in files:
        if args.out:
            # Mirror the source's subfolder under -o so recursive runs don't
            # flatten same-named files from different subfolders into one.
            out_dir = args.out / src.parent.relative_to(input_root)
        else:
            out_dir = src.parent
        src_key = None

        if args.semitones is not None:
            shift = args.semitones
        else:
            src_key = from_key_override or parse_key(src.name)
            if src_key is None:
                print(f"  skip  {src.name}\n"
                      f"        no key in filename - pass --from, or use "
                      f"--semitones")
                skipped += 1
                continue
            if src_key == dst_key:
                print(f"  skip  {src.name}  (already {dst_key})")
                skipped += 1
                continue
            shift = semitone_distance(src_key, dst_key, args.direction)

        # Claim the output even on a dry run, so the plan we print is the
        # plan we would actually carry out.
        dst, reason = claim_output(
            src, output_name(src, src_key, dst_key, shift, out_dir),
            claimed, args.overwrite,
        )
        if dst is None:
            print(f"  skip  {src.name}  ({reason})")
            skipped += 1
            continue

        label = f"{src_key} -> {dst_key}" if src_key else "shift"
        sign = "+" if shift >= 0 else ""
        warn = ""
        if abs(shift) > args.max_shift:
            warn = "  [large shift - expect artefacts]"
        if src_key and dst_key and src_key.minor != dst_key.minor:
            warn += (f"  [mode mismatch: {src_key.mode} -> {dst_key.mode}; "
                     f"transposing the root only]")

        print(f"  {src.name}\n"
              f"        {label}  {sign}{shift:g}st  ->  {dst.name}{warn}")

        if args.dry_run:
            done += 1
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = build_command(engine, src, dst, shift, args.tape, args.quality,
                           args.formants)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except OSError as exc:
            # A missing binary should read like any other failure, not a
            # traceback halfway through a folder.
            print(f"        FAILED: could not run {cmd[0]}: {exc.strerror}")
            failed += 1
            continue
        if proc.returncode != 0:
            lines = proc.stderr.strip().splitlines()
            print(f"        FAILED: {lines[-1] if lines else 'unknown error'}")
            try:  # don't leave a truncated file behind
                dst.unlink(missing_ok=True)
            except OSError:
                pass
            failed += 1
        else:
            done += 1

    print(f"\ndone: {done}   skipped: {skipped}   failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
