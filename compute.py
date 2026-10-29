from pathlib import Path
import json, subprocess, os, shutil, sys

CHUNK_COMPUTE = 50_000_000  # 50M
CHUNK_SAVE = 100_000
FILES_PER_SHARD = 100
DATA_DIR = Path("pi_data")
STATE_DIR = Path("state")
YCRUNCHER_DIR = Path("y-cruncher")

def log(m): print(f"[CLI] {m}", flush=True)

def find_bin():
    for p in YCRUNCHER_DIR.rglob("y-cruncher"):
        if p.is_file() and os.access(p, os.X_OK):
            return p.resolve()
    return None

def ensure_ycruncher():
    b = find_bin()
    if b: return b
    url = "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547-static.tar.xz"
    dl = Path("dl.tar.xz")
    log(f"Downloading y-cruncher")
    subprocess.run(["curl","-L","-o",str(dl),url], check=True)
    subprocess.run(["tar","-xJf",str(dl)], check=True)
    dl.unlink(missing_ok=True)
    for d in Path(".").glob("y-cruncher*"):
        if d.is_dir() and d.name != "y-cruncher":
            if YCRUNCHER_DIR.exists(): shutil.rmtree(YCRUNCHER_DIR)
            d.rename(YCRUNCHER_DIR); break
    for p in YCRUNCHER_DIR.rglob("y-cruncher"):
        p.chmod(0o755)
    return find_bin()

def main():
    DATA_DIR.mkdir(exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)
    
    idx_path = STATE_DIR / "index.json"
    prog_path = STATE_DIR / "progress.json"
    
    if not idx_path.exists():
        idx_path.write_text('{"total_digits":0}')
    total = json.loads(idx_path.read_text())["total_digits"]
    next_total = total + CHUNK_COMPUTE
    
    log(f"Computing {total:,} -> {next_total:,} digits")

    y_bin = ensure_ycruncher()
    if not y_bin:
        log("y-cruncher binary not found")
        sys.exit(1)

    work = STATE_DIR / "_work"
    if work.exists(): shutil.rmtree(work)
    work.mkdir(exist_ok=True)
    
    # Copy Binaries
    if (YCRUNCHER_DIR / "Binaries").exists():
        shutil.copytree(YCRUNCHER_DIR / "Binaries", work / "Binaries", dirs_exist_ok=True)

    # 15GB + Swap mode for >1.5B
    if next_total > 1_500_000_000:
        cmd = [str(y_bin), "skip-warnings", "custom", "pi", f"-dec:{next_total}", "-hex:0",
               "-mode:swap", "-M:15g", "-swap:default", "-minIO:4m"]
        log("Mode: SWAP -M:15g")
    else:
        cmd = [str(y_bin), "skip-warnings", "custom", "pi", f"-dec:{next_total}", "-hex:0",
               "-M:15g"]
        log("Mode: RAM -M:15g")

    subprocess.run(cmd, cwd=work, check=True)

    # Find output txt
    cands = [p for p in work.glob("*.txt") if p.stat().st_size > 1_000_000]
    if not cands:
        cands = [p for p in work.rglob("*.txt") if p.stat().st_size > 1_000_000]
    pi_file = sorted(cands, key=lambda x: x.stat().st_size, reverse=True)[0]
    log(f"Found output: {pi_file} {pi_file.stat().st_size} bytes")

    raw = pi_file.read_text()
    clean = raw.replace("\n","").replace(" ","").replace("\r","")
    if clean.startswith("3."):
        clean = clean[2:]
    clean = clean[:next_total]
    log(f"Clean length: {len(clean):,}")

    # Save shards
    for i in range(total, next_total, CHUNK_SAVE):
        shard = (i // CHUNK_SAVE) // FILES_PER_SHARD
        sd = DATA_DIR / f"{shard:03d}"
        sd.mkdir(parents=True, exist_ok=True)
        dest = sd / f"pi_{i:08d}-{i+CHUNK_SAVE-1:08d}.txt"
        if not dest.exists():
            dest.write_text(clean[i:i+CHUNK_SAVE])

    # Progress
    prog_path.write_text(json.dumps({
        "total_digits": next_total,
        "last_shard": f"{(next_total // CHUNK_SAVE -1)//FILES_PER_SHARD:03d}"
    }, indent=2))
    
    shutil.rmtree(work, ignore_errors=True)
    idx_path.write_text(json.dumps({"total_digits": next_total}, indent=2))
    log(f"Done {next_total:,}")

if __name__ == "__main__":
    main()
