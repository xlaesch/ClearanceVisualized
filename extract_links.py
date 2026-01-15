import re
import sys
from html.parser import HTMLParser

class HrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs = dict(attrs)
            if 'href' in attrs:
                self.urls.append(attrs['href'])

def extract_links(html_file, output_file):
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {html_file} not found.")
        sys.exit(1)

    parser = HrefParser()
    parser.feed(content)
    
    # Filter out empty or whitespace-only links
    links = [u.strip() for u in parser.urls if u.strip()]
    
    # Write to output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for link in links:
                f.write(link + '\n')
        print(f"Successfully extracted {len(links)} links to {output_file}")
    except Exception as e:
        print(f"Error writing to {output_file}: {e}")

if __name__ == "__main__":
    # Input file is links.txt (containing HTML), output is extracted_links.txt
    extract_links('links.txt', 'extracted_links.txt')
