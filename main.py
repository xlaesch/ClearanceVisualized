import os
import sys
import re
import argparse
import random
import time
import urllib.parse
from html.parser import HTMLParser
from playwright.sync_api import sync_playwright

# Import modules from src
from src import extract, download, convert, format, classify

ROOT_URL = "https://doha.ogc.osd.mil/Industrial-Security-Program/Industrial-Security-Clearance-Decisions/ISCR-Hearing-Decisions/"

def setup_api_key():
    # Check .env
    env_path = ".env"
    api_key = None
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("OPENAI_API_KEY="):
                    parts = line.strip().split("=", 1)
                    if len(parts) > 1:
                        api_key = parts[1]
                    break
    
    if not api_key and "OPENAI_API_KEY" in os.environ:
        api_key = os.environ["OPENAI_API_KEY"]

    if not api_key:
        print("OpenAI API Key not found.")
        key = input("Please enter your OpenAI API Key: ").strip()
        if key:
            with open(env_path, "a") as f:
                f.write(f"\nOPENAI_API_KEY={key}\n")
            print(f"Saved key to {env_path}")
            os.environ["OPENAI_API_KEY"] = key
        else:
            print("No key provided. Classification step might fail.")

def fetch_html(url):
    print(f"Fetching {url} using Playwright...")
    # User agents to rotate
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
    ]
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=random.choice(user_agents))
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
            content = page.content()
            return content
        except Exception as e:
            print(f"Playwright error: {e}")
            raise
        finally:
            browser.close()

class YearParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.years = []
        self.in_link = False
        self.current_href = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs = dict(attrs)
            if 'href' in attrs:
                self.current_href = attrs['href']
                self.in_link = True

    def handle_endtag(self, tag):
        if tag == 'a':
            self.in_link = False
            self.current_href = None

    def handle_data(self, data):
        if self.in_link:
            match = re.search(r'\b(20\d{2})\b', data)
            if match:
                self.years.append((match.group(1), self.current_href))
            elif self.current_href and re.search(r'20\d{2}', self.current_href):
                 match = re.search(r'(20\d{2})', self.current_href)
                 if match:
                     self.years.append((match.group(1), self.current_href))

def select_year():
    try:
        html = fetch_html(ROOT_URL)
    except Exception as e:
        print(f"Failed to fetch root URL: {e}")
        return None, None

    parser = YearParser()
    parser.feed(html)
    
    # Deduplicate with priority for ISCR links
    seen_years = set()
    unique_years = []
    
    # List of (year, link, priority)
    candidates = []
    for y, link in set(parser.years):
        priority = 0
        if "ISCR" in link or "iscr" in link.lower():
            priority = 1
        candidates.append((y, link, priority))
    
    # Sort by Year DESC, then Priority DESC
    # reverse=True means larger values come first.
    candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)
    
    for y, link, prio in candidates:
        if y not in seen_years:
            unique_years.append((y, link))
            seen_years.add(y)
            
    if not unique_years:
        print("Could not find any year links.")
        return None, None

    print("\nAvailable Years:")
    for i, (year, link) in enumerate(unique_years, 1):
        print(f"{i}. {year}")

    choice = input("\nSelect a year (number): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(unique_years):
            selected_year, relative_link = unique_years[idx]
            if relative_link.startswith("http"):
                 full_link = relative_link
            else:
                 full_link = urllib.parse.urljoin(ROOT_URL, relative_link)
            return selected_year, full_link
    except ValueError:
        pass
    
    print("Invalid selection.")
    return None, None

def main():
    setup_api_key()
    
    year, year_url = select_year()
    if not year:
        print("No year selected. Exiting.")
        return

    print(f"\nProcessing Year: {year}")
    print(f"URL: {year_url}")

    # Directories
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    
    site_source_dir = os.path.join(data_dir, "site_source", year)
    os.makedirs(site_source_dir, exist_ok=True)
    
    pdfs_dir = os.path.join(data_dir, "pdfs", year)
    txt_dir = os.path.join(data_dir, "txt", year)
    txt_formatted_dir = os.path.join(data_dir, "txt_formatted", year)
    
    # 1. Download Source
    source_file = os.path.join(site_source_dir, "index.html")
    if not os.path.exists(source_file):
        try:
            html_content = fetch_html(year_url)
            with open(source_file, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"Saved source to {source_file}")
        except Exception as e:
            print(f"Failed to download source: {e}")
            return
    else:
        print(f"Source already exists at {source_file}")

    # 2. Extract Links
    links_file = os.path.join(site_source_dir, "links.txt")
    print(f"Extracting links from {source_file}...")
    
    raw_links = extract.extract_links(source_file, output_file=None)
    
    valid_links = []
    for text, href in raw_links:
        href = href.strip()
        text = text.strip()
        
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        
        is_pdf = False
        if href.lower().endswith(".pdf"):
            is_pdf = True
        elif text.lower().endswith(".pdf"):
            is_pdf = True
        elif "FileId" in href and ".pdf" in text.lower():
             is_pdf = True

        if is_pdf:
             full_url = urllib.parse.urljoin(year_url, href)
             valid_links.append(full_url)
    
    valid_links = sorted(list(set(valid_links)))
    print(f"Found {len(valid_links)} PDF links.")
    
    with open(links_file, "w", encoding="utf-8") as f:
        for link in valid_links:
            f.write(link + "\n")

    # 3. Download PDFs
    print(f"Downloading PDFs to {pdfs_dir}...")
    download.download_pdfs(links_file, pdfs_dir)

    # 4. Convert to TXT
    print("Converting PDFs to TXT...")
    convert.run(input_path=pdfs_dir, output_path=txt_dir)

    # 5. Format TXT
    print("Formatting TXT files...")
    format.run(input_path=txt_dir, output_path=txt_formatted_dir)

    # 6. Classify
    print("Classifying cases...")
    output_csv = f"classified_cases_{year}.csv"
    manifest_path = os.path.join(pdfs_dir, "manifest.json")
    
    # classify.py expects argv list because full refactor was skipped to avoid errors
    classify_argv = [
        "--input", txt_formatted_dir,
        "--output", output_csv,
        "--manifest", manifest_path
    ]
    
    try:
        classify.run(classify_argv)
    except SystemExit:
        pass # classify.run might exit(0) on success

    print(f"\nWorkflow complete! Check {output_csv}")

if __name__ == "__main__":
    main()
