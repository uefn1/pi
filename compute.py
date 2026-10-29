from pathlib import Path
import json, subprocess, os, shutil, sys

CHUNK_COMPUTE = 50_000_000
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

def extract_new_digits(pi_file: Path, total: int, need: int) -> str:
    """9.5GBの整形済みy-cruncher出力をストリーミングで50Mだけ抜く"""
    log(f"Streaming {pi_file.stat().st_size/1e9:.2f} GB file...")
    collected = []
    collected_len = 0
    scanned_len = 0
    
    with pi_file.open("r", encoding="utf-8", errors="ignore", buffering=1024*1024) as f:
        for line in f:
            if ":" not in line:
                continue
            # "4124606720 884879... :  9550000000" の左側だけが数字
            left = line.split(":")[0]
            digits = left.replace(" ", "").strip()
            if not digits:
                continue
            if scanned_len == 0 and digits.startswith("3."):
                digits = digits[2:]
            
            if scanned_len + len(digits) <= total:
                scanned_len += len(digits)
                continue
            
            # ここから必要
            start_in_line = max(0, total - scanned_len)
            chunk = digits[start_in_line:]
            
            take = min(len(chunk), need - collected_len)
            if take > 0:
                collected.append(chunk[:take])
                collected_len += take
            
            scanned_len += len(digits)
            
            if collected_len >= need:
                break
    
    result = "".join(collected)
    log(f"Extracted {len(result):,} digits (scanned {scanned_len:,})")
    return result[:need]

def main():
    DATA_DIR.mkdir(exist_ok=True); STATE_DIR.mkdir(exist_ok=True)
    idx = STATE_DIR/"index.json"
    if not idx.exists(): idx.write_text('{"total_digits":0}')
    total = json.loads(idx.read_text())["total_digits"]
    next_total = total + CHUNK_COMPUTE
    log(f"{total:,} -> {next_total:,}")

    y_bin = ensure_ycruncher()
    work = STATE_DIR/"_work"
    if work.exists(): shutil.rmtree(work)
    work.mkdir()
    if (YCRUNCHER_DIR/"Binaries").exists():
        shutil.copytree(YCRUNCHER_DIR/"Binaries", work/"Binaries", dirs_exist_ok=True)

    cmd = [str(y_bin), "skip-warnings", "custom", "pi", f"-dec:{next_total}", "-hex:0",
           "-mode:swap", "-M:15g", "-swap:default", "-minIO:4m"]
    subprocess.run(cmd, cwd=work, check=True)

    cands = [p for p in work.rglob("*.txt") if p.stat().st_size > 1_000_000]
    pi_file = sorted(cands, key=lambda x: x.stat().st_size, reverse=True)[0]
    log(f"Found {pi_file} {pi_file.stat().st_size/1e9:.2f} GB")

    # ★ ここが修正: 9.5GBを全部読まない
    clean = extract_new_digits(pi_file, total, CHUNK_COMPUTE)
    
    # 即削除してRAM/ディスク空ける
    shutil.rmtree(work, ignore_errors=True)
    
    for i in range(total, next_total, CHUNK_SAVE):
        shard = (i//CHUNK_SAVE)//FILES_PER_SHARD
        sd = DATA_DIR/f"{shard:03d}"; sd.mkdir(parents=True, exist_ok=True)
        dest = sd/f"pi_{i:08d}-{i+CHUNK_SAVE-1:08d}.txt"
        offset = i - total
        if not dest.exists():
            dest.write_text(clean[offset:offset+CHUNK_SAVE])
    
    idx.write_text(json.dumps({"total_digits": next_total}, indent=2))
    (STATE_DIR/"progress.json").write_text(json.dumps({"total_digits": next_total}, indent=2))
    log(f"Done {next_total:,}")

if __name__ == "__main__":
    main()
