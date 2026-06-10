"""Validazione strutturale del layout v2."""
import json
from pathlib import Path

from book_twin.converters import read_book
from book_twin.indexer import build_index
from book_twin.repository import create_book_repository
from book_twin.status import load_status
from book_twin.validation import validate_twin

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_book.md"


def _twin(tmp_path: Path) -> Path:
    text, pages, meta = read_book(SAMPLE)
    out = tmp_path / "twin"
    create_book_repository(source_path=SAMPLE, out_dir=out, language="it",
                           full_text=text, pages=pages, metadata=meta, force=True)
    build_index(out, embeddings=False)
    return out


def test_validate_passes_on_fresh_ingest(tmp_path):
    out = _twin(tmp_path)
    report = validate_twin(out)
    assert report.ok, report.render()


def test_validate_fails_on_missing_status(tmp_path):
    out = _twin(tmp_path)
    (out / "STATUS.json").unlink()
    report = validate_twin(out)
    assert not report.ok


def test_validate_detects_orphan_chunks(tmp_path):
    out = _twin(tmp_path)
    p = out / "knowledge" / "chunks.jsonl"
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows[0]["chapter_id"] = "ch999"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                 encoding="utf-8")
    report = validate_twin(out)
    assert not report.ok
    assert any("orfani" in lbl and not ok for ok, lbl in report.checks)


def test_validate_detects_missing_committed_card(tmp_path):
    out = _twin(tmp_path)
    # STATUS dichiara committato un capitolo senza scheda su disco
    st = load_status(out)
    cid = sorted(st["chapters"])[0]
    st["chapters"][cid]["status"] = "committed"
    (out / "STATUS.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    report = validate_twin(out)
    assert not report.ok
    assert any(cid in lbl and not ok for ok, lbl in report.checks)


def test_config_stamps_engine_version(tmp_path):
    import yaml
    import book_twin
    out = _twin(tmp_path)
    cfg = yaml.safe_load((out / "book.config.yaml").read_text(encoding="utf-8"))
    assert cfg.get("engine_version") == book_twin.__version__
    assert "generated_at" in cfg
    assert cfg.get("status") == "ingested"
