"""STEP 2 — core LLM-native: ingest v2, commit validati, pack, stabilità ID."""
import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from book_twin.cli import app
from book_twin.commit import CommitError, commit_chapter, commit_synthesis, render_twin
from book_twin.converters import read_book
from book_twin.indexer import build_index
from book_twin.repository import create_book_repository, pack_twin, split_parts
from book_twin.status import load_status
from book_twin.utils import read_jsonl
from book_twin.validation import validate_twin

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_book.md"
runner = CliRunner()

RIASSUNTO = (
    "Riassunto fedele del capitolo: il testo viene trasformato in una base di "
    "conoscenza interrogabile, conservando il contenuto in modo fedele e rendendolo "
    "esplorabile tramite capitoli, chunk e indici, così che un'intelligenza "
    "artificiale possa rispondere citando i passaggi rilevanti del libro originale."
)


def _ingest(tmp_path: Path, name: str = "twin") -> Path:
    text, pages, meta = read_book(SAMPLE)
    out = tmp_path / name
    create_book_repository(source_path=SAMPLE, out_dir=out, language="it",
                           full_text=text, pages=pages, metadata=meta, force=True)
    build_index(out, embeddings=False)
    return out


def _chunks_for(out: Path, chapter_id: str) -> list[dict]:
    return [c for c in read_jsonl(out / "knowledge" / "chunks.jsonl")
            if c["chapter_id"] == chapter_id]


def _anchor_from(chunk: dict, words: int = 5) -> str:
    return " ".join(chunk["text"].split()[:words])


def _card(out: Path, chapter_id: str, **overrides) -> dict:
    st = load_status(out)
    info = st["chapters"][chapter_id]
    chunks = _chunks_for(out, chapter_id)
    chunk_id = chunks[0]["id"]
    card = {
        "chapter_id": chapter_id,
        "title": info["title"],
        "coverage": {"parts_read": info["parts_total"], "parts_total": info["parts_total"]},
        "funzione": "Presenta una parte del percorso argomentativo del libro.",
        "riassunto": RIASSUNTO,
        "tesi": "Un libro può diventare una rete interrogabile di concetti e claim.",
        "concetti": [{
            "name": "base di conoscenza",
            "definition": "Rappresentazione strutturata e interrogabile del testo.",
            "chunk_ids": [chunk_id],
        }],
        "claims": [{
            "claim": "Il testo va conservato fedelmente e reso esplorabile.",
            "tipo": "testo",
            "chunk_ids": [chunk_id],
            "anchors": [_anchor_from(chunks[0])],
        }],
        "passaggi": [],
        "domande": ["Come si misura la fedeltà di una ricostruzione?"],
        "obiezioni": ["La segmentazione potrebbe perdere il filo argomentativo."],
        "applicazioni": ["Costruire twin interrogabili di saggistica."],
        "cosa_memorizzare": "Conversione, segmentazione, indicizzazione, interpretazione.",
    }
    card.update(overrides)
    return card


def _write_card(tmp_path: Path, card: dict, name: str = "card.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return p


def _synthesis(out: Path) -> dict:
    chapter_ids = sorted(load_status(out)["chapters"])
    return {
        "tesi_centrale": "Un libro può essere trasformato in una base di conoscenza interrogabile.",
        "formula": "Dal testo alla rete di concetti.",
        "mappa": ["Tesi", "Metodo", "Dialogo"],
        "argomentazione": "Conversione fedele, segmentazione, indicizzazione e interpretazione.",
        "concetti_globali": [{
            "name": "base di conoscenza",
            "definition": "Rete interrogabile di concetti, claim e passaggi.",
            "chapter_ids": chapter_ids,
        }],
        "domande_profonde": ["Cosa si perde trasformando un libro in rete?"],
        "limiti": ["Il libro di esempio è minimale."],
        "collegamenti_esterni": [],
    }


# --------------------------------------------------------------------------- #
# Ingest v2
# --------------------------------------------------------------------------- #
def test_ingest_layout_v2(tmp_path):
    out = _ingest(tmp_path)
    assert (out / "STATUS.json").exists()
    assert (out / "book.config.yaml").exists()
    assert (out / "canonical" / "book.md").exists()
    assert (out / "analysis" / "rendered").is_dir()
    assert (out / "canonical" / "notes").is_dir()
    # niente placeholder md di analisi
    assert list((out / "analysis" / "chapters").glob("*.md")) == []
    st = load_status(out)
    assert st["phase"] == "ingested"
    for cid, c in st["chapters"].items():
        assert cid.startswith("ch") and len(cid) == 5
        assert c["status"] == "pending"
        assert c["parts_total"] >= 1
        assert c["hash"].startswith("sha256:")


def test_chunk_ids_v2_and_chapter_hash(tmp_path):
    out = _ingest(tmp_path)
    chunks = read_jsonl(out / "knowledge" / "chunks.jsonl")
    st = load_status(out)
    assert chunks
    for c in chunks:
        assert c["id"].startswith(f"chunk_{c['chapter_id']}_")
        assert c["chapter_hash"] == st["chapters"][c["chapter_id"]]["hash"]


def test_reingest_same_text_same_ids(tmp_path):
    out1 = _ingest(tmp_path, "twin1")
    out2 = _ingest(tmp_path, "twin2")
    ids1 = [c["id"] for c in read_jsonl(out1 / "knowledge" / "chunks.jsonl")]
    ids2 = [c["id"] for c in read_jsonl(out2 / "knowledge" / "chunks.jsonl")]
    assert ids1 == ids2
    st1, st2 = load_status(out1), load_status(out2)
    assert st1["book_hash"] == st2["book_hash"]
    assert {k: v["hash"] for k, v in st1["chapters"].items()} == \
           {k: v["hash"] for k, v in st2["chapters"].items()}


def test_split_parts_deterministic():
    text = "\n\n".join(f"Paragrafo numero {i}. " + ("parola " * 200) for i in range(20))
    parts = split_parts(text, 5000)
    assert len(parts) > 1
    assert parts == split_parts(text, 5000)
    assert "".join(p if i == 0 else p for i, p in enumerate(parts))  # nessuna parte vuota
    assert all(p.strip() for p in parts)


# --------------------------------------------------------------------------- #
# Commit: rifiuti deterministici
# --------------------------------------------------------------------------- #
def test_commit_rejects_unknown_chunk_id(tmp_path):
    out = _ingest(tmp_path)
    card = _card(out, "ch001")
    card["claims"][0]["chunk_ids"] = ["chunk_ch001_9999"]
    card["claims"][0]["anchors"] = []
    card["claims"][0]["tipo"] = "inferenza"
    with pytest.raises(CommitError, match="chunk_ch001_9999"):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))
    assert load_status(out)["chapters"]["ch001"]["status"] == "pending"


def test_commit_rejects_chunk_of_other_chapter(tmp_path):
    out = _ingest(tmp_path)
    other = _chunks_for(out, "ch002")[0]["id"]
    card = _card(out, "ch001")
    card["concetti"][0]["chunk_ids"] = [other]
    with pytest.raises(CommitError, match="appartiene a ch002"):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))


def test_commit_rejects_missing_anchor(tmp_path):
    out = _ingest(tmp_path)
    card = _card(out, "ch001")
    card["claims"][0]["anchors"] = ["frase del tutto inventata e assente"]
    with pytest.raises(CommitError, match="anchor non trovata"):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))


def test_commit_rejects_incomplete_coverage(tmp_path):
    out = _ingest(tmp_path)
    st = load_status(out)
    total = st["chapters"]["ch001"]["parts_total"]
    card = _card(out, "ch001", coverage={"parts_read": total - 1 if total > 1 else 0,
                                         "parts_total": total})
    with pytest.raises(CommitError, match="coverage incompleto"):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))


def test_commit_rejects_wrong_parts_total(tmp_path):
    out = _ingest(tmp_path)
    total = load_status(out)["chapters"]["ch001"]["parts_total"]
    card = _card(out, "ch001", coverage={"parts_read": total + 2, "parts_total": total + 2})
    with pytest.raises(CommitError, match="parts_total"):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))


def test_commit_rejects_tesi_equal_riassunto(tmp_path):
    out = _ingest(tmp_path)
    card = _card(out, "ch001", tesi=RIASSUNTO)
    with pytest.raises(CommitError, match="tesi"):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))


def test_commit_testo_claim_requires_anchor(tmp_path):
    out = _ingest(tmp_path)
    card = _card(out, "ch001")
    card["claims"][0]["anchors"] = []
    with pytest.raises(CommitError, match="anchor"):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))


def test_synthesis_rejected_with_pending_chapters(tmp_path):
    out = _ingest(tmp_path)
    syn = tmp_path / "synthesis.json"
    syn.write_text(json.dumps(_synthesis(out)), encoding="utf-8")
    with pytest.raises(CommitError, match="non ancora committati"):
        commit_synthesis(out, syn)


def test_cli_commit_exit_code_nonzero(tmp_path):
    out = _ingest(tmp_path)
    card = _card(out, "ch001")
    card["claims"][0]["chunk_ids"] = ["chunk_ch001_9999"]
    card["claims"][0]["tipo"] = "inferenza"
    card["claims"][0]["anchors"] = []
    p = _write_card(tmp_path, card)
    result = runner.invoke(app, ["commit-chapter", str(out), "1", "--file", str(p)])
    assert result.exit_code != 0
    assert "chunk_ch001_9999" in result.output


# --------------------------------------------------------------------------- #
# End-to-end: ingest → commit per ogni capitolo → synthesis → render → pack
# --------------------------------------------------------------------------- #
def test_end_to_end_complete(tmp_path):
    out = _ingest(tmp_path)
    chapter_ids = sorted(load_status(out)["chapters"])
    assert len(chapter_ids) >= 2  # oggi 2 sul sample; 3 dopo STEP 4

    for cid in chapter_ids:
        chunks = _chunks_for(out, cid)
        card = _card(out, cid)
        card["chunk_summaries"] = [{"chunk_id": chunks[0]["id"],
                                    "summary": "Lettura ermeneutica del capitolo."}]
        commit_chapter(out, cid, _write_card(tmp_path, card, f"card_{cid}.json"))

    st = load_status(out)
    assert all(c["status"] == "committed" for c in st["chapters"].values())
    assert st["phase"] == "analyzing"

    # summary/keywords aggiornati nei chunk
    chunks = read_jsonl(out / "knowledge" / "chunks.jsonl")
    assert any(c["summary"] == "Lettura ermeneutica del capitolo." for c in chunks)
    assert any("base di conoscenza" in (c["keywords"] or []) for c in chunks)

    # STEP 3 (aggiunta scope): l'indice ricostruito da commit-chapter popola le
    # colonne stem anche per le summary committate dopo l'ingest:
    # "ermeneutiche" (flesso) trova la summary "ermeneutica", parola assente dal testo
    from book_twin.indexer import search_index
    rows = search_index(out, "ermeneutiche", top_k=5)
    assert rows, "la summary committata deve essere trovata via stem"

    syn = tmp_path / "synthesis.json"
    syn.write_text(json.dumps(_synthesis(out), ensure_ascii=False), encoding="utf-8")
    commit_synthesis(out, syn)
    st = load_status(out)
    assert st["phase"] == "synthesized"
    assert read_jsonl(out / "knowledge" / "claims.jsonl")
    assert read_jsonl(out / "knowledge" / "concepts.jsonl")

    rendered = render_twin(out)
    assert (out / "analysis" / "rendered" / "synthesis.md").exists()
    assert len(rendered) == len(chapter_ids) + 1

    report = validate_twin(out)
    assert report.ok, report.render()

    zip_path = pack_twin(out)
    assert zip_path.exists()
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["chapters_committed"] == len(chapter_ids)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith("MANIFEST.json") for n in names)
    assert any(n.endswith("STATUS.json") for n in names)
    assert load_status(out)["phase"] == "packed"


def test_pack_partial_is_legal(tmp_path):
    out = _ingest(tmp_path)
    cid = sorted(load_status(out)["chapters"])[0]
    commit_chapter(out, cid, _write_card(tmp_path, _card(out, cid)))
    zip_path = pack_twin(out)
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "partial"
    assert zip_path.exists()
    # lo stato resta ripristinabile: fase non "packed"
    assert load_status(out)["phase"] == "analyzing"


def _complete_twin(tmp_path: Path) -> Path:
    out = _ingest(tmp_path)
    for cid in sorted(load_status(out)["chapters"]):
        commit_chapter(out, cid, _write_card(tmp_path, _card(out, cid), f"c_{cid}.json"))
    syn = tmp_path / "syn.json"
    syn.write_text(json.dumps(_synthesis(out), ensure_ascii=False), encoding="utf-8")
    commit_synthesis(out, syn)
    return out


def test_pack_unzip_validate_roundtrip(tmp_path):
    out = _complete_twin(tmp_path)
    zip_path = pack_twin(out)
    dest = tmp_path / "estratto"
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    extracted = dest / out.name
    report = validate_twin(extracted)
    assert report.ok, report.render()


def test_pack_aligns_config_status(tmp_path):
    import yaml
    out = _complete_twin(tmp_path)
    pack_twin(out)
    cfg = yaml.safe_load((out / "book.config.yaml").read_text(encoding="utf-8"))
    assert cfg["status"] == load_status(out)["phase"] == "packed"
    # twin parziale: status config = fase corrente (non "ingested" fossile)
    out2 = _ingest(tmp_path, "twin_partial")
    cid = sorted(load_status(out2)["chapters"])[0]
    commit_chapter(out2, cid, _write_card(tmp_path, _card(out2, cid), "cp.json"))
    pack_twin(out2)
    cfg2 = yaml.safe_load((out2 / "book.config.yaml").read_text(encoding="utf-8"))
    assert cfg2["status"] == "analyzing"


def test_rejected_commit_is_logged_in_status(tmp_path):
    out = _ingest(tmp_path)
    card = _card(out, "ch001")
    card["claims"][0]["chunk_ids"] = ["chunk_ch001_9999"]
    card["claims"][0]["tipo"] = "inferenza"
    card["claims"][0]["anchors"] = []
    with pytest.raises(CommitError):
        commit_chapter(out, "ch001", _write_card(tmp_path, card))
    log = load_status(out)["log"]
    assert any("commit-chapter ch001 rifiutato" in line and "chunk_ch001_9999" in line
               for line in log)


def test_sample_has_three_chapters(tmp_path):
    # STEP 4: il capitolo 3 (breve ma con corpo) non viene più inghiottito
    out = _ingest(tmp_path)
    st = load_status(out)
    assert len(st["chapters"]) == 3
    assert st["chapters"]["ch003"]["title"].endswith("Il dialogo")


def test_restructure_blocked_after_commit(tmp_path):
    from book_twin.repository import restructure_twin
    out = _ingest(tmp_path)
    commit_chapter(out, "ch001", _write_card(tmp_path, _card(out, "ch001")))
    ov = tmp_path / "ov.yaml"
    ov.write_text("actions:\n  - {action: rename, chapter: 2, title: X}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="già committati"):
        restructure_twin(out, ov)


def test_restructure_applies_override_and_pack_includes_it(tmp_path):
    from book_twin.repository import restructure_twin
    out = _ingest(tmp_path)
    ov = tmp_path / "ov.yaml"
    ov.write_text(
        "actions:\n"
        "  - {action: merge, chapters: [2, 3]}\n"
        "  - {action: rename, chapter: 1, title: Tesi rivista}\n",
        encoding="utf-8",
    )
    chapters = restructure_twin(out, ov)
    st = load_status(out)
    assert len(st["chapters"]) == 2
    assert st["chapters"]["ch001"]["title"] == "Tesi rivista"
    assert all(c["status"] == "pending" for c in st["chapters"].values())
    assert any("override" in line for line in st["log"])
    # l'override applicato è copiato nel twin…
    assert (out / "chapters.override.yaml").exists()
    # …e incluso nel MANIFEST al pack: twin riproducibile da (libro, engine, override)
    pack_twin(out)
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert "chapters.override.yaml" in manifest["files"]
    # i chunk sono stati rigenerati coerenti coi nuovi capitoli
    chunks = read_jsonl(out / "knowledge" / "chunks.jsonl")
    assert {c["chapter_id"] for c in chunks} == {"ch001", "ch002"}


def test_ingest_with_override(tmp_path):
    text, pages, meta = read_book(SAMPLE)
    ov = tmp_path / "ov.yaml"
    ov.write_text("actions:\n  - {action: drop, chapter: 3}\n", encoding="utf-8")
    out = tmp_path / "twin_ov"
    create_book_repository(source_path=SAMPLE, out_dir=out, language="it",
                           full_text=text, pages=pages, metadata=meta, force=True,
                           override_path=ov)
    st = load_status(out)
    assert len(st["chapters"]) == 2
    assert (out / "chapters.override.yaml").exists()
    assert any("drop" in line for line in st["log"])


def test_status_and_chapter_cli(tmp_path):
    out = _ingest(tmp_path)
    result = runner.invoke(app, ["status", str(out)])
    assert result.exit_code == 0
    assert "Prossima azione" in result.output
    result = runner.invoke(app, ["chapter", str(out), "1"])
    assert result.exit_code == 0
    assert "ch001" in result.output
    result = runner.invoke(app, ["chapter", str(out), "99"])
    assert result.exit_code != 0
