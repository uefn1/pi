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

def update_progress(**kw):
    p = DATA_DIR / "progress.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    d.update(kw)
    import datetime
    d["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False))

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

    # ★重要: 出力は絶対パスではなく、y-cruncherからの相対パスで、存在するディレクトリを指定
    # y-cruncherは指定したディレクトリに "Pi - 100000000.txt" のようなファイルを作る
    abs_data_dir = DATA_DIR.resolve()
    abs_data_dir.mkdir(parents=True, exist_ok=True)
    
    # 一時出力用の空フォルダ
    tmp_out_dir = abs_data_dir / "_yc_out"
    tmp_out_dir.mkdir(exist_ok=True)

    os.chdir(YCRUNCHER_DIR)
    # -o はディレクトリを指定。ファイル名はy-cruncherが決める
    cmd = ["./y-cruncher","custom","pi", f"-o:{tmp_out_dir}", f"-d:{next_total}", "-b:1G", "--no-wait"]
    log(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    os.chdir("..")

    # 生成されたファイルを探す
    generated = list(tmp_out_dir.glob("*.txt"))
    if not generated:
        generated = list(tmp_out_dir.glob("*Pi*"))
    if not generated:
        raise FileNotFoundError(f"y-cruncher output not found in {tmp_out_dir}, listing: {list(tmp_out_dir.iterdir())}")
    
    out_file = generated[0]
    log(f"Found y-cruncher output: {out_file}")

    raw = out_file.read_text()
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

    # 後片付け
    shutil.rmtree(tmp_out_dir)
    index_file.write_text(json.dumps({"total_digits": next_total}, indent=2))
    update_progress(total_digits=next_total, status="computed", total_files=next_total//CHUNK_SAVE)

if __name__ == "__main__":
    main()
