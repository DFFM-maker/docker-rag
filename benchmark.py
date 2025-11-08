"""
Benchmark estrazione PDF via Unstructured API
- CLI per ocr_languages (default: ita+eng)
- Rimosse le chiavi deprecate: 'languages' e 'pdf_infer_table_structure'
- Estimator opzionale: elabora le prime N pagine (default 10) e proietta il tempo totale

Esempi:
  # Run con hi_res, timeout 8h, stima su prime 10 pagine e notifica Telegram via env
  python benchmark.py --files "D:\\docker-rag\\data\\w502.pdf" --strategies hi_res --timeout 28800 --output w502_hi_res.json

  # Disabilita warm-up, salva risposta raw e passa token/chat via CLI
  python benchmark.py --files "D:\\docker-rag\\data\\w502.pdf" --strategies hi_res --no-warmup --save-raw \
      --telegram-token "123:ABC" --telegram-chat "23383038"

Note:
- L'estimator richiede PyPDF2 per estrarre le prime N pagine in un PDF temporaneo.
- Se PyPDF2 non è installato o il conteggio pagine non è disponibile, l'estimator viene saltato.
"""

import requests
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
import sys
import os
from typing import List, Dict, Any, Optional

# ----------------------------- COLORI -----------------------------
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

def disable_colors():
    for attr in dir(Colors):
        if attr.isupper():
            setattr(Colors, attr, '')

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*78}")
    print(f"{text:^78}")
    print(f"{'='*78}{Colors.END}\n")

def print_info(label: str, value: Any, color=Colors.CYAN):
    print(f"{color}{label:32s}{Colors.END} {value}")

# ----------------------------- NOTIFICHE -----------------------------
def notify_telegram(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        r = requests.post(url, json=payload, timeout=8)
        print_info("Telegram notify:", f"HTTP {r.status_code}", Colors.GREEN if r.status_code == 200 else Colors.YELLOW)
    except Exception as e:
        print_info("Telegram notify error:", str(e), Colors.RED)

# ----------------------------- UTILS -----------------------------
def safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw_text": response.text[:2000]}

def count_pages(pdf_path: Path) -> Optional[int]:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        return None

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def extract_head_pdf(src: Path, n_pages: int, out_dir: Path = Path("samples")) -> Optional[Path]:
    """Crea un PDF con le prime n_pages. Richiede PyPDF2."""
    try:
        from PyPDF2 import PdfReader, PdfWriter
        ensure_dir(out_dir)
        reader = PdfReader(str(src))
        n = min(n_pages, len(reader.pages))
        if n <= 0:
            return None
        w = PdfWriter()
        for i in range(n):
            w.add_page(reader.pages[i])
        out = out_dir / f"{src.stem}_head{n}.pdf"
        with open(out, "wb") as f:
            w.write(f)
        return out
    except Exception as e:
        print_info("Estimator skipped (PyPDF2 or write failed):", str(e), Colors.YELLOW)
        return None

# ----------------------------- TEST SINGOLO -----------------------------
def test_extraction(session: requests.Session,
                    pdf_path: Path,
                    strategy: str = 'hi_res',
                    api_url: str = "http://localhost:8000",
                    timeout: int = 7200,
                    ocr_languages: str = "ita+eng",
                    save_raw: bool = False,
                    raw_dir: Path = Path("responses")) -> Optional[Dict[str, Any]]:

    if not pdf_path.exists():
        print(f"{Colors.RED}❌ File not found: {pdf_path}{Colors.END}")
        return None

    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
    pages = count_pages(pdf_path)

    print_header(f"📄 Testing: {pdf_path.name}")
    print_info("File size (MB):", f"{file_size_mb:.2f}")
    if pages is not None:
        print_info("Page count:", pages)
    print_info("Strategy:", strategy)
    print_info("OCR languages:", ocr_languages)
    print_info("Start time:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    endpoint = f"{api_url}/general/v0/general"
    start_time = time.time()

    try:
        with open(pdf_path, 'rb') as f:
            files = {'files': (pdf_path.name, f, 'application/pdf')}
            # Rimosse 'languages' e 'pdf_infer_table_structure'
            data = {
                'strategy': strategy,
                'extract_images_in_pdf': 'true',
                'ocr_languages': ocr_languages,
                'output_format': 'application/json'
            }

            print(f"\n{Colors.YELLOW}⏳ Processing request...{Colors.END}")
            response = session.post(endpoint, files=files, data=data, timeout=timeout)

        elapsed = time.time() - start_time

        # Salva raw se richiesto
        if save_raw:
            ensure_dir(raw_dir)
            raw_name = f"{pdf_path.stem}_{strategy}_{int(start_time)}.json"
            raw_path = raw_dir / raw_name
            try:
                with open(raw_path, "w", encoding="utf-8") as rf:
                    rf.write(response.text)
                print_info("Saved raw response:", str(raw_path), Colors.BLUE)
            except Exception as e:
                print_info("Save raw failed:", str(e), Colors.YELLOW)

        if response.status_code == 200:
            # Parsing robusto: supporta list oppure dict con chiave 'elements'
            data_parsed = safe_json(response)

            if isinstance(data_parsed, list):
                elements = data_parsed
            elif isinstance(data_parsed, dict):
                elements = data_parsed.get('elements', data_parsed)
            else:
                elements = []

            if isinstance(elements, str):
                try:
                    maybe = json.loads(elements)
                    elements = maybe if isinstance(maybe, list) else []
                except Exception:
                    elements = []

            elements_count = len(elements) if isinstance(elements, list) else 0
            speed_mb_per_min = file_size_mb / (elapsed / 60) if elapsed > 0 else 0
            speed_mb_per_hour = speed_mb_per_min * 60
            speed_mb_per_sec = file_size_mb / elapsed if elapsed > 0 else 0
            pages_per_min = pages / (elapsed / 60) if pages and elapsed > 0 else None
            pages_per_hour = pages_per_min * 60 if pages_per_min else None

            report = {
                'filename': pdf_path.name,
                'filepath': str(pdf_path),
                'size_mb': round(file_size_mb, 3),
                'pages': pages,
                'strategy': strategy,
                'processing_time_seconds': round(elapsed, 3),
                'processing_time_minutes': round(elapsed / 60, 3),
                'processing_time_hours': round(elapsed / 3600, 5),
                'elements_count': elements_count,
                'speed_mb_per_second': round(speed_mb_per_sec, 5),
                'speed_mb_per_minute': round(speed_mb_per_min, 5),
                'speed_mb_per_hour': round(speed_mb_per_hour, 5),
                'pages_per_minute': round(pages_per_min, 4) if pages_per_min else None,
                'pages_per_hour': round(pages_per_hour, 2) if pages_per_hour else None,
                'success': True,
                'timestamp_start': datetime.fromtimestamp(start_time).isoformat(),
                'timestamp_end': datetime.now().isoformat(),
                'status_code': response.status_code
            }

            print(f"\n{Colors.GREEN}✅ SUCCESS{Colors.END}")
            print_info("Elapsed (min):", f"{elapsed/60:.2f}", Colors.GREEN)
            print_info("Elements:", f"{elements_count:,}", Colors.GREEN)
            print_info("Speed MB/s:", f"{speed_mb_per_sec:.5f}", Colors.GREEN)
            print_info("Speed MB/min:", f"{speed_mb_per_min:.3f}", Colors.GREEN)
            if pages is not None:
                print_info("Pages/min:", f"{pages_per_min:.3f}", Colors.GREEN)
            print_info("Capacity MB/hour:", f"{speed_mb_per_hour:.1f}", Colors.GREEN)
            return report

        else:
            snippet = response.text[:600]
            print(f"\n{Colors.RED}❌ ERROR HTTP {response.status_code}{Colors.END}")
            print(f"{Colors.DIM}{snippet}{Colors.END}")
            return {
                'filename': pdf_path.name,
                'strategy': strategy,
                'success': False,
                'error': f"HTTP {response.status_code}",
                'response_snippet': snippet,
                'timestamp_end': datetime.now().isoformat()
            }

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"\n{Colors.RED}❌ TIMEOUT after {elapsed/60:.2f} min{Colors.END}")
        return {
            'filename': pdf_path.name,
            'strategy': strategy,
            'success': False,
            'error': 'Timeout',
            'elapsed_minutes': round(elapsed / 60, 2)
        }
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n{Colors.RED}❌ EXCEPTION after {elapsed/60:.2f} min{Colors.END}")
        print(f"Error: {str(e)}")
        return {
            'filename': pdf_path.name,
            'strategy': strategy,
            'success': False,
            'error': str(e),
            'elapsed_minutes': round(elapsed / 60, 2)
        }

# ----------------------------- HEALTHCHECK / WARM-UP -----------------------------
def wait_for_api(session: requests.Session, api_url: str, retries: int = 20, delay: float = 4.0) -> bool:
    url = f"{api_url}/healthcheck"
    for i in range(1, retries + 1):
        try:
            r = session.get(url, timeout=3)
            if r.status_code == 200:
                print_info("API Status:", f"✅ Online (attempt {i})", Colors.GREEN)
                return True
            else:
                print_info("API Status:", f"⚠️ {r.status_code} (attempt {i})", Colors.YELLOW)
        except Exception as e:
            print_info("API Status:", f"⏳ waiting ({i}) - {e}", Colors.YELLOW)
        time.sleep(delay)
    print(f"{Colors.RED}❌ Cannot reach API at {api_url}{Colors.END}")
    return False

# ----------------------------- ESTIMATOR -----------------------------
def run_estimator(session: requests.Session,
                  original_pdf: Path,
                  strategy: str,
                  api_url: str,
                  timeout: int,
                  ocr_languages: str,
                  estimate_pages: int,
                  save_raw: bool) -> Optional[Dict[str, Any]]:
    if estimate_pages <= 0:
        return None

    total_pages = count_pages(original_pdf)
    if not total_pages or total_pages <= estimate_pages:
        # Se non possiamo stimare o il file è più corto, saltiamo
        return None

    sample_path = extract_head_pdf(original_pdf, estimate_pages, out_dir=Path("samples"))
    if not sample_path or not sample_path.exists():
        return None

    print_header(f"🧪 Estimator: prime {estimate_pages} pagine → proiezione totale")
    res = test_extraction(session, sample_path, strategy, api_url, timeout, ocr_languages, save_raw, raw_dir=Path("responses"))
    if not res or not res.get("success"):
        print_info("Estimator:", "sample run failed, skipping projection", Colors.YELLOW)
        return None

    time_per_page_s = res["processing_time_seconds"] / estimate_pages
    est_total_seconds = time_per_page_s * total_pages
    est_total_minutes = est_total_seconds / 60.0
    est_total_hours = est_total_minutes / 60.0

    print_info("Pages (total):", total_pages, Colors.BLUE)
    print_info("Time/page (s):", f"{time_per_page_s:.2f}", Colors.BLUE)
    print_info("Estimated total (min):", f"{est_total_minutes:.2f}", Colors.BLUE)
    print_info("Estimated total (hours):", f"{est_total_hours:.2f}", Colors.BLUE)

    return {
        "sample_pages": estimate_pages,
        "total_pages": total_pages,
        "time_per_page_seconds": round(time_per_page_s, 3),
        "estimated_total_seconds": round(est_total_seconds, 2),
        "estimated_total_minutes": round(est_total_minutes, 2),
        "estimated_total_hours": round(est_total_hours, 3),
        "strategy": strategy,
        "ocr_languages": ocr_languages,
        "sample_file": str(sample_path)
    }

# ----------------------------- BENCHMARK LOOP -----------------------------
def run_benchmark(pdf_files: List[str],
                  strategies: List[str],
                  api_url: str = "http://localhost:8000",
                  warmup: bool = True,
                  timeout: int = 7200,
                  save_raw: bool = False,
                  ocr_languages: str = "ita+eng",
                  estimate_pages: int = 10) -> List[Dict[str, Any]]:

    print_header("🚀 UNSTRUCTURED EXTRACTION BENCHMARK")
    print_info("API URL:", api_url)
    print_info("Strategies:", ', '.join(strategies))
    print_info("Files:", len(pdf_files))
    print_info("OCR languages:", ocr_languages)

    session = requests.Session()

    if not wait_for_api(session, api_url):
        return []

    # Warm-up opzionale
    if warmup and pdf_files:
        print_header("🔥 Warm-up (non incluso nel report)")
        test_extraction(session, Path(pdf_files[0]), strategies[0], api_url, timeout=timeout, ocr_languages=ocr_languages, save_raw=save_raw)

    # Estimator opzionale: prima del run vero, solo sul primo file e prima strategia
    if estimate_pages and estimate_pages > 0 and pdf_files:
        try:
            _ = run_estimator(session,
                              original_pdf=Path(pdf_files[0]),
                              strategy=strategies[0],
                              api_url=api_url,
                              timeout=timeout,
                              ocr_languages=ocr_languages,
                              estimate_pages=estimate_pages,
                              save_raw=save_raw)
        except Exception as e:
            print_info("Estimator error:", str(e), Colors.YELLOW)

    # Run reale
    results: List[Dict[str, Any]] = []
    for i, pdf in enumerate(pdf_files, 1):
        print(f"\n{Colors.BOLD}Progress: {i}/{len(pdf_files)}{Colors.END}")
        p = Path(pdf)
        for strategy in strategies:
            r = test_extraction(session, p, strategy, api_url, timeout=timeout, ocr_languages=ocr_languages, save_raw=save_raw)
            if r:
                results.append(r)
            if r and r.get('success'):
                time.sleep(2)
    return results

# ----------------------------- REPORT -----------------------------
def print_final_report(results: List[Dict[str, Any]]):
    if not results:
        print(f"{Colors.RED}\nNo results to report{Colors.END}")
        return

    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]

    print_header("📊 FINAL BENCHMARK REPORT")
    print(f"{Colors.BOLD}Summary:{Colors.END}")
    print_info("Total tests:", len(results))
    print_info("Successful:", f"{len(successful)} ({(len(successful)/len(results)*100):.0f}%)",
               Colors.GREEN if successful else Colors.RED)
    print_info("Failed:", len(failed), Colors.RED if failed else Colors.GREEN)

    if not successful:
        return

    total_mb = sum(r['size_mb'] for r in successful)
    total_seconds = sum(r['processing_time_seconds'] for r in successful)
    total_pages = sum(r['pages'] for r in successful if r.get('pages') is not None)

    agg_mb_per_s = total_mb / total_seconds if total_seconds > 0 else 0
    agg_mb_per_min = agg_mb_per_s * 60
    agg_pages_per_min = (total_pages / (total_seconds / 60)) if total_pages and total_seconds > 0 else None

    print_info("Total size (MB):", f"{total_mb:.2f}", Colors.BLUE)
    if total_pages:
        print_info("Total pages:", total_pages, Colors.BLUE)
    print_info("Aggregate MB/s:", f"{agg_mb_per_s:.5f}", Colors.BLUE)
    print_info("Aggregate MB/min:", f"{agg_mb_per_min:.2f}", Colors.BLUE)
    if agg_pages_per_min:
        print_info("Aggregate pages/min:", f"{agg_pages_per_min:.2f}", Colors.BLUE)

    print(f"\n{Colors.BOLD}Detailed Results:{Colors.END}\n{'─'*110}")
    for r in successful:
        line = [
            f"File: {r['filename']}",
            f"{r['size_mb']:.2f} MB",
            f"Strategy: {r['strategy']}",
            f"Time: {r['processing_time_minutes']:.3f} min",
            f"MB/min: {r['speed_mb_per_minute']:.3f}",
        ]
        if r.get('pages'):
            line.append(f"Pages: {r['pages']}")
            if r.get('pages_per_minute') is not None:
                line.append(f"P/min: {r['pages_per_minute']:.3f}")
        print("  " + " | ".join(line))
        print('─'*110)

    avg_speed = sum(r['speed_mb_per_minute'] for r in successful) / len(successful)
    max_speed = max(r['speed_mb_per_minute'] for r in successful)
    min_speed = min(r['speed_mb_per_minute'] for r in successful)

    print(f"\n{Colors.BOLD}Statistics:{Colors.END}")
    print_info("Average MB/min:", f"{avg_speed:.3f}", Colors.GREEN)
    print_info("Max MB/min:", f"{max_speed:.3f}", Colors.GREEN)
    print_info("Min MB/min:", f"{min_speed:.3f}", Colors.YELLOW)

    daily_capacity_gb = (avg_speed * 60 * 24) / 1024
    print_info("Daily capacity (GB/day, 24/7):", f"{daily_capacity_gb:.2f}", Colors.BLUE)

# ----------------------------- SAVE REPORT -----------------------------
def save_report(results: List[Dict[str, Any]], filename: Optional[str] = None) -> str:
    if filename is None:
        filename = f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n{Colors.GREEN}✅ Report saved: {filename}{Colors.END}")
    return filename

# ----------------------------- CLI PARSING -----------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark Unstructured API")
    parser.add_argument("--files", nargs="*", help="Lista di file PDF (path completi)")
    parser.add_argument("--dir", help="Directory da scandire per *.pdf")
    parser.add_argument("--strategies", nargs="*", default=["fast", "hi_res"],
                        help="Strategie (default: fast hi_res)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL API")
    parser.add_argument("--timeout", type=int, default=7200,
                        help="Timeout per singola richiesta (secondi, default 7200)")
    parser.add_argument("--no-warmup", action="store_true", help="Disabilita warm-up")
    parser.add_argument("--output", help="Nome file JSON per il report")
    parser.add_argument("--no-color", action="store_true", help="Disabilita colori ANSI")
    parser.add_argument("--save-raw", action="store_true", help="Salva la risposta raw del server in ./responses")
    # Notifiche Telegram (opzionali; se non passati usa env)
    parser.add_argument("--telegram-token", help="Token Bot Telegram (o usa env TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--telegram-chat", help="Chat ID Telegram (o usa env TELEGRAM_CHAT_ID)")
    # OCR languages e estimator
    parser.add_argument("--ocr-languages", default="ita+eng",
                        help="Codici Tesseract separati da + (es: ita+eng). Default: ita+eng")
    parser.add_argument("--estimate", type=int, default=10,
                        help="Numero di pagine per la stima iniziale (0 per disabilitare). Default: 10")
    return parser.parse_args()

def collect_files(args) -> List[str]:
    files = set()
    if args.files:
        for f in args.files:
            p = Path(f)
            if p.exists() and p.suffix.lower() == ".pdf":
                files.add(str(p))
    if args.dir:
        d = Path(args.dir)
        if d.exists() and d.is_dir():
            for p in d.glob("*.pdf"):
                files.add(str(p))
    return sorted(files)

# ----------------------------- MAIN -----------------------------
def main():
    args = parse_args()
    if args.no_color:
        disable_colors()

    # Fallback a variabili d'ambiente se non passati
    telegram_token = args.telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = args.telegram_chat or os.environ.get("TELEGRAM_CHAT_ID")

    pdf_list = collect_files(args)
    if not pdf_list:
        print(f"{Colors.RED}❌ No PDF files provided/found!{Colors.END}")
        return

    results = run_benchmark(pdf_list,
                            strategies=args.strategies,
                            api_url=args.api_url,
                            warmup=not args.no_warmup,
                            timeout=args.timeout,
                            save_raw=args.save_raw,
                            ocr_languages=args.ocr_languages,
                            estimate_pages=args.estimate)

    print_final_report(results)
    report_file = None
    if results:
        report_file = save_report(results, filename=args.output)

    # Notifica Telegram se configurata
    if results and telegram_token and telegram_chat:
        last = results[-1]
        dur_min = last.get("processing_time_minutes")
        msg = (
            f"✅ Benchmark completato.\n"
            f"Test eseguiti: {len(results)}\n"
            f"Ultimo file: {last.get('filename')}\n"
            f"Strategia: {last.get('strategy')}\n"
            f"OCR: {args.ocr_languages}\n"
            f"Durata ultimo: {dur_min} min\n"
            f"Report: {report_file or 'N/D'}"
        )
        notify_telegram(telegram_token, telegram_chat, msg)
    elif results:
        print_info("Telegram:", "Token/chat non configurati – nessuna notifica.", Colors.YELLOW)

if __name__ == "__main__":
    main()