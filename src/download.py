import os
import sys
import time
import random
import json
from playwright.sync_api import sync_playwright

LINKS_FILE = 'extracted_links.txt'
OUTPUT_DIR = 'pdfs'
MANIFEST_FILE = 'manifest.json'

# User agents from download_pdfs.py to avoid 403s
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
]

def download_pdfs(links_file=LINKS_FILE, output_dir=OUTPUT_DIR):
    if not os.path.exists(links_file):
        print(f"Error: {links_file} not found.")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(links_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Found {len(urls)} links to process.")
    
    # Load existing manifest if any
    manifest_path = os.path.join(output_dir, MANIFEST_FILE)
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
        except:
            pass

    with sync_playwright() as p:
        # Launch browser
        print("Launching browser...")
        browser = p.chromium.launch(headless=True)
        
        # Create context with a real user agent
        user_agent = random.choice(USER_AGENTS)
        context = browser.new_context(accept_downloads=True, user_agent=user_agent)
        page = context.new_page()

        for i, url in enumerate(urls, 1):
            try:
                print(f"[{i}/{len(urls)}] Visiting: {url}")
                
                # Check if URL is already in manifest (and file exists)
                existing_filename = None
                for fname, furl in manifest.items():
                    if furl == url:
                        existing_filename = fname
                        break
                
                if existing_filename and os.path.exists(os.path.join(output_dir, existing_filename)):
                     print(f"   Skipping (already downloaded): {existing_filename}")
                     continue

                # Expect a download event
                try:
                    with page.expect_download(timeout=30000) as download_info:
                        # Navigate to URL. 
                        # We use a try-except here because if the server responds with a 
                        # file download immediately, navigate might raise an error or stay in 'loading' 
                        # but the download event will still fire.
                        try:
                            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        except Exception as nav_e:
                            # Verify if it was just a navigation abort due to download
                            pass 

                    download = download_info.value
                    filename = download.suggested_filename
                    
                    # Sanitize output filename
                    if not filename:
                        filename = f"doc_{i}.pdf"
                    
                    filepath = os.path.join(output_dir, filename)

                    # Check for duplicates or existing files
                    if os.path.exists(filepath):
                        print(f"   Skipping (exists): {filename}")
                    else:
                        download.save_as(filepath)
                        print(f"   Downloaded: {filename}")
                    
                    # Update manifest
                    manifest[filename] = url
                    with open(manifest_path, 'w') as mf:
                        json.dump(manifest, mf, indent=2)

                except Exception as dl_error:
                    print(f"   Download failed: {dl_error}")

                # Sleep briefly to avoid rate limiting
                time.sleep(1)

            except Exception as e:
                print(f"   Error processing {url}: {e}")

        browser.close()
        print("Done.")

if __name__ == "__main__":
    download_pdfs()
