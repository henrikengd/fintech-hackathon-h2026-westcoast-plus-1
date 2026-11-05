"""Extract source-linked filing passages for the local, exploratory RAG index.

Offsets address the canonical extracted text, not the original HTML bytes.
Vote outcomes and rationales are never copied into this corpus.
"""
import bisect
import csv
from datetime import date, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "data" / "meetings" / "us.csv"
VOTES = ROOT / "data" / "real_votes.csv"
BLOCKS = {"p", "div", "section", "article", "li", "blockquote", "pre", "table", "ul", "ol"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
HIDDEN = {"head", "script", "style", "noscript", "template", "ix:hidden", "ix:header", "svg"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class FilingParser(HTMLParser):
    """Keep visible paragraph and table-row boundaries without an HTML dependency."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = []
        self.blocks = []
        self.heading = ""

    @property
    def hidden(self):
        return bool(self.stack and self.stack[-1][1])

    @property
    def in_row(self):
        return any(tag == "tr" for tag, _ in self.stack)

    def flush(self, heading=False):
        text = " ".join("".join(self.parts).split()).strip(" |")
        self.parts.clear()
        if text:
            if heading:
                self.heading = text
            self.blocks.append({"text": text, "heading": self.heading})

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        style = attrs.get("style", "").lower()
        hidden = self.hidden or tag in HIDDEN or "hidden" in attrs or attrs.get("aria-hidden", "").lower() == "true"
        hidden = hidden or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)\b", style))
        if not hidden:
            if tag in HEADINGS or tag == "tr" or (tag in BLOCKS and not self.in_row):
                self.flush()
            elif tag in {"td", "th"} and self.parts:
                self.parts.append(" | ")
            elif tag in {"br", "hr"} or (tag in BLOCKS and self.in_row):
                self.parts.append(" ")
        if tag not in VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        hidden = self.hidden
        if not hidden:
            if tag in HEADINGS:
                self.flush(heading=True)
            elif tag == "tr" or (tag in BLOCKS and not self.in_row):
                self.flush()
            elif tag in BLOCKS and self.in_row:
                self.parts.append(" ")
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract_html(raw):
    """Return canonical visible text and blocks with exact text offsets."""
    parser = FilingParser()
    parser.feed(raw)
    parser.close()
    parser.flush()
    blocks, pieces, offset = [], [], 0
    for block in parser.blocks:
        start = offset
        pieces.append(block["text"])
        offset += len(block["text"])
        blocks.append({**block, "start": start, "end": offset})
        offset += 2
    return "\n\n".join(pieces), blocks


def chunk_document(document, blocks, target_words=180, overlap_words=30):
    """Prefer paragraph ends; split long paragraphs with a small word overlap."""
    if target_words < 2 or not 0 <= overlap_words < target_words:
        raise ValueError("Chunk size must exceed overlap and be at least two words")
    text = document["text"]
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    ends = [word.end() for word in words]
    paragraph_ends = sorted({bisect.bisect_right(ends, block["end"]) for block in blocks})
    block_starts = [block["start"] for block in blocks]
    metadata = {key: value for key, value in document.items() if key not in {"id", "text"}}
    result, first = [], 0
    while first < len(words):
        desired = min(first + target_words, len(words))
        candidates = [end for end in paragraph_ends if first + max(overlap_words + 1, target_words // 2) <= end <= desired]
        last = max(candidates) if candidates and desired < len(words) else desired
        start, end = words[first].start(), words[last - 1].end()
        excerpt = text[start:end]
        block_index = max(0, bisect.bisect_right(block_starts, start) - 1)
        identity = f"{document['id']}:{start}:{end}:{excerpt}".encode("utf-8")
        result.append({
            **metadata, "id": sha256(identity).hexdigest()[:24], "document_id": document["id"],
            "text": excerpt, "start": start, "end": end,
            "heading": blocks[block_index]["heading"] if blocks else "",
        })
        if last == len(words):
            break
        first = max(first + 1, last - overlap_words)
    return result


def _meeting_metadata(votes_csv):
    meetings = {}
    with Path(votes_csv).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"meeting_id", "company_id", "company", "meeting_date"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError("Vote source lacks meeting metadata columns")
        for row in reader:
            # Deliberate allowlist. Outcomes/rationale must not become retrieval context.
            item = {name: row[name] for name in sorted(required)}
            previous = meetings.setdefault(item["meeting_id"], item)
            if previous != item:
                raise ValueError(f"Conflicting metadata for meeting {item['meeting_id']}")
    return meetings


def build_corpus(index_csv=INDEX, votes_csv=VOTES, year="2024", meeting_ids=None):
    """Read dated filings. Explicit meeting IDs override the default year filter.

    Only documents filed strictly before the meeting-minus-five-days cutoff enter
    the corpus. Missing or unusable sources are recorded rather than fabricated.
    """
    index_csv = Path(index_csv).resolve()
    base = index_csv.parent
    meetings = _meeting_metadata(votes_csv)
    selected = None if meeting_ids is None else {str(value) for value in meeting_ids}
    documents, chunks, skipped, seen = [], [], [], set()
    with index_csv.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"meeting_id", "meeting_date", "filed", "file", "url"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError("Filing index lacks source metadata columns")
        rows = sorted(reader, key=lambda row: (row["meeting_date"], row["meeting_id"], row["file"]))
    for row in rows:
        meeting_id = row["meeting_id"]
        if selected is not None:
            if meeting_id not in selected:
                continue
        elif year is not None and not row["meeting_date"].startswith(str(year) + "-"):
            continue
        marker = {"meeting_id": meeting_id, "file": row["file"]}
        if meeting_id in seen:
            skipped.append({**marker, "reason": "duplicate filing-index meeting"})
            continue
        seen.add(meeting_id)
        meta = meetings.get(meeting_id)
        if not meta or not meta["company_id"] or not meta["company"] or meta["meeting_date"] != row["meeting_date"]:
            skipped.append({**marker, "reason": "missing or inconsistent meeting metadata"})
            continue
        try:
            meeting_day = date.fromisoformat(row["meeting_date"])
            filed = date.fromisoformat(row["filed"])
        except ValueError:
            skipped.append({**marker, "reason": "invalid filing or meeting date"})
            continue
        if filed >= meeting_day - timedelta(days=5):
            skipped.append({**marker, "reason": "filing not available before decision cutoff"})
            continue
        path = (base / row["file"]).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            skipped.append({**marker, "reason": "source file missing or outside source directory"})
            continue
        raw = path.read_bytes()
        text, blocks = extract_html(raw.decode("utf-8-sig", errors="replace"))
        if not text.strip():
            skipped.append({**marker, "reason": "source contains no visible text"})
            continue
        content_hash = sha256(raw).hexdigest()
        identity = f"{meeting_id}:{meta['company_id']}:{row['meeting_date']}:{row['filed']}:{row['url']}:{content_hash}"
        document = {
            **meta, "id": sha256(identity.encode("utf-8")).hexdigest()[:24],
            "filed": row["filed"], "url": row["url"], "file": str(path),
            "sha256": content_hash, "text": text,
        }
        documents.append(document)
        chunks.extend(chunk_document(document, blocks))
    if selected is not None:
        skipped.extend({"meeting_id": value, "file": "", "reason": "meeting not in filing index"} for value in sorted(selected - seen))
    return {"documents": documents, "chunks": chunks, "skipped": skipped}
