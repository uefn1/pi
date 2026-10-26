from pathlib import Path
import json, subprocess, os, shutil, sys, urllib.request, tarfile

# ===== 設定 =====
CHUNK_COMPUTE = 100_000_000  # 1回で1億桁計算 (y-cruncherなら数秒)
CHUNK_SAVE = 100_000         # 保存は10万桁ずつ (1000ファイル制限対策)
FILES_PER_SHARD = 100        # 1フォルダ100ファイル = 1000万桁

DATA_DIR = Path("pi_data")
YCRUNCHER_DIR = Path("y-cruncher")

YCRUNCHER_URL = "https://github.com/Mysticial/y-cruncher/releases/download/v0.8.5.9543/y-cruncher-v0.8.5.9543-static-dynamic.tar.gz"

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
        return
    log("Downloading y-cruncher...")
    tar_path = Path("yc.tar.gz")
    urllib.request.urlretrieve(YCRUNCHER_URL, tar_path)
    with tarfile.open(tar_path) as tar:
        tar.extractall(".")
    tar_path.unlink()
    # 展開されたフォルダを y-cruncher にリネーム
    for d in Path(".").glob("y-cruncher*"):
        if d.is_dir() and d != YCRUNCHER_DIR:
            if YCRUNCHER_DIR.exists():
                shutil.rmtree(YCRUNCHER_DIR)
            d.rename(YCRUNCHER_DIR)
            break
    (YCRUNCHER_DIR / "y-cruncher").chmod(0o755)
    log("y-cruncher ready")

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ensure_ycruncher()

    index_file = DATA_DIR / "index.json"
    total = json.loads(index_file.read_text()).get("total_digits", 0) if index_file.exists() else 0
    next_total = total + CHUNK_COMPUTE

    log(f"=== FASTEST MODE ===")
    log(f"Current: {total:,} digits")
    log(f"Computing to: {next_total:,} digits (+{CHUNK_COMPUTE:,})")

    update_progress(total_digits=total, status="start_computing", next_range=f"{total}-{next_total-1}")

    # y-cruncher実行
    os.chdir(YCRUNCHER_DIR)
    out_tmp = Path(f"../{DATA_DIR}/_full.tmp").resolve()
    # 既存の出力があれば消す
    out_tmp.unlink(missing_ok=True)
    
    cmd = [
        "./y-cruncher", "custom", "pi",
        f"-o:{out_tmp}",
        f"-d:{next_total}",
        "-b:1G",  # 1GBメモリまで使う (GitHub runnerは7GB)
        "--no-wait"
    ]
    log(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    os.chdir("..")

    # 出力をクリーニング: "3.\\n14159..." -> "14159..."
    raw = out_tmp.read_text()
    clean = raw.replace("\n","").replace(" ","").replace("\r","")
    if clean.startswith("3."):
        clean = clean[2:]
    clean = clean[:next_total]

    log(f"Cleaned length: {len(clean):,} digits")

    # シャーディング保存
    for i in range(total, next_total, CHUNK_SAVE):
        shard_id = (i // CHUNK_SAVE) // FILES_PER_SHARD
        shard_dir = DATA_DIR / f"{shard_id:03d}"
        shard_dir.mkdir(parents=True, exist_ok=True)
        out_file = shard_dir / f"pi_{i:08d}-{i+CHUNK_SAVE-1:08d}.txt"
        if not out_file.exists():
            chunk = clean[i:i+CHUNK_SAVE]
            out_file.write_text(chunk)
    
    out_tmp.unlink(missing_ok=True)
    index_file.write_text(json.dumps({"total_digits": next_total}, indent=2))
    
    total_files = next_total // CHUNK_SAVE
    log(f"Done! Total files: {total_files}, Shards: {len(list(DATA_DIR.glob('[0-9][0-9][0-9]')))}")
    update_progress(
        total_digits=next_total,
        status="computed",
        total_files=total_files,
        last_shard=f"{(next_total//CHUNK_SAVE)//FILES_PER_SHARD:03d}"
    )

if __name__ == "__main__":
    main()
