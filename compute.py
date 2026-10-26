from pathlib import Path
import json, subprocess, os, shutil, zipfile

CHUNK_COMPUTE = 100_000_000
CHUNK_SAVE = 100_000
FILES_PER_SHARD = 100

DATA_DIR = Path("pi_data")
STATE_DIR = Path("state")
YCRUNCHER_DIR = Path("y-cruncher")

URLS = [
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547-dynamic.tar.xz",
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547-static.tar.xz",
]

def log(m): print(f"[CLI] {m}", flush=True)

def find_ycruncher_bin():
    # いろんな場所を探す
    candidates = [
        YCRUNCHER_DIR / "y-cruncher",
        YCRUNCHER_DIR / "y-cruncher" / "y-cruncher",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c.resolve()
    # 再帰探索
    if YCRUNCHER_DIR.exists():
        for p in YCRUNCHER_DIR.rglob("y-cruncher"):
            if p.is_file() and os.access(p, os.X_OK):
                return p.resolve()
        for p in YCRUNCHER_DIR.rglob("y-cruncher*"):
            if p.is_file() and p.name == "y-cruncher":
                return p.resolve()
    return None

def ensure_ycruncher():
    bin_path = find_ycruncher_bin()
    if bin_path and bin_path.exists():
        log(f"y-cruncher exists at {bin_path}")
        return bin_path

    for url in URLS:
        try:
            log(f"Downloading {url}")
            dl = Path("dl.tar.xz")
            r = subprocess.run(["curl","-L","-f","-o",str(dl),url], capture_output=True)
            if r.returncode != 0: 
                log(f"curl failed {r.returncode}")
                continue
            log(f"Extracting {dl} size={dl.stat().st_size}")
            subprocess.run(["tar","-xJf",str(dl)], check=True)
            dl.unlink(missing_ok=True)

            # 展開されたフォルダを探す
            for d in Path(".").glob("y-cruncher*"):
                if d.is_dir() and d.name != "y-cruncher":
                    if YCRUNCHER_DIR.exists():
                        shutil.rmtree(YCRUNCHER_DIR)
                    d.rename(YCRUNCHER_DIR)
                    log(f"Renamed {d} -> {YCRUNCHER_DIR}")
                    break
            
            # 権限付与
            for b in YCRUNCHER_DIR.rglob("y-cruncher"):
                if b.is_file():
                    b.chmod(0o755)
                    log(f"chmod +x {b}")

            bin_path = find_ycruncher_bin()
            if bin_path:
                log(f"y-cruncher ready at {bin_path}")
                return bin_path
        except Exception as e:
            log(f"Error {e}")
            import traceback; traceback.print_exc()
            continue
    raise FileNotFoundError("y-cruncher binary not found after download")

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    index_file = STATE_DIR / "index.json"
    progress_file = STATE_DIR / "progress.json"

    if not index_file.exists():
        index_file.write_text(json.dumps({"total_digits":0}, indent=2))
    if not progress_file.exists():
        progress_file.write_text(json.dumps({"total_digits":0,"status":"idle"}, indent=2))

    total = json.loads(index_file.read_text()).get("total_digits",0)
    next_total = total + CHUNK_COMPUTE
    log(f"{total:,} -> {next_total:,}")

    y_bin = ensure_ycruncher()
    log(f"Using y-cruncher binary: {y_bin}")

    work_dir = STATE_DIR / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    for f in work_dir.glob("*"): 
        if f.is_file(): 
            try: f.unlink()
            except: pass
        else: 
            try: shutil.rmtree(f)
            except: pass

    # Binariesをwork_dirにコピー
    for src_bin_dir in [YCRUNCHER_DIR / "Binaries", YCRUNCHER_DIR.parent / "Binaries"]:
        if src_bin_dir.exists():
            shutil.copytree(src_bin_dir, work_dir / "Binaries", dirs_exist_ok=True)
            log(f"Copied {src_bin_dir} -> {work_dir/'Binaries'}")
            break

    cmd = [str(y_bin), "skip-warnings", "custom", "pi", f"-dec:{next_total}"]
    log(f"Running in {work_dir}: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=work_dir, check=True)

    candidates = list(work_dir.glob("Pi*.txt")) + list(work_dir.glob("*.txt"))
    pi_file = None
    for c in candidates:
        if c.stat().st_size > 1000000:
            txt = c.read_text()[:500]
            if "y-cruncherCommand-LineManual" not in txt:
                pi_file = c
                break
    if not pi_file:
        if candidates:
            pi_file = sorted(candidates, key=lambda x: x.stat().st_size, reverse=True)[0]
        else:
            raise FileNotFoundError(f"No txt in {work_dir}: {list(work_dir.iterdir())}")

    log(f"Found {pi_file} size={pi_file.stat().st_size}")
    raw = pi_file.read_text()
    if "y-cruncherCommand-LineManual" in raw[:500]:
        raise ValueError("Got manual not digits")

    clean = raw.replace("\n","").replace(" ","").replace("\r","")
    if clean.startswith("3."): clean = clean[2:]
    clean = clean[:next_total]
    log(f"Cleaned {len(clean):,} digits")

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
    prog = json.loads(progress_file.read_text()) if progress_file.exists() else {}
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
