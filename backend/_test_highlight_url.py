import sys
from gallery_dl import extractor

urls = [
    "https://www.instagram.com/annykim__/",
    "https://www.instagram.com/annykim__/highlights",
    "https://www.instagram.com/annykim__/highlights/ABC123xyz",
]
for u in urls:
    ex = extractor.find(u)
    name = type(ex).__name__ if ex else None
    sub = getattr(ex, "subcategory", None)
    print(f"{u}\n  -> {name} sub={sub}")
