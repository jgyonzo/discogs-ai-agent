"""Dataset builder (023 US1 T010): selection preference, resume, manifest
integrity, containment. FakeDiscogsClient only — zero live calls."""

from __future__ import annotations

import json

import pytest

from collection_agent.eval.dataset import (
    DatasetError,
    ManifestRelease,
    build_dataset,
    done_release_ids,
    load_manifest,
    manifest_path,
    newest_header,
    select_images,
)
from collection_agent.snapshot.store import SnapshotStore

from tests.conftest import make_record, make_snapshot
from tests.fixtures.fake_client import FakeDiscogsClient


def img(kind: str, uri: str) -> dict:
    return {"type": kind, "uri": uri, "uri150": uri + "?150"}


def make_fake(details: dict[int, dict], images_ok: list[str]) -> FakeDiscogsClient:
    fake = FakeDiscogsClient(instances=[], details=details)
    for uri in images_ok:
        fake.image_bytes[uri] = f"bytes-of-{uri}".encode()
    return fake


def seeded_store(settings, release_ids: list[int]) -> SnapshotStore:
    store = SnapshotStore(settings.snapshot_path)
    records = [
        make_record(instance_id=i + 1, release_id=rid)
        for i, rid in enumerate(release_ids)
    ]
    store.save(make_snapshot(records))
    return store


class TestSelection:
    def test_secondary_preferred_over_primary(self):
        images = [img("primary", "u1"), img("secondary", "u2"), img("secondary", "u3")]
        chosen = select_images(images, cap=2)
        assert [i["uri"] for i in chosen] == ["u2", "u3"]

    def test_primary_taken_when_cap_allows(self):
        images = [img("primary", "u1"), img("secondary", "u2")]
        assert [i["uri"] for i in select_images(images, cap=3)] == ["u2", "u1"]

    def test_primary_only_release_is_taken(self):
        images = [img("primary", "u1")]
        assert [i["uri"] for i in select_images(images, cap=2)] == ["u1"]


class TestBuild:
    def test_happy_build_writes_images_manifest_and_notice(self, settings):
        store = seeded_store(settings, [101])
        fake = make_fake(
            {101: {"id": 101, "images": [
                img("primary", "https://i.discogs.com/p.jpg"),
                img("secondary", "https://i.discogs.com/s.jpg"),
            ]}},
            images_ok=["https://i.discogs.com/p.jpg", "https://i.discogs.com/s.jpg"],
        )
        stats = build_dataset(fake, store, settings)

        assert stats["downloaded"] == 1 and stats["images_downloaded"] == 2
        assert (settings.eval_dataset_dir / "NOTICE.txt").exists()
        assert (settings.eval_dataset_dir / "101_secondary1.jpg").read_bytes() \
            == b"bytes-of-https://i.discogs.com/s.jpg"
        assert (settings.eval_dataset_dir / "101_primary1.jpg").exists()

        entries = load_manifest(settings.eval_dataset_dir)
        header = newest_header(entries)
        assert header is not None and header.snapshot_completeness == "complete"
        release = [e for e in entries if isinstance(e, ManifestRelease)][0]
        assert release.release_id == 101 and release.status == "downloaded"
        # manifest (not filename) carries ground truth + verbatim URI
        assert release.images[0].source_uri == "https://i.discogs.com/s.jpg"

    def test_missing_snapshot_is_actionable_error(self, settings):
        store = SnapshotStore(settings.snapshot_path)
        with pytest.raises(DatasetError, match="sync"):
            build_dataset(FakeDiscogsClient(instances=[], details={}), store, settings)

    def test_no_images_recorded_not_skipped(self, settings):
        store = seeded_store(settings, [101])
        fake = make_fake({101: {"id": 101, "images": []}}, images_ok=[])
        stats = build_dataset(fake, store, settings)
        assert stats["no_images"] == 1
        entries = load_manifest(settings.eval_dataset_dir)
        release = [e for e in entries if isinstance(e, ManifestRelease)][0]
        assert release.status == "no_images" and release.images == []

    def test_failed_download_recorded_and_build_continues(self, settings):
        store = seeded_store(settings, [101, 102])
        fake = make_fake(
            {
                101: {"id": 101, "images": [img("secondary", "https://i/expired.jpg")]},
                102: {"id": 102, "images": [img("secondary", "https://i/ok.jpg")]},
            },
            images_ok=["https://i/ok.jpg"],  # 101's URI unscripted -> None
        )
        stats = build_dataset(fake, store, settings)
        assert stats["failed"] == 1 and stats["downloaded"] == 1
        entries = [e for e in load_manifest(settings.eval_dataset_dir)
                   if isinstance(e, ManifestRelease)]
        by_id = {e.release_id: e for e in entries}
        assert by_id[101].status == "failed"
        assert by_id[101].images[0].status == "failed"
        assert by_id[101].images[0].detail  # honest reason recorded
        assert by_id[102].status == "downloaded"

    def test_release_fetch_404_is_failed_line(self, settings):
        store = seeded_store(settings, [101])
        fake = FakeDiscogsClient(
            instances=[], details={}, release_failures={101: "404"}
        )
        stats = build_dataset(fake, store, settings)
        assert stats["failed"] == 1
        release = [e for e in load_manifest(settings.eval_dataset_dir)
                   if isinstance(e, ManifestRelease)][0]
        assert release.status == "failed" and "404" in (release.detail or "")

    def test_instances_of_same_release_deduplicated(self, settings):
        store = SnapshotStore(settings.snapshot_path)
        store.save(make_snapshot([
            make_record(instance_id=1, release_id=101),
            make_record(instance_id=2, release_id=101),  # second copy
        ]))
        fake = make_fake(
            {101: {"id": 101, "images": [img("secondary", "https://i/s.jpg")]}},
            images_ok=["https://i/s.jpg"],
        )
        stats = build_dataset(fake, store, settings)
        assert stats["processed"] == 1
        assert fake.release_fetches == [101]

    def test_limit_truncates_worklist(self, settings):
        store = seeded_store(settings, [101, 102, 103])
        fake = make_fake({rid: {"id": rid, "images": []} for rid in (101, 102, 103)}, [])
        stats = build_dataset(fake, store, settings, limit=2)
        assert stats["processed"] == 2


class TestResume:
    def test_rerun_skips_done_and_retries_failed(self, settings):
        store = seeded_store(settings, [101, 102])
        # first run: 101 ok, 102's download fails
        fake1 = make_fake(
            {
                101: {"id": 101, "images": [img("secondary", "https://i/a.jpg")]},
                102: {"id": 102, "images": [img("secondary", "https://i/b.jpg")]},
            },
            images_ok=["https://i/a.jpg"],
        )
        build_dataset(fake1, store, settings)
        # second run: 102 now succeeds; 101 must not be re-fetched
        fake2 = make_fake(
            {102: {"id": 102, "images": [img("secondary", "https://i/b.jpg")]}},
            images_ok=["https://i/b.jpg"],
        )
        stats = build_dataset(fake2, store, settings)
        assert fake2.release_fetches == [102]
        assert stats["processed"] == 1 and stats["downloaded"] == 1
        done = done_release_ids(load_manifest(settings.eval_dataset_dir))
        assert done == {101, 102}

    def test_torn_trailing_line_is_tolerated(self, settings):
        store = seeded_store(settings, [101])
        fake = make_fake(
            {101: {"id": 101, "images": [img("secondary", "https://i/a.jpg")]}},
            images_ok=["https://i/a.jpg"],
        )
        build_dataset(fake, store, settings)
        mpath = manifest_path(settings.eval_dataset_dir)
        with mpath.open("a", encoding="utf-8") as fh:
            fh.write('{"type": "release", "release_id": 9')  # crash mid-append
        done = done_release_ids(load_manifest(settings.eval_dataset_dir))
        assert done == {101}

    def test_corrupt_mid_file_line_is_a_hard_error(self, settings):
        store = seeded_store(settings, [101])
        fake = make_fake(
            {101: {"id": 101, "images": [img("secondary", "https://i/a.jpg")]}},
            images_ok=["https://i/a.jpg"],
        )
        build_dataset(fake, store, settings)
        mpath = manifest_path(settings.eval_dataset_dir)
        lines = mpath.read_text(encoding="utf-8").splitlines()
        lines.insert(1, "not json at all")
        mpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="corrupt manifest"):
            load_manifest(settings.eval_dataset_dir)

    def test_each_run_appends_its_own_header(self, settings):
        store = seeded_store(settings, [101])
        fake = make_fake({101: {"id": 101, "images": []}}, [])
        build_dataset(fake, store, settings)
        build_dataset(make_fake({}, []), store, settings)
        entries = load_manifest(settings.eval_dataset_dir)
        headers = [e for e in entries if not isinstance(e, ManifestRelease)]
        assert len(headers) == 2


class TestCli:
    def test_eval_dataset_without_snapshot_exits_config(self, settings, monkeypatch):
        from collection_agent import cli

        monkeypatch.setattr(cli, "load_settings", lambda: settings)
        monkeypatch.setattr(
            "collection_agent.discogs.client.DiscogsClient",
            lambda *a, **k: FakeDiscogsClient(instances=[], details={}),
        )
        assert cli.main(["eval-dataset"]) == cli.EXIT_CONFIG

    def test_eval_dataset_happy_exit_ok(self, settings, monkeypatch):
        from collection_agent import cli

        seeded_store(settings, [101])
        fake = make_fake({101: {"id": 101, "images": []}}, [])
        monkeypatch.setattr(cli, "load_settings", lambda: settings)
        monkeypatch.setattr(
            "collection_agent.discogs.client.DiscogsClient",
            lambda *a, **k: fake,
        )
        assert cli.main(["eval-dataset"]) == cli.EXIT_OK
        assert manifest_path(settings.eval_dataset_dir).exists()
