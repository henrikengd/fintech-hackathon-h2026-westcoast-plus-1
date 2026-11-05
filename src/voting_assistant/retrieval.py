"""Build and search a deterministic local index of dated policy sections."""

from collections import Counter
from datetime import date
from hashlib import blake2b, sha256
import json
from math import sqrt
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationError

from voting_assistant.cli import CliError
from voting_assistant.contracts import Contract, Guideline, NonEmpty, Sha256, Source


EMBEDDING_MODEL = "hashed-word-count-262144-v1"
MAX_QUERY_LENGTH = 1500
MAX_RESULTS = 10
_STOP_WORDS = set(
    "a an the on in at for to or of as by with from is are this that we will "
    "can and about should proposal proposals company companies meeting "
    "support vote voting shareholder shareholders".split()
)
_ALIASES = {
    "auditors": "auditor",
    "directors": "director",
    "elections": "election",
    "revisor": "auditor",
    "revisorvalg": "auditor appointment",
    "styrevalg": "board director election",
    "godtgjørelse": "remuneration",
    "lederlønn": "ceo remuneration",
    "vedtekter": "governing documents",
    "aksjeutstedelse": "share issuance",
}
CorpusKind = Literal["nbim", "synthetic"]


class SectionSpec(Contract):
    guideline_id: NonEmpty
    section: NonEmpty
    page: int = Field(ge=1)
    end_page: int | None = Field(default=None, ge=1)
    start: NonEmpty
    stop: NonEmpty | None = None


class DocumentSpec(Contract):
    document: NonEmpty
    path: Path
    url: NonEmpty | None = None
    policy_version: NonEmpty
    document_date: date
    sha256: Sha256
    valid_from: date
    valid_until: date | None = None
    body_width: int | None = Field(default=None, ge=1)
    body_height: int | None = Field(default=None, ge=1)
    sections: list[SectionSpec] = Field(min_length=1)


class PolicyManifest(Contract):
    corpus_kind: CorpusKind
    documents: list[DocumentSpec] = Field(min_length=1)


class IndexEntry(Contract):
    guideline: Guideline
    vector: dict[int, int]


class IndexData(Contract):
    schema_version: Literal[1] = 1
    embedding_model: Literal["hashed-word-count-262144-v1"] = EMBEDDING_MODEL
    corpus_kind: CorpusKind
    index_version: Sha256
    entries: list[IndexEntry] = Field(min_length=1)


def _tokens(text: str) -> list[str]:
    return [
        token
        for word in re.findall(r"[^\W_]+", text.casefold())
        for token in _ALIASES.get(word, word).split()
        if token not in _STOP_WORDS and len(token) > 1
    ]


def _vector(tokens: list[str]) -> dict[int, int]:
    return dict(Counter(
        int.from_bytes(blake2b(token.encode("utf-8"), digest_size=8).digest(), "big") % 262144
        for token in tokens
    ))


def _norm(vector: dict[int, int]) -> float:
    return sqrt(sum(value * value for value in vector.values()))


def _index_version(entries: list[IndexEntry], corpus_kind: CorpusKind) -> str:
    content = {
        "schema_version": 1,
        "embedding_model": EMBEDDING_MODEL,
        "corpus_kind": corpus_kind,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }
    payload = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _read_pages(document: DocumentSpec, directory: Path) -> list[str]:
    path = directory / document.path
    try:
        content = path.read_bytes()
    except OSError:
        raise CliError(f"Kan ikke lese regeldokumentet {document.path.name}") from None
    if sha256(content).hexdigest() != document.sha256:
        raise CliError(f"Feil SHA-256 for {document.path.name}")
    if path.suffix.lower() == ".pdf":
        command = ["pdftotext", "-layout", "-enc", "UTF-8"]
        if document.body_width is not None:
            command.extend(["-W", str(document.body_width)])
        if document.body_height is not None:
            command.extend(["-H", str(document.body_height)])
        try:
            content = subprocess.run(
                [*command, "-", "-"], input=content, capture_output=True,
                check=True, timeout=30,
            ).stdout
        except FileNotFoundError:
            raise CliError("Installer Poppler (pdftotext) for å indeksere PDF-filer") from None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            raise CliError(f"Kunne ikke hente tekst fra {document.path.name}") from None
    elif path.suffix.lower() != ".txt":
        raise CliError("Regeldokumentet må være en PDF eller UTF-8-tekst")
    try:
        return content.decode("utf-8").removesuffix("\f").split("\f")
    except UnicodeError:
        raise CliError(f"Teksten i {document.path.name} er ikke gyldig UTF-8") from None


def _marker(lines: list[str], marker: str, section: str) -> int:
    positions = [i for i, line in enumerate(lines) if line.strip() == marker]
    if len(positions) != 1:
        raise CliError(f"Finner ikke entydig avsnittsgrense for {section}: {marker}")
    return positions[0]


def _section_text(pages: list[str], section: SectionSpec) -> str:
    end = section.end_page or section.page
    if end < section.page or end > len(pages):
        raise CliError(f"Ugyldig sideintervall for {section.section}")
    first_lines = pages[section.page - 1].splitlines()
    start = _marker(first_lines, section.start, section.section)
    if end == section.page:
        lines = first_lines[start:]
    else:
        lines = first_lines[start:]
        for page in pages[section.page:end]:
            lines.extend(["", *page.splitlines()])
    if section.stop is not None:
        lines = lines[:_marker(lines, section.stop, section.section)]
    if not any(line.strip() for line in lines[1:]):
        raise CliError(f"Avsnittet {section.section} mangler regeltekst")
    return "\n".join(line.replace("\a", "").rstrip() for line in lines).strip()


def _make_entries(manifest: PolicyManifest, directory: Path) -> list[IndexEntry]:
    entries = []
    for document in manifest.documents:
        if manifest.corpus_kind == "nbim":
            try:
                url = urlsplit(document.url or "")
            except ValueError:
                raise CliError("NBIM-manifestet krever en gyldig dokumentlenke") from None
            if (
                document.path.suffix.lower() != ".pdf" or url.scheme != "https"
                or url.netloc not in {"nbim.no", "www.nbim.no"}
            ):
                raise CliError("NBIM-manifestet krever PDF og offisiell HTTPS-lenke fra nbim.no")
        if document.document_date > document.valid_from:
            raise CliError(f"Gyldighetsstart er før dokumentdato for {document.document}")
        pages = _read_pages(document, directory)
        for section in document.sections:
            guideline = Guideline(
                guideline_id=section.guideline_id,
                text=_section_text(pages, section),
                policy_version=document.policy_version,
                valid_from=document.valid_from,
                valid_until=document.valid_until,
                section=section.section,
                source=Source(
                    document=document.document,
                    url=document.url,
                    section=section.section,
                    page=section.page,
                    document_date=document.document_date,
                    version=document.policy_version,
                    sha256=document.sha256,
                ),
            )
            vector = _vector(_tokens(guideline.text) + 3 * _tokens(guideline.section))
            entries.append(IndexEntry(guideline=guideline, vector=vector))
    return sorted(entries, key=lambda entry: (entry.guideline.guideline_id, entry.guideline.policy_version))


class PolicyIndex:
    def __init__(self, data: IndexData):
        if _index_version(data.entries, data.corpus_kind) != data.index_version:
            raise CliError("Regelindeksen stemmer ikke med kontrollsummen. Bygg indeksen på nytt.")
        self.index_version = data.index_version
        self.embedding_model = data.embedding_model
        self.corpus_kind = data.corpus_kind
        self._entries = data.entries
        self._terms = [
            set(_tokens(f"{entry.guideline.text} {entry.guideline.section}"))
            for entry in self._entries
        ]
        self._norms = [_norm(entry.vector) for entry in self._entries]
        self._by_id: dict[str, dict[str, Guideline]] = {}
        for entry in self._entries:
            guideline = entry.guideline
            versions = self._by_id.setdefault(guideline.guideline_id, {})
            if guideline.policy_version in versions:
                raise CliError(f"Duplikat av regel {guideline.guideline_id} og versjon")
            if any(
                (old.valid_until is None or guideline.valid_from < old.valid_until)
                and (guideline.valid_until is None or old.valid_from < guideline.valid_until)
                for old in versions.values()
            ):
                raise CliError(f"Overlappende versjoner av regel {guideline.guideline_id}")
            versions[guideline.policy_version] = guideline

    @classmethod
    def load(cls, path: Path) -> "PolicyIndex":
        try:
            return cls(IndexData.model_validate_json(path.read_bytes()))
        except (OSError, ValidationError):
            raise CliError("Kan ikke lese regelindeksen. Kjør index med et gyldig manifest.") from None

    def valid_guidelines(self, as_of_date: date) -> list[Guideline]:
        return [entry.guideline for entry in self._entries if entry.guideline.applies_on(as_of_date)]

    def search(self, query: str, as_of_date: date, limit: int = 5) -> dict:
        if not 1 <= limit <= MAX_RESULTS or len(query) > MAX_QUERY_LENGTH:
            return {"status": "invalid_query", "results": []}
        valid = [(i, entry) for i, entry in enumerate(self._entries)
                 if entry.guideline.applies_on(as_of_date)]
        if not valid:
            return {"status": "no_valid_version", "results": []}
        terms = _tokens(query)
        term_set = set(terms)
        vector = _vector(terms)
        norm = _norm(vector)
        matches = []
        for i, entry in valid:
            if not (self._terms[i] & term_set) or not self._norms[i]:
                continue
            dot = sum(value * entry.vector.get(token, 0) for token, value in vector.items())
            score = dot / (norm * self._norms[i])
            matches.append((score, entry.guideline))
        matches.sort(key=lambda match: (-match[0], match[1].guideline_id))
        return {
            "status": "ok" if matches else "no_matching_rules",
            "results": [
                rule.model_dump(mode="json") | {"score": round(score, 6)}
                for score, rule in matches[:limit]
            ],
        }

    def get(self, guideline_id: str, policy_version: str) -> dict:
        versions = self._by_id.get(guideline_id)
        if versions is None:
            return {"status": "unknown_guideline", "guideline": None}
        rule = versions.get(policy_version)
        if rule is None:
            return {"status": "unknown_version", "guideline": None}
        return {"status": "ok", "guideline": rule.model_dump(mode="json")}


def build_index(args) -> int:
    try:
        manifest = PolicyManifest.model_validate_json(args.manifest.read_bytes())
        inputs = {args.manifest.resolve()} | {
            (args.manifest.parent / document.path).resolve()
            for document in manifest.documents
        }
        if args.output.resolve() in inputs:
            raise CliError("Regelindeksen må skrives til en egen fil")
        entries = _make_entries(manifest, args.manifest.parent)
        data = IndexData(
            index_version=_index_version(entries, manifest.corpus_kind),
            corpus_kind=manifest.corpus_kind,
            entries=entries,
        )
        PolicyIndex(data)
    except (OSError, ValidationError):
        raise CliError("Kan ikke lese eller validere manifestet for regeldokumenter") from None
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=args.output.parent, mode="w", encoding="utf-8", delete=False
        ) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(data.model_dump_json(indent=2) + "\n")
                handle.close()
                temporary.replace(args.output)
            finally:
                temporary.unlink(missing_ok=True)
    except OSError:
        raise CliError("Kan ikke skrive regelindeksen") from None
    print(f"Indekserte {len(entries)} regelavsnitt. Indeksversjon: {data.index_version}")
    return 0
