from pathlib import Path
import json, subprocess, os, shutil, urllib.request, tarfile, zipfile

CHUNK_COMPUTE = 100_000_000
CHUNK_SAVE = 100_000
FILES_PER_SHARD = 100

DATA_DIR = Path("pi_data")
YCRUNCHER_DIR = Path("y-cruncher")

FALLBACK_URLS = [
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher-v0.8.7.9547-static.tar.gz",
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher-v0.8.7.9547-static-dynamic.tar.gz",
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.6.9545/y-cruncher-v0.8.6.9545-static.tar.gz",
    "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.5.9543/y-cruncher-v0.8.5.9543-static-dynamic.tar.gz",
]

def log(msg):
    print(f"[CLI] {msg}", flush=True)

def update_progress(**kw):
    p = DATA_DIR / "progress.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    d.update(kw)
    import datetime
    d["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    log(f"PROGRESS -> {kw}")

def ensure_ycruncher():
    if (YCRUNCHER_DIR / "y-cruncher").exists():
        log("y-cruncher exists")
        return

    asset_url = None
    try:
        log("Fetching latest release from 【entity-GitHub¦canonical_name=GitHub】 API...")
        api_url = "https://api.github.com/repos/Mysticial/y-cruncher/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "pi-bot", "Accept": "application/vnd.【entity-github¦canonical_name=GitHub】.v3+json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            # とにかくtar.gz / tar.xz / zip を探す
            for asset in data.get("assets", []):
                n = asset["name"].lower()
                if n.endswith(".tar.gz") or n.endswith(".tar.xz") or n.endswith(".zip"):
                    asset_url = asset["browser_download_url"]
                    log(f"Found asset: {asset['name']} -> {asset_url}")
                    break
    except Exception as e:
        log(f"API failed: {e}")

    urls_to_try = []
    if asset_url:
        urls_to_try.append(asset_url)
    urls_to_try.extend(FALLBACK_URLS)

    tar_path = None
    for url in urls_to_try:
        try:
            log(f"Trying download: {url}")
            if url.endswith(".zip"):
                tar_path = Path("yc.zip")
            elif url.endswith(".tar.xz"):
                tar_path = Path("yc.tar.xz")
            else:
                tar_path = Path("yc.tar.gz")
            
            # curl -L でリダイレクト対応
            result = subprocess.run(["curl","-L","-f","-o",str(tar_path),url], capture_output=True, text=True)
            if result.returncode == 0 and tar_path.exists() and tar_path.stat().st_size > 1000000:
                log(f"Downloaded {tar_path} size={tar_path.stat().st_size}")
                break
            else:
                log(f"Failed: {result.stderr[:200]}")
                tar_path.unlink(missing_ok=True)
                tar_path = None
        except Exception as e:
            log(f"Download error: {e}")
            continue

    if not tar_path or not tar_path.exists():
        raise RuntimeError("All y-cruncher downloads failed. Use C version fallback.")

    log(f"Extracting {tar_path}...")
    try:
        if str(tar_path).endswith(".zip"):
            with zipfile.ZipFile(tar_path) as z:
                z.extractall(".")
        elif str(tar_path).endswith(".tar.xz"):
            subprocess.run(["tar","-xJf",str(tar_path)], check=True)
        else:
            subprocess.run(["tar","-xzf",str(tar_path)], check=True)
    finally:
        tar_path.unlink(missing_ok=True)

    # フォルダを探す
    for d in Path(".").glob("y-cruncher*"):
        if d.is_dir() and d != YCRUNCHER_DIR:
            if YCRUNCHER_DIR.exists():
                shutil.rmtree(YCRUNCHER_DIR)
            d.rename(YCRUNCHER_DIR)
            break

    bin_path = None
    for b in YCRUNCHER_DIR.rglob("y-cruncher"):
        if b.is_file():
            bin_path = b
            break
    if not bin_path:
        bin_path = YCRUNCHER_DIR / "y-cruncher"
    
    if bin_path.exists():
        bin_path.chmod(0o755)
        log(f"y-cruncher ready at {bin_path}")
    else:
        raise RuntimeError(f"y-cruncher binary not found in {YCRUNCHER_DIR}")

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_ycruncher()

    index_file = DATA_DIR / "index.json"
    total = json.loads(index_file.read_text()).get("total_digits",0) if index_file.exists() else 0
    next_total = total + CHUNK_COMPUTE

    log(f"=== FASTEST MODE {total:,} -> {next_total:,} ===")
    update_progress(total_digits=total, status="start_computing", next_range=f"{total}-{next_total-1}")

    os.chdir(YCRUNCHER_DIR)
    out_tmp = Path(f"../{DATA_DIR}/_full.tmp").resolve()
    out_tmp.unlink(missing_ok=True)
    
    cmd = ["./y-cruncher","custom","pi", f"-o:{out_tmp}", f"-d:{next_total}", "-b:1G", "--no-wait"]
    log(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    os.chdir("..")

    raw = out_tmp.read_text()
    clean = raw.replace("\n","").replace(" ","").replace("\r","")
    if clean.startswith("3."):
        clean = clean[2:]
    clean = clean[:next_total]
    log(f"Cleaned {len(clean):,}")

    for i in range(total, next_total, CHUNK_SAVE):
        shard_id = (i // CHUNK_SAVE) // FILES_PER_SHARD
        shard_dir = DATA_DIR / f"{shard_id:03d}"
        shard_dir.mkdir(parents=True, exist_ok=True)
        out_file = shard_dir / f"pi_{i:08d}-{i+CHUNK_SAVE-1:08d}.txt"
        if not out_file.exists():
            out_file.write_text(clean[i:i+CHUNK_SAVE])

    out_tmp.unlink(missing_ok=True)
    index_file.write_text(json.dumps({"total_digits": next_total}, indent=2))
    update_progress(total_digits=next_total, status="computed", total_files=next_total//CHUNK_SAVE)

if __name__ == "__main__":
    main()
