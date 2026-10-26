from pathlib import Path
import json, subprocess, os, shutil, tarfile, zipfile

CHUNK_COMPUTE = 100_000_000
CHUNK_SAVE = 100_000
FILES_PER_SHARD = 100

DATA_DIR = Path("pi_data")
YCRUNCHER_DIR = Path("y-cruncher")

# あなたが見つけた正しいURL (優先順位順)
URLS = [
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547-dynamic.tar.xz",
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547-static.tar.xz",
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher.v0.8.7.9547.zip",
]

def log(m): print(f"[CLI] {m}", flush=True)

def update_progress(**kw):
    p = DATA_DIR / "progress.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    d.update(kw)
    import datetime
    d["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    log(f"PROGRESS {kw}")

def ensure_ycruncher():
    if (YCRUNCHER_DIR / "y-cruncher").exists():
        return
    for url in URLS:
        try:
            log(f"Downloading {url}")
            fname = Path(url).name
            ext = ".tar.xz" if ".tar.xz" in fname else ".zip" if ".zip" in fname else ".tar.gz"
            dl = Path(f"dl{ext}")
            r = subprocess.run(["curl","-L","-f","-o",str(dl),url], capture_output=True, text=True)
            if r.returncode != 0 or not dl.exists():
                log(f"curl failed {r.stderr[:200]}")
                continue
            log(f"Extracting {dl} size={dl.stat().st_size}")
            if ext == ".zip":
                with zipfile.ZipFile(dl) as z: z.extractall(".")
            elif ext == ".tar.xz":
                subprocess.run(["tar","-xJf",str(dl)], check=True)
            else:
                subprocess.run(["tar","-xzf",str(dl)], check=True)
            dl.unlink(missing_ok=True)
            # フォルダ探す
            for d in Path(".").glob("y-cruncher*"):
                if d.is_dir() and d != YCRUNCHER_DIR:
                    if YCRUNCHER_DIR.exists(): shutil.rmtree(YCRUNCHER_DIR)
                    d.rename(YCRUNCHER_DIR)
                    break
            # バイナリ権限
            for b in YCRUNCHER_DIR.rglob("y-cruncher"):
                if b.is_file(): b.chmod(0o755)
            if (YCRUNCHER_DIR / "y-cruncher").exists():
                log("y-cruncher ready")
                return
        except Exception as e:
            log(f"Error {e}")
            continue
    raise RuntimeError("All downloads failed")

def main():
    DATA_DIR.mkdir(exist_ok=True)
    ensure_ycruncher()
    total = json.loads((DATA_DIR/"index.json").read_text()).get("total_digits",0) if (DATA_DIR/"index.json").exists() else 0
    next_total = total + CHUNK_COMPUTE
    log(f"{total:,} -> {next_total:,}")
    update_progress(total_digits=total, status="start_computing")
    os.chdir(YCRUNCHER_DIR)
    out_tmp = Path(f"../{DATA_DIR}/_full.tmp").resolve()
    out_tmp.unlink(missing_ok=True)
    subprocess.run(["./y-cruncher","custom","pi",f"-o:{out_tmp}",f"-d:{next_total}","-b:1G","--no-wait"], check=True)
    os.chdir("..")
    raw = out_tmp.read_text()
    clean = raw.replace("\n","").replace(" ","").replace("\r","")
    if clean.startswith("3."): clean = clean[2:]
    clean = clean[:next_total]
    for i in range(total, next_total, CHUNK_SAVE):
        shard_id = (i // CHUNK_SAVE) // FILES_PER_SHARD
        shard_dir = DATA_DIR / f"{shard_id:03d}"
        shard_dir.mkdir(parents=True, exist_ok=True)
        out_file = shard_dir / f"pi_{i:08d}-{i+CHUNK_SAVE-1:08d}.txt"
        if not out_file.exists():
            out_file.write_text(clean[i:i+CHUNK_SAVE])
    out_tmp.unlink(missing_ok=True)
    (DATA_DIR/"index.json").write_text(json.dumps({"total_digits": next_total}, indent=2))
    update_progress(total_digits=next_total, status="computed", total_files=next_total//CHUNK_SAVE)

if __name__ == "__main__":
    main()
