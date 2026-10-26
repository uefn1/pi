from pathlib import Path
import json, subprocess, os, shutil, zipfile

CHUNK_COMPUTE = 100_000_000
CHUNK_SAVE = 100_000
FILES_PER_SHARD = 100

DATA_DIR = Path("pi_data")
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
            fname = Path(url).name
            ext = ".tar.xz" if ".tar.xz" in fname else ".zip"
            dl = Path(f"dl{ext}")
            r = subprocess.run(["curl","-L","-f","-o",str(dl),url], capture_output=True)
            if r.returncode != 0: continue
            if ext == ".zip":
                with zipfile.ZipFile(dl) as z: z.extractall(".")
            else:
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
                log("y-cruncher ready")
                return
        except Exception as e:
            log(f"Error {e}")
            continue

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_ycruncher()

    index_file = DATA_DIR / "index.json"
    total = json.loads(index_file.read_text()).get("total_digits",0) if index_file.exists() else 0
    next_total = total + CHUNK_COMPUTE
    log(f"{total:,} -> {next_total:,}")

    # 絶対パスで出力ファイルを指定
    abs_data_dir = DATA_DIR.resolve()
    out_file_path = abs_data_dir / f"pi_{next_total}.txt"
    out_file_path.unlink(missing_ok=True)

    os.chdir(YCRUNCHER_DIR)
    # ★修正: -dec: と -o スペース区切り
    cmd = ["./y-cruncher", "custom", "pi", f"-dec:{next_total}", "-o", str(out_file_path)]
    log(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    os.chdir("..")

    if not out_file_path.exists():
        # y-cruncherはカレントに作ることがあるので探す
        candidates = list(YCRUNCHER_DIR.glob("*.txt")) + list(Path(".").glob("*.txt"))
        if candidates:
            out_file_path = candidates[0]
    
    raw = out_file_path.read_text()
    clean = raw.replace("\n","").replace(" ","").replace("\r","")
    if clean.startswith("3."): clean = clean[2:]
    clean = clean[:next_total]
    log(f"Cleaned {len(clean):,}")

    for i in range(total, next_total, CHUNK_SAVE):
        shard_id = (i // CHUNK_SAVE) // FILES_PER_SHARD
        shard_dir = DATA_DIR / f"{shard_id:03d}"
        shard_dir.mkdir(parents=True, exist_ok=True)
        dest = shard_dir / f"pi_{i:08d}-{i+CHUNK_SAVE-1:08d}.txt"
        if not dest.exists():
            dest.write_text(clean[i:i+CHUNK_SAVE])

    out_file_path.unlink(missing_ok=True)
    index_file.write_text(json.dumps({"total_digits": next_total}, indent=2))
    log(f"Done {next_total:,}")

if __name__ == "__main__":
    main()
