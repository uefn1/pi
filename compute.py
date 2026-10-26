from pathlib import Path
import json, subprocess, os, shutil, zipfile

CHUNK_COMPUTE = 100_000_000
CHUNK_SAVE = 100_000
FILES_PER_SHARD = 100

DATA_DIR = Path("pi_data")
STATE_DIR = Path("state")  # ★ jsonはこっち

YCRUNCHER_DIR = Path("y-cruncher")

URLS = [
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547-dynamic.tar.xz",
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547-static.tar.xz",
]

def log(m): print(f"[CLI] {m}", flush=True)

def ensure_ycruncher():
    if (YCRUNCHER_DIR / "y-cruncher").exists():
        return
    for url in URLS:
        try:
            log(f"Downloading {url}")
            dl = Path("dl.tar.xz")
            r = subprocess.run(["curl","-L","-f","-o",str(dl),url], capture_output=True)
            if r.returncode != 0: continue
            subprocess.run(["tar","-xJf",str(dl)], check=True)
            dl.unlink(missing_ok=True)
            for d in Path(".").glob("y-cruncher*"):
                if d.is_dir() and d != YCRUNCHER_DIR:
                    if YCRUNCHER_DIR.exists(): shutil.rmtree(YCRUNCHER_DIR)
                    d.rename(YCRUNCHER_DIR)
                    break
            for b in YCRUNCHER_DIR.rglob("y-cruncher"):
                if b.is_file(): b.chmod(0o755)
            if (YCRUNCHER_DIR / "y-cruncher").exists():
                return
        except Exception as e:
            log(f"Error {e}")

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    index_file = STATE_DIR / "index.json"
    progress_file = STATE_DIR / "progress.json"

    # 初回用にファイルが無ければ作る
    if not index_file.exists():
        index_file.write_text(json.dumps({"total_digits":0}, indent=2))
    if not progress_file.exists():
        progress_file.write_text(json.dumps({"total_digits":0,"status":"idle"}, indent=2))

    total = json.loads(index_file.read_text()).get("total_digits",0)
    next_total = total + CHUNK_COMPUTE
    log(f"{total:,} -> {next_total:,}")

    work_dir = STATE_DIR / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    for f in work_dir.glob("*"): 
        if f.is_file(): f.unlink()
        else: shutil.rmtree(f)

    y_bin = (YCRUNCHER_DIR / "y-cruncher").resolve()
    bin_dir = YCRUNCHER_DIR / "Binaries"
    if bin_dir.exists():
        shutil.copytree(bin_dir, work_dir / "Binaries", dirs_exist_ok=True)

    cmd = [str(y_bin), "skip-warnings", "custom", "pi", f"-dec:{next_total}"]
    log(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=work_dir, check=True)

    candidates = list(work_dir.glob("Pi*.txt")) + list(work_dir.glob("*.txt"))
    pi_file = None
    for c in candidates:
        if c.stat().st_size > 1000000:
            if "y-cruncherCommand-LineManual" not in c.read_text()[:500]:
                pi_file = c
                break
    if not pi_file:
        pi_file = sorted(candidates, key=lambda x: x.stat().st_size, reverse=True)[0]

    log(f"Found {pi_file} size={pi_file.stat().st_size}")
    raw = pi_file.read_text()
    if "y-cruncherCommand-LineManual" in raw[:500]:
        raise ValueError("Got manual not digits")

    clean = raw.replace("\n","").replace(" ","").replace("\r","")
    if clean.startswith("3."): clean = clean[2:]
    clean = clean[:next_total]

    for i in range(total, next_total, CHUNK_SAVE):
        shard_id = (i // CHUNK_SAVE) // FILES_PER_SHARD
        shard_dir = DATA_DIR / f"{shard_id:03d}"
        shard_dir.mkdir(parents=True, exist_ok=True)
        dest = shard_dir / f"pi_{i:08d}-{i+CHUNK_SAVE-1:08d}.txt"
        if not dest.exists() or dest.stat().st_size < 50000:
            dest.write_text(clean[i:i+CHUNK_SAVE])

    shutil.rmtree(work_dir)
    index_file.write_text(json.dumps({"total_digits": next_total}, indent=2))
    
    import datetime
    prog = json.loads(progress_file.read_text())
    prog.update({
        "total_digits": next_total,
        "status": "computed",
        "total_files": next_total // CHUNK_SAVE,
        "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    progress_file.write_text(json.dumps(prog, indent=2))
    log(f"Done {next_total:,}")

if __name__ == "__main__":
    main()
