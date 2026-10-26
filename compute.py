from pathlib import Path
import json, subprocess, os, shutil, sys, urllib.request, tarfile

CHUNK_COMPUTE = 100_000_000  # 1億桁ずつ
CHUNK_SAVE = 100_000
FILES_PER_SHARD = 100

DATA_DIR = Path("pi_data")
YCRUNCHER_DIR = Path("y-cruncher")

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
        log("y-cruncher already exists")
        return
    
    log("Fetching latest y-cruncher release info from 【entity-GitHub¦canonical_name=GitHub】 API...")
    try:
        # APIから最新リリースのURLを取得 (404回避)
        api_url = "https://api.github.com/repos/Mysticial/y-cruncher/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "pi-bot"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            # Linuxの static-dynamic tar.gz を探す
            asset_url = None
            for asset in data.get("assets", []):
                name = asset["name"].lower()
                if "linux" in name or name.endswith(".tar.gz") or name.endswith(".tar.xz"):
                    if "static" in name or "dynamic" in name:
                        asset_url = asset["browser_download_url"]
                        break
            # 見つからなければ最初のtar
            if not asset_url:
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".tar.gz") or asset["name"].endswith(".tar.xz"):
                        asset_url = asset["browser_download_url"]
                        break
            log(f"Latest asset URL: {asset_url}")
    except Exception as e:
        log(f"API failed {e}, fallback to known URL")
        asset_url = "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.7.9547/y-cruncher-v0.8.7.9547-static.tar.gz"

    tar_path = Path("yc.tar.gz")
    if asset_url.endswith(".tar.xz"):
        tar_path = Path("yc.tar.xz")

    log(f"Downloading {asset_url} ...")
    # curlの方がリダイレクトに強いのでcurlを使う
    try:
        subprocess.run(["curl","-L","-o",str(tar_path),asset_url], check=True)
    except:
        urllib.request.urlretrieve(asset_url, tar_path)

    log("Extracting...")
    if str(tar_path).endswith(".tar.xz"):
        subprocess.run(["tar","-xJf",str(tar_path)], check=True)
    else:
        subprocess.run(["tar","-xzf",str(tar_path)], check=True)
    
    tar_path.unlink(missing_ok=True)

    # フォルダを探して移動
    for d in Path(".").glob("y-cruncher*"):
        if d.is_dir() and d != YCRUNCHER_DIR:
            if YCRUNCHER_DIR.exists():
                shutil.rmtree(YCRUNCHER_DIR)
            d.rename(YCRUNCHER_DIR)
            break
    
    bin_path = YCRUNCHER_DIR / "y-cruncher"
    if not bin_path.exists():
        # 中にバイナリがあるパターン
        for b in YCRUNCHER_DIR.rglob("y-cruncher"):
            if b.is_file():
                bin_path = b
                break
    bin_path.chmod(0o755)
    log(f"y-cruncher ready at {bin_path}")

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_ycruncher()

    index_file = DATA_DIR / "index.json"
    total = json.loads(index_file.read_text()).get("total_digits",0) if index_file.exists() else 0
    next_total = total + CHUNK_COMPUTE

    log(f"=== FASTEST MODE ===")
    log(f"Current: {total:,} -> {next_total:,}")

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
    log(f"Cleaned length: {len(clean):,}")

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
