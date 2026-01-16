# ClearanceVisualized

A tool to scrape, classify, and visualize DOHA Industrial Security Clearance Decisions using LLMs (gpt-4o) and Streamlit.

## Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure API Key**:
   Create a `.env` file in the root directory:
   ```ini
   OPENAI_API_KEY=sk-...
   ```

## Usage

### 1. Process Data
Run the scraping and classification workflow:
```bash
python main.py
```
- Select a year to download.
- The script handles downloading, PDF conversion, text formatting, and LLM classification.
- Output: `classified_cases_<YEAR>.csv`.

### 2. Visualize
Launch the interactive dashboard:
```bash
streamlit run dashboard.py
```