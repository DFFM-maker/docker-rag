"""
Script di benchmark per testare performance GPU vs CPU
per estrazione documenti PDF con Unstructured
"""
import requests
import time
import json
from pathlib import Path
from datetime import datetime
import sys

class Colors:
    """ANSI colors per output colorato"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}")
    print(f"{text:^70}")
    print(f"{'='*70}{Colors.END}\n")

def print_info(label, value, color=Colors.CYAN):
    print(f"{color}{label:30s}{Colors.END} {value}")

def test_extraction(pdf_path, strategy='hi_res', api_url="http://localhost:8000"):
    """
    Testa l'estrazione di un PDF con timing dettagliato
    """
    pdf_path = Path(pdf_path)
    
    if not pdf_path.exists():
        print(f"{Colors.RED}❌ File not found: {pdf_path}{Colors.END}")
        return None
    
    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)
    
    print_header(f"📄 Testing: {pdf_path.name}")
    print_info("File size:", f"{file_size_mb:.2f} MB")
    print_info("Strategy:", strategy)
    print_info("Start time:", datetime.now().strftime('%H:%M:%S'))
    
    # Endpoint da testare
    url = f"{api_url}/general/v0/general"
    
    start_time = time.time()
    
    try:
        with open(pdf_path, 'rb') as f:
            files = {'files': (pdf_path.name, f, 'application/pdf')}
            data = {
                'strategy': strategy,
                'extract_images_in_pdf': 'true',
                'pdf_infer_table_structure': 'true',
                'languages': 'ita,eng',
                'output_format': 'application/json'
            }
            
            print(f"\n{Colors.YELLOW}⏳ Processing...{Colors.END}")
            
            response = requests.post(
                url,
                files=files,
                data=data,
                timeout=7200  # 2 ore max
            )
        
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            
            # Estrai elementi (gestisci sia formato standard che con metadata)
            if 'elements' in result:
                elements = result['elements']
            else:
                elements = result
            
            if isinstance(elements, str):
                elements = json.loads(elements)
            
            elements_count = len(elements) if isinstance(elements, list) else 0
            
            # Calcola metriche
            speed_mb_per_min = file_size_mb / (elapsed / 60) if elapsed > 0 else 0
            speed_mb_per_hour = speed_mb_per_min * 60
            
            report = {
                'filename': pdf_path.name,
                'filepath': str(pdf_path),
                'size_mb': round(file_size_mb, 2),
                'strategy': strategy,
                'processing_time_seconds': round(elapsed, 2),
                'processing_time_minutes': round(elapsed / 60, 2),
                'processing_time_hours': round(elapsed / 3600, 4),
                'elements_count': elements_count,
                'speed_mb_per_minute': round(speed_mb_per_min, 2),
                'speed_mb_per_hour': round(speed_mb_per_hour, 2),
                'success': True,
                'timestamp': datetime.now().isoformat(),
                'status_code': response.status_code
            }
            
            # Output risultati
            print(f"\n{Colors.GREEN}✅ SUCCESS!{Colors.END}")
            print_info("Processing time:", f"{elapsed/60:.2f} min ({elapsed:.0f}s)", Colors.GREEN)
            print_info("Elements extracted:", f"{elements_count:,}", Colors.GREEN)
            print_info("Speed:", f"{speed_mb_per_min:.2f} MB/min", Colors.GREEN)
            print_info("Capacity:", f"{speed_mb_per_hour:.0f} MB/hour", Colors.GREEN)
            
            return report
            
        else:
            print(f"\n{Colors.RED}❌ ERROR: HTTP {response.status_code}{Colors.END}")
            print(f"Response: {response.text[:500]}")
            return {
                'filename': pdf_path.name,
                'success': False,
                'error': f"HTTP {response.status_code}",
                'response': response.text[:500]
            }
    
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"\n{Colors.RED}❌ TIMEOUT after {elapsed/60:.2f} minutes{Colors.END}")
        return {
            'filename': pdf_path.name,
            'success': False,
            'error': 'Timeout',
            'elapsed_minutes': elapsed / 60
        }
    
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n{Colors.RED}❌ EXCEPTION after {elapsed/60:.2f} minutes{Colors.END}")
        print(f"Error: {str(e)}")
        return {
            'filename': pdf_path.name,
            'success': False,
            'error': str(e),
            'elapsed_minutes': elapsed / 60
        }

def run_benchmark(pdf_files, strategies=['fast', 'hi_res'], api_url="http://localhost:8000"):
    """
    Esegue benchmark completo su lista di file
    """
    print_header("🚀 UNSTRUCTURED GPU BENCHMARK")
    print_info("API URL:", api_url)
    print_info("Strategies:", ', '.join(strategies))
    print_info("Files to test:", len(pdf_files))
    
    # Verifica connessione API
    try:
        response = requests.get(f"{api_url}/healthcheck", timeout=5)
        if response.status_code == 200:
            print_info("API Status:", "✅ Online", Colors.GREEN)
        else:
            print_info("API Status:", "⚠️  Warning", Colors.YELLOW)
    except:
        print(f"{Colors.RED}❌ Cannot connect to API at {api_url}{Colors.END}")
        return []
    
    all_results = []
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n{Colors.BOLD}Progress: {i}/{len(pdf_files)}{Colors.END}")
        
        for strategy in strategies:
            result = test_extraction(pdf_path, strategy, api_url)
            
            if result:
                all_results.append(result)
            
            # Pausa tra test per evitare sovraccarico
            if result and result.get('success'):
                time.sleep(3)
    
    return all_results

def print_final_report(results):
    """
    Stampa report finale con statistiche
    """
    if not results:
        print(f"\n{Colors.RED}No results to report{Colors.END}")
        return
    
    successful = [r for r in results if r.get('success')]
    
    print_header("📊 FINAL BENCHMARK REPORT")
    
    # Statistiche generali
    print(f"{Colors.BOLD}Summary:{Colors.END}")
    print_info("Total tests:", len(results))
    print_info("Successful:", f"{len(successful)} ({len(successful)/len(results)*100:.0f}%)", Colors.GREEN)
    print_info("Failed:", f"{len(results)-len(successful)}", Colors.RED if len(results)>len(successful) else Colors.GREEN)
    
    if not successful:
        return
    
    # Risultati dettagliati
    print(f"\n{Colors.BOLD}Detailed Results:{Colors.END}\n")
    print(f"{'─'*100}")
    
    for r in successful:
        print(f"\n{Colors.CYAN}File:{Colors.END} {r['filename']} ({r['size_mb']} MB)")
        print(f"  {Colors.CYAN}Strategy:{Colors.END} {r['strategy']}")
        print(f"  {Colors.CYAN}Time:{Colors.END} {r['processing_time_minutes']:.2f} min ({r['processing_time_hours']:.3f} hours)")
        print(f"  {Colors.CYAN}Speed:{Colors.END} {r['speed_mb_per_minute']:.2f} MB/min ({r['speed_mb_per_hour']:.0f} MB/hour)")
        print(f"  {Colors.CYAN}Elements:{Colors.END} {r['elements_count']:,}")
        print(f"{'─'*100}")
    
    # Statistiche aggregate
    print(f"\n{Colors.BOLD}Statistics:{Colors.END}\n")
    
    avg_speed = sum(r['speed_mb_per_minute'] for r in successful) / len(successful)
    max_speed = max(r['speed_mb_per_minute'] for r in successful)
    min_speed = min(r['speed_mb_per_minute'] for r in successful)
    
    print_info("Average speed:", f"{avg_speed:.2f} MB/min", Colors.GREEN)
    print_info("Max speed:", f"{max_speed:.2f} MB/min", Colors.GREEN)
    print_info("Min speed:", f"{min_speed:.2f} MB/min", Colors.YELLOW)
    
    # Calcola capacità giornaliera
    daily_capacity_gb = (avg_speed * 60 * 24) / 1024
    print_info("Daily capacity (24/7):", f"{daily_capacity_gb:.1f} GB/day", Colors.BLUE)

def save_report(results, filename=None):
    """
    Salva report in formato JSON
    """
    if filename is None:
        filename = f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, indent=2, fp=f, ensure_ascii=False)
    
    print(f"\n{Colors.GREEN}✅ Report saved: {filename}{Colors.END}")
    return filename

def main():
    """
    Main function
    """
    # Configura i tuoi file di test
    test_files = [
        r'D:\docker-rag\data\test_12mb.pdf',
        r'D:\docker-rag\data\test_15mb.pdf',
    ]
    
    # Filtra solo file esistenti
    existing_files = [f for f in test_files if Path(f).exists()]
    
    if not existing_files:
        print(f"{Colors.RED}❌ No test files found!{Colors.END}")
        print(f"\nPlease add your PDF files to test in the test_files list")
        print(f"Current files specified:")
        for f in test_files:
            print(f"  - {f} {'✅' if Path(f).exists() else '❌'}")
        return
    
    # Configura strategies da testare
    strategies = ['fast', 'hi_res']
    
    # URL API
    api_url = "http://localhost:8000"
    
    # Esegui benchmark
    results = run_benchmark(existing_files, strategies, api_url)
    
    # Report finale
    print_final_report(results)
    
    # Salva report
    if results:
        report_file = save_report(results)
        print(f"\n{Colors.BLUE}📄 Full report available in: {report_file}{Colors.END}")

if __name__ == "__main__":
    main()