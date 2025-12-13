#!/usr/bin/env python3
import argparse
import subprocess
import sys
import shlex
from dataclasses import dataclass
from typing import List, Tuple, Optional

from rich import print
from rich.table import Table

# ---------- Data structures ----------

@dataclass
class EpisodeSegment:
    index: int
    start: float   # seconds
    end: float     # seconds
    has_intro: bool
    intro_start: Optional[float] = None
    intro_end: Optional[float] = None


# ---------- Shell helpers ----------

def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess:
    """Run a command and return the CompletedProcess, raising on error."""
    # Debug: print(" ".join(shlex.quote(c) for c in cmd))
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if proc.returncode != 0:
        print(f"[red]Command failed:[/red] {' '.join(cmd)}")
        print("[yellow]stderr:[/yellow]")
        print(proc.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return proc


# ---------- ffprobe / ffmpeg utilities ----------

def get_duration(input_file: str) -> float:
    """Get total duration of a video in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    proc = run_cmd(cmd)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Could not parse duration for {input_file}")


def detect_scene_changes(input_file: str, threshold: float = 0.4) -> List[float]:
    """
    Use ffmpeg's scene detection to get timestamps of big visual changes.

    This runs:
        ffmpeg -i input -vf "select='gt(scene,THRESH)',showinfo" -f null -
    and parses pts_time from showinfo lines.
    """
    cmd = [
        "ffmpeg",
        "-i", input_file,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-"
    ]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    times: List[float] = []
    for line in proc.stderr.splitlines():
        if "showinfo" in line and "pts_time:" in line:
            # example: "... pts_time:12.345 ..."
            parts = line.split("pts_time:")
            if len(parts) < 2:
                continue
            tail = parts[1].split()[0]
            try:
                t = float(tail)
                times.append(t)
            except ValueError:
                continue

    times = sorted(set(times))
    return times


# ---------- Intro detection heuristics ----------

def find_intro_for_episode(
    scene_changes: List[float],
    ep_start: float,
    ep_end: float,
    cold_open_min: float = 5.0,
    cold_open_max: float = 240.0,
    intro_min: float = 8.0,
    intro_max: float = 210.0,
) -> Tuple[Optional[float], Optional[float]]:
    """Find an intro inside a single episode range using scene change pairs.

    Strategy: consider consecutive scene-change pairs inside the episode.
    Prefer pairs whose start is inside the expected cold-open window and whose
    gap (intro length) is within [intro_min, intro_max]. If none, fall back to
    the earliest pair that satisfies only the length window.
    """
    ep_scenes = [t for t in scene_changes if ep_start <= t <= ep_end]
    if len(ep_scenes) < 2:
        return None, None

    candidates: List[Tuple[float, float, float]] = []  # (start, end, gap)
    for a, b in zip(ep_scenes, ep_scenes[1:]):
        gap = b - a
        if intro_min <= gap <= intro_max:
            candidates.append((a, b, gap))

    if not candidates:
        return None, None

    # Prefer those that start inside the cold-open window
    cold_window_candidates = [
        c for c in candidates if ep_start + cold_open_min <= c[0] <= ep_start + cold_open_max
    ]

    chosen = cold_window_candidates[0] if cold_window_candidates else candidates[0]
    return chosen[0], chosen[1]


# ---------- Multi-episode guess ----------

def count_potential_episodes(scene_changes: List[float], duration: float) -> int:
    """
    Heuristically detect number of episodes by looking for intro+outro patterns.
    
    Typical Paw Patrol pattern:
    - Intro: 15-30 seconds of scene changes
    - Content: variable
    - Outro/Title card transition: another intro pattern
    
    Returns: 1 or 2 (or best guess)
    """
    if not scene_changes or duration < 600:
        return 1
    
    # Look for intro-like patterns (clusters of scene changes in first ~30s)
    intro_end_candidates = []
    for t in scene_changes:
        if 8 < t < 30:  # typical intro end range
            intro_end_candidates.append(t)
    
    if not intro_end_candidates:
        return 1
    
    first_intro_end = intro_end_candidates[-1]  # last scene change in intro range
    
    # Look for a second intro pattern (suggests 2nd episode)
    # Typical split is around 690-730s for 23-24 min episodes
    mid = duration / 2.0
    tolerance = 150  # +/- 2.5 minutes from midpoint
    
    second_intro_start = mid - 50  # intros start ~50s before actual content begins
    second_intro_end = mid + 50
    
    for t in scene_changes:
        if second_intro_start < t < second_intro_end and t > first_intro_end + 300:
            # found scene activity in expected 2nd episode intro region
            return 2
    
    return 1


def guess_episode_segments(
    duration: float,
    scene_changes: List[float],
    assume_two: bool
) -> List[Tuple[float, float]]:
    """
    Return list of (start, end) segments for episodes.

    Strategy:
      - If not assume_two: treat entire file as one episode.
      - If assume_two:
          * Try to auto-detect if actually 1 or 2 episodes
          * If 2 detected: naive split at middle, snap to nearest scene change
          * If 1 detected: return entire file as single episode
    """
    if not assume_two:
        return [(0.0, duration)]

    # Auto-detect number of episodes
    num_episodes = count_potential_episodes(scene_changes, duration)
    
    if num_episodes == 1:
        return [(0.0, duration)]

    mid = duration / 2.0

    # find scene change closest to mid, but not too close to edges
    best_t = None
    best_delta = None
    for t in scene_changes:
        if t < 300 or t > duration - 300:  # don't split near very start or very end
            continue
        delta = abs(t - mid)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_t = t

    if best_t is None:
        # fallback: just hard split
        split = mid
    else:
        split = best_t

    return [(0.0, split), (split, duration)]


# ---------- Cutting ----------

def cut_segment(
    input_file: str,
    start: float,
    end: float,
    output_file: str
) -> None:
    """Use ffmpeg to cut a segment [start, end] into output_file (re-mux, no re-encode)."""
    duration = max(0, end - start)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{start:.3f}",
        "-i", input_file,
        "-t", f"{duration:.3f}",
        "-c", "copy",
        output_file
    ]
    run_cmd(cmd)


# ---------- High-level pipeline ----------

def analyze_and_split(
    input_file: str,
    scene_threshold: float,
    assume_two: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    duration = get_duration(input_file)
    print(f"[cyan]Duration:[/cyan] {duration:.1f} seconds")

    print(f"[cyan]Detecting scene changes (threshold={scene_threshold})...[/cyan]")
    scenes = detect_scene_changes(input_file, threshold=scene_threshold)
    print(f"[cyan]Found {len(scenes)} scene changes[/cyan]")

    if verbose:
        preview = ", ".join(f"{t:.1f}" for t in scenes[:40])
        print(f"[blue]Scene times (first 40):[/blue] {preview}")

    episode_ranges = guess_episode_segments(duration, scenes, assume_two=assume_two)

    segments: List[EpisodeSegment] = []
    for idx, (ep_start, ep_end) in enumerate(episode_ranges, start=1):
        ep_intro_start, ep_intro_end = find_intro_for_episode(
            scenes,
            ep_start,
            ep_end,
        )
        has_intro = ep_intro_start is not None and ep_intro_end is not None

        if verbose and not has_intro:
            print(f"[yellow]No intro detected for episode {idx} in range {ep_start:.1f}-{ep_end:.1f}s[/yellow]")

        segments.append(
            EpisodeSegment(
                index=idx,
                start=ep_start,
                end=ep_end,
                has_intro=has_intro,
                intro_start=ep_intro_start,
                intro_end=ep_intro_end,
            )
        )

    # Pretty-print plan
    table = Table(title="Episode segmentation plan")
    table.add_column("#", justify="right")
    table.add_column("Episode range (s)")
    table.add_column("Has intro?")
    table.add_column("Intro range (s)")

    for seg in segments:
        ep_range = f"{seg.start:.1f} → {seg.end:.1f}"
        intro_info = "-"
        has_intro_str = "no"
        if seg.has_intro and seg.intro_start is not None and seg.intro_end is not None:
            has_intro_str = "yes"
            intro_info = f"{seg.intro_start:.1f} → {seg.intro_end:.1f}"
        table.add_row(str(seg.index), ep_range, has_intro_str, intro_info)

    print(table)

    if dry_run:
        print("[magenta]Dry run only; no files written.[/magenta]")
        return

    # Cut full episodes
    base = input_file.rsplit(".", 1)[0]

    for seg in segments:
        ep_out = f"{base}_ep{seg.index}.mkv"
        print(f"[cyan]Cutting episode {seg.index} → {ep_out}[/cyan]")
        cut_segment(input_file, seg.start, seg.end, ep_out)

        # Also cut intro separately if present
        if seg.has_intro and seg.intro_start is not None and seg.intro_end is not None:
            intro_out = f"{base}_ep{seg.index}_intro.mkv"
            print(f"[cyan]Cutting intro for episode {seg.index} → {intro_out}[/cyan]")
            cut_segment(input_file, seg.intro_start, seg.intro_end, intro_out)

    print("[green]Done.[/green]")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="Detect intro & split single or double-episode video files using ffmpeg."
    )
    parser.add_argument(
        "input",
        help="Input video file"
    )
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=0.4,
        help="Scene detection threshold for ffmpeg (default: 0.4)"
    )
    parser.add_argument(
        "--assume-two",
        action="store_true",
        help="Assume the file contains two episodes and try to split near the middle."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and print plan, but don't write output files."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional detection details (scene times)."
    )

    args = parser.parse_args()

    try:
        analyze_and_split(
            input_file=args.input,
            scene_threshold=args.scene_threshold,
            assume_two=args.assume_two,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
