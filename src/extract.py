import re
import sys
from html.parser import HTMLParser

class HrefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = [] # List of (text, href)
        self._current_href = None
        self._current_text = []
        self._in_anchor = False

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self._in_anchor = True
            attrs = dict(attrs)
            self._current_href = attrs.get('href', '').strip()
            self._current_text = []

    def handle_endtag(self, tag):
        if tag == 'a':
            self._in_anchor = False
            if self._current_href:
                text = " ".join(self._current_text).strip()
                self.links.append((text, self._current_href))
            self._current_href = None

    def handle_data(self, data):
        if self._in_anchor:
            self._current_text.append(data.strip())

def extract_links(html_file, output_file=None):
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {html_file} not found.")
        sys.exit(1)

    parser = HrefParser()
    try:
        parser.feed(content)
    except Exception as e:
        print(f"Warning: HTML parsing error: {e}")

    # Return list of (text, url)
    links = parser.links
    
    if output_file:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for text, link in links:
                    # simplistic representation for text file
                    f.write(f"{link}\t{text}\n")
            print(f"Successfully extracted {len(links)} links to {output_file}")
        except Exception as e:
            print(f"Error writing to {output_file}: {e}")
    
    return links

if __name__ == "__main__":
    # Input file is links.txt (containing HTML), output is extracted_links.txt
    extract_links('links.txt', 'extracted_links.txt')
