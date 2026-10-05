from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.scripts = []
        self.styles = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            assert attrs["id"] not in self.ids, f"duplicate id: {attrs['id']}"
            self.ids.add(attrs["id"])
        if tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet" and attrs.get("href"):
            self.styles.append(attrs["href"])

parser = Parser()
parser.feed((WEB / "index.html").read_text())
for asset in parser.scripts + parser.styles:
    if asset.startswith("/"):
        path = WEB / asset.lstrip("/")
        assert path.exists(), f"missing referenced asset: {asset}"
required = {"globe", "search-form", "journey-list", "departures-panel", "provider-items"}
missing = required - parser.ids
assert not missing, f"missing required UI ids: {sorted(missing)}"
print(f"Static UI validated: {len(parser.ids)} unique ids, {len(parser.scripts)+len(parser.styles)} referenced assets.")
