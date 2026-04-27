"""Step 1 — Prepare sources: resolve releases.xml or .gz, record size + checksum.

Per spec ``002-etl-scaleup`` (FR-010): the input may be either an
uncompressed ``releases.xml`` or a gzipped ``releases.xml.gz``. The
gzip-aware opener at :mod:`discogs_etl.io.input` resolves which file
applies and reports back via :class:`~discogs_etl.io.input.ReleasesInput`.
"""
from __future__ import annotations

from ..io.file_utils import sha256_file
from ..io.input import open_releases_input
from ..pipeline.context import RunContext
from ..pipeline.manifest import Manifest


class PrepareSourcesStep:
    name = "prepare_sources"

    def outputs_exist(self, ctx: RunContext) -> bool:
        return False

    def delete_outputs(self, ctx: RunContext) -> None:
        pass

    def run(self, ctx: RunContext, manifest: Manifest) -> None:
        try:
            ri = open_releases_input(ctx.raw_snapshot_dir)
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"no releases input in snapshot dir {ctx.raw_snapshot_dir}"
            ) from e
        try:
            ri.file_obj.close()
        except Exception:  # noqa: BLE001 — close is best-effort
            pass

        path = ri.source_path
        size = path.stat().st_size
        ctx.logger.info(
            "prepare_sources: hashing %s (%d bytes; gzipped=%s)",
            path, size, ri.is_gzipped,
        )
        checksum = sha256_file(path)
        manifest.record_source_file(
            "releases", path=path, size_bytes=size, checksum=checksum,
        )

        if ri.is_gzipped:
            manifest.warn("prepare_sources.gz_input", str(path))
        if ri.gz_and_plain_present:
            manifest.warn(
                "prepare_sources.gz_and_plain_present",
                f"using uncompressed {path}; .gz sibling also present",
            )
