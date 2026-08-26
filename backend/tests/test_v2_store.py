import pytest

from app.models import Connection, Profile, QueueItem, ScanRun


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Point the store at a scratch dir so tests never touch real user data."""
    from app import config as cfg
    from app import store

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "EVAL_DIR", tmp_path / "evaluations")
    monkeypatch.setattr(cfg, "OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "evaluations").mkdir()
    (tmp_path / "output").mkdir()
    return store


def test_connections_round_trip(tmp_data):
    store = tmp_data
    assert store.load_connections() == {}
    store.save_connection(Connection(portal="naukri", status="connected"))
    assert store.load_connections()["naukri"].status == "connected"


def test_save_connection_overwrites_the_same_portal(tmp_data):
    store = tmp_data
    store.save_connection(Connection(portal="naukri", status="connected"))
    store.save_connection(Connection(portal="naukri", status="expired", note="cookie gone"))
    conns = store.load_connections()
    assert len(conns) == 1 and conns["naukri"].note == "cookie gone"


def test_delete_connection_removes_it(tmp_data):
    store = tmp_data
    store.save_connection(Connection(portal="naukri", status="connected"))
    store.delete_connection("naukri")
    assert store.load_connections() == {}


def test_delete_unknown_connection_is_a_noop(tmp_data):
    tmp_data.delete_connection("never-existed")   # must not raise


def test_queue_upsert_updates_in_place_and_preserves_order(tmp_data):
    store = tmp_data
    store.upsert_queue_item(QueueItem(job_id="a", score=90))
    store.upsert_queue_item(QueueItem(job_id="b", score=80))
    store.upsert_queue_item(QueueItem(job_id="a", state="submitted", score=90))
    q = store.load_queue()
    assert [i.job_id for i in q] == ["a", "b"]
    assert q[0].state == "submitted"


def test_runs_are_newest_first_and_capped(tmp_data):
    store = tmp_data
    for i in range(205):
        store.save_run(ScanRun(id=f"r{i:03d}", started=f"2026-08-26T{i % 24:02d}:00:00"))
    runs = store.load_runs(limit=500)
    assert len(runs) == 200
    assert runs[0].id == "r204"


def test_source_config_defaults_empty_and_round_trips(tmp_data):
    store = tmp_data
    assert store.load_source_config() == {}
    store.set_source_enabled("linkedin", True)
    store.set_source_enabled("naukri", False)
    assert store.load_source_config() == {"linkedin": True, "naukri": False}


def test_embeddings_round_trip(tmp_data):
    store = tmp_data
    store.save_embeddings({"job1": [0.1, 0.2, 0.3]})
    assert store.load_embeddings()["job1"] == [0.1, 0.2, 0.3]


def test_corrupt_files_read_as_absent_not_as_a_crash(tmp_data, tmp_path):
    store = tmp_data
    (tmp_path / "connections.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "queue.json").write_text("", encoding="utf-8")
    assert store.load_connections() == {}
    assert store.load_queue() == []


def test_free_disk_gb_is_positive(tmp_data):
    assert tmp_data.free_disk_gb() > 0


def test_assert_disk_headroom_raises_when_space_is_low(tmp_data, monkeypatch):
    store = tmp_data
    monkeypatch.setattr(store, "free_disk_gb", lambda: 0.4)
    with pytest.raises(RuntimeError, match="Only 0.4 GB free"):
        store.assert_disk_headroom()


def test_disk_floor_covers_v1_writers_too(tmp_data, monkeypatch):
    """The 2 GB floor (spec §12.4) is unconditional — it must also stop the
    pre-existing v1 writers, not just the five v2 accessors. This is enforced
    by hoisting the check into `_write_atomic`, the single choke point every
    writer in this module funnels through, rather than calling it from each
    v2 accessor individually.
    """
    store = tmp_data
    monkeypatch.setattr(store, "free_disk_gb", lambda: 0.4)
    with pytest.raises(RuntimeError, match="Only 0.4 GB free"):
        store.save_profile(Profile(name="Ada"))
