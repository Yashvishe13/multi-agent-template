## SEARCH SKILL

This guide covers web search operations using Exa API (primary) with DuckDuckGo fallback. The search functionality supports batched queries, category filtering, and full text content extraction.

## Quick Start

```python
import os
from exa_py import Exa

# Initialize client
exa = Exa(api_key=os.environ.get("EXA_API_KEY"))

# Simple search
results = exa.search(
    query="Python web scraping best practices",
    type="auto",
    num_results=10,
    contents={"text": {"max_characters": 20000}}
)

for result in results.results:
    print(f"{result.title}: {result.url}")
```

## Dependencies

Install required packages:

```bash
pip install exa-py duckduckgo-search python-dotenv
```

## Search Methods

### Exa Search (Primary)

Exa provides high-quality neural search with full content extraction.

#### Basic Search
```python
from exa_py import Exa
import os

exa = Exa(api_key=os.environ.get("EXA_API_KEY"))

results = exa.search(
    query="machine learning tutorials",
    type="auto",
    num_results=10,
    contents={"text": {"max_characters": 20000}}
)

for result in results.results:
    print(f"Title: {result.title}")
    print(f"URL: {result.url}")
    print(f"Text: {result.text[:500]}...")
    print("---")
```

#### Category-Filtered Search
```python
# Search for news articles
news_results = exa.search(
    query="AI developments 2024",
    type="auto",
    num_results=10,
    category="news",
    contents={"text": {"max_characters": 20000}}
)

# Search for research papers
paper_results = exa.search(
    query="transformer architecture",
    type="auto",
    num_results=10,
    category="research paper",
    contents={"text": {"max_characters": 20000}}
)

# Search for company information
company_results = exa.search(
    query="OpenAI",
    type="auto",
    num_results=10,
    category="company",
    contents={"text": {"max_characters": 20000}}
)
```

### DuckDuckGo Search (Fallback)

Free fallback option when Exa is unavailable.

```python
from duckduckgo_search import DDGS

with DDGS() as ddgs:
    results = list(ddgs.text("Python tutorials", max_results=10))

for result in results:
    print(f"Title: {result['title']}")
    print(f"URL: {result['href']}")
    print(f"Snippet: {result['body']}")
    print("---")
```

## Batched Searches

Perform multiple searches in one call:

```python
queries = [
    "Python web frameworks comparison",
    "FastAPI vs Flask performance",
    "Django best practices 2024"
]

all_results = []
for query in queries:
    results = exa.search(
        query=query,
        type="auto",
        num_results=5,
        contents={"text": {"max_characters": 10000}}
    )
    all_results.append({
        "query": query,
        "results": results.results
    })
```

```python
from skills.search.scripts.web_search import WebSearch

# Initialize searcher
searcher = WebSearch()

# Single search
result = searcher.search("Python async programming")
print(result)

# Batched search
results = searcher.batch_search([
    "Python async programming",
    "asyncio best practices"
])
print(results)

# Category search (Exa only)
news = searcher.search("AI news", category="news")
print(news)
```

## Common Tasks

### Search and Extract Key Information
```python
def search_and_summarize(query: str, num_results: int = 5) -> list:
    """Search and extract key information from results."""
    results = exa.search(
        query=query,
        type="auto",
        num_results=num_results,
        contents={"text": {"max_characters": 5000}}
    )
    
    summaries = []
    for r in results.results:
        summaries.append({
            "title": r.title,
            "url": r.url,
            "published": getattr(r, 'published_date', None),
            "excerpt": r.text[:500] if r.text else ""
        })
    return summaries
```

### Search with Date Filtering
```python
from datetime import datetime, timedelta

# Search for recent content (last 7 days)
week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

results = exa.search(
    query="latest Python releases",
    type="auto",
    num_results=10,
    start_published_date=week_ago,
    contents={"text": {"max_characters": 20000}}
)
```

## Quick Reference

| Task | Method | Example |
|------|--------|---------|
| Basic search | `exa.search()` | `exa.search(query="...", num_results=10)` |
| Category filter | `category` param | `category="news"` |
| Full text | `contents` param | `contents={"text": {"max_characters": 20000}}` |
| Date filter | `start_published_date` | `start_published_date="2024-01-01"` |
| Fallback search | DuckDuckGo | `ddgs.text(query, max_results=10)` |

## Error Handling

```python
def safe_search(query: str) -> str:
    """Search with automatic fallback."""
    try:
        # Try Exa first
        if exa_client:
            return exa_search(query)
    except Exception as e:
        print(f"Exa failed: {e}, falling back to DuckDuckGo")
    
    # Fallback to DuckDuckGo
    return duckduckgo_search(query)
```