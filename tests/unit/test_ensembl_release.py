"""The Ensembl release a run reads must be pinned, declared and recorded.

Roadmap B17. The project called `https://rest.ensembl.org` with no release in
the URL and nothing recording which release answered. Measured consequence,
2026-11-27: the cache held sequences from **two** releases at once — six
transcripts matched release 116 only, eight matched 113/115 only, because TTLs
expire per entry and a refetch landed on whatever was live that day. The same
transcript can change: VEGFA's `ENST00000372067` is 3535 nt in releases
113-115 and 3537 nt in 116, and a 7-nt seed scan over a cDNA that grew by 2 nt
is not the same scan.

Three things have to be true, and they fail in different ways:

* the **pin** — a release-qualified host, so the URL itself says which release
  answered. Ensembl refuses versioned accessions (`ENST00000372067.8` →
  *ID not found*), so the pin has to be the host, never the id;
* the **cache key** carries the release, so two releases cannot share an
  entry. A schema-version bump would invalidate the mixed entries once, but it
  relies on someone remembering to bump it next time; a release in the key
  makes mixing impossible by construction, which is the difference between a
  rule and a mechanism (invariant 3);
* the **check** — if the pinned host answers with a different release than the
  config declares, the run fails loudly instead of computing on other bytes.

Archive hosts only exist for releases that have been superseded: when this was
written the newest archived release was 115 (`sep2025`), while 116 was live and
had no archive host yet. So the pin rule is "the newest release with a
resolvable archive host" — pinning to the live release would give a URL that
silently starts meaning something else.
"""

from __future__ import annotations

import pytest

from src.core import ensembl_release as er


class TestTheHostAndTheReleaseMustAgree:
    """A declared release that the host does not serve is the whole hazard."""

    def test_release_is_parsed_from_an_archive_host(self) -> None:
        assert er.host_is_archived("https://sep2025.rest.ensembl.org") is True
        assert er.host_is_archived("https://may2025.rest.ensembl.org/") is True

    def test_the_live_host_is_not_a_pin(self) -> None:
        """`rest.ensembl.org` means "whatever is current", which is the bug."""
        assert er.host_is_archived("https://rest.ensembl.org") is False

    def test_verify_accepts_a_matching_release(self) -> None:
        assert er.verify(declared=115, live=115) is None

    def test_verify_refuses_a_mismatch(self) -> None:
        with pytest.raises(er.ReleaseMismatch) as caught:
            er.verify(declared=115, live=116)
        assert "115" in str(caught.value)
        assert "116" in str(caught.value)

    def test_unreachable_is_unverified_not_a_mismatch(self) -> None:
        """A transient network failure must not look like a changed release.

        It also must not pass silently: the manifest records
        `release_verified: false`, so the run says what it could not confirm
        rather than implying it checked (invariant 2 applied to provenance).
        """
        assert er.verify(declared=115, live=None) is None
        assert er.verified(declared=115, live=None) is False
        assert er.verified(declared=115, live=115) is True


class TestCacheKeysCarryTheRelease:
    """Two releases must not be able to occupy the same cache entry."""

    def test_sequence_key_includes_the_release(self) -> None:
        key = er.cache_key("seq", 115, "ENST00000372067")
        assert key == "seq:115:ENST00000372067"

    def test_a_different_release_is_a_different_key(self) -> None:
        assert er.cache_key("seq", 115, "ENST1") != er.cache_key("seq", 116, "ENST1")

    def test_the_source_prefix_survives_for_the_schema_registry(self) -> None:
        """`cache.source_of` reads the first token; it must still see `seq`."""
        from src.core.cache import source_of

        assert source_of(er.cache_key("seq", 115, "ENST1")) == "seq"
        assert source_of(er.cache_key("bg", 115, "canonical:ACTB")) == "bg"

    def test_pre_b17_keys_are_not_reachable(self) -> None:
        """The 243 mixed entries already on disk must never be served again."""
        assert er.cache_key("seq", 115, "ENST1") != "seq:ENST1"

    def test_every_ensembl_cache_key_in_production_is_release_qualified(self) -> None:
        """Measured over the source, not asserted: a call site that builds its
        own key string is how the two copies diverge (roadmap H9)."""
        import re
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        offenders: list[str] = []
        for rel in (
            "src/stage1_genomic_map/transcript_resolver.py",
            "src/stage1_genomic_map/tss_mapper.py",
            "src/stage2_offtarget_scan/transcriptome_fetcher.py",
        ):
            text = (root / rel).read_text(encoding="utf-8")
            for match in re.finditer(
                r'f?"(seq|bg|ensembl):(?!\{release)[^"]*"', text
            ):
                literal = match.group(0)
                if "{release}" in literal or "{self._release}" in literal:
                    continue
                offenders.append(f"{rel}: {literal}")
        assert not offenders, "cache keys built without the release: " + "; ".join(
            offenders
        )


class TestTheConfigIsPinned:
    def test_config_declares_an_archived_host_and_a_release(self) -> None:
        import yaml
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        config = yaml.safe_load(
            (root / "config" / "config.yaml").read_text(encoding="utf-8")
        )
        assert er.host_is_archived(config["ensembl_base_url"]), (
            f"ensembl_base_url is not a pinned archive host: "
            f"{config['ensembl_base_url']}"
        )
        assert isinstance(config.get("ensembl_release"), int)
        assert er.release_in_host(config["ensembl_base_url"]) is not None

    def test_the_declared_release_is_wired_into_the_model(self) -> None:
        from src.core.config import OrcSonarConfig

        assert "ensembl_release" in OrcSonarConfig.model_fields


class TestTheManifestRecordsIt:
    def test_manifest_has_a_data_sources_block_naming_the_release(self) -> None:
        from pathlib import Path

        from src.core.run_manifest import data_sources

        root = Path(__file__).resolve().parents[2]
        block = data_sources(root)
        assert block["ensembl"]["release"] == 115
        assert "sep2025" in block["ensembl"]["base_url"]
        # Whether the live host confirmed it is a separate, honest field.
        assert "release_verified" in block["ensembl"]
