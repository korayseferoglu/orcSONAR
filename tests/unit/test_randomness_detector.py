"""The randomness probe reads code, not prose (roadmap H24).

`run_manifest.stochastic_components()` decides whether the pipeline has any
stochastic component, and the manifest's reproducibility claim rests on that
sentence: "No seeds are recorded because no stochastic component was found."

It used to decide with a textual ``git grep`` for
``\\brandom\\b|np\\.random|numpy\\.random|secrets\\.|shuffle|sample\\(`` over
``src``, and both directions of that were wrong.

**The cheap direction, observed live.** `B11c` added ``_chance_hits``, a
closed-form expectation that performs no sampling at all, and the full suite
went red — because the function's *docstring* described the refuted shuffled
null, and ``models.py``'s comment said "random 20-mer". A detector that cannot
tell a docstring from a call reported randomness that does not exist, and the
workaround at the time was to reword the prose, which means the record was
being written to fit the detector's blindness.

**The dangerous direction.** ``rng = default_rng()`` matches none of those
patterns. Neither does ``import random as rnd``. So a module that genuinely
samples would have been reported as clean, and the manifest would have
claimed reproducibility it could not support. That is the half this file
measures hardest, because a false green is the failure invariant 5 exists for.

An AST walk removes the first class of error structurally — a string constant
is not an import and not a call — and the second class is closed by anchoring
on imports and on the call graph rather than on spelling.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from src.core.run_manifest import randomness_findings, stochastic_components

ROOT = Path(__file__).resolve().parents[2]


def _module(tmp_path: Path, body: str, name: str = "probe.py") -> Path:
    target = tmp_path / name
    target.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return target


class TestProseIsNotRandomness:
    """The false-positive direction: the shape that broke the suite on B11c."""

    def test_a_docstring_about_shuffling_is_not_randomness(self, tmp_path: Path) -> None:
        """The exact shape that turned the suite red while writing B11c.

        Built by concatenation rather than a nested literal so that this file
        itself stays free of a stray triple quote.
        """
        quote = chr(34) * 3
        source = (
            "def chance_hits(motifs, length):\n"
            "    " + quote + "A permuted null tracks the observation.\n"
            "\n"
            "    Shuffling the sequence preserves its uridine content, so the\n"
            "    shuffled null cancels the signal. A random 20-mer scores 0.56,\n"
            "    and np.random.sample( would be the wrong tool here.\n"
            "    " + quote + "\n"
            "    return sum(2 * (length - len(m) + 1) * 0.25 ** len(m) for m in motifs)\n"
        )
        target = tmp_path / "prose.py"
        target.write_text(source, encoding="utf-8")
        assert randomness_findings([target]) == []

    def test_a_comment_about_random_is_not_randomness(self, tmp_path: Path) -> None:
        module = _module(tmp_path, """
            # random.shuffle would be wrong here, and np.random.sample( too
            VALUE = 1
        """)
        assert randomness_findings([module]) == []

    def test_a_domain_method_called_sample_is_not_randomness(self, tmp_path: Path) -> None:
        """`sample(` was in the old pattern and matches ordinary code."""
        module = _module(tmp_path, """
            def read(curve, points):
                return curve.sample(points)
        """)
        assert randomness_findings([module]) == []

    def test_a_variable_named_random_is_not_randomness(self, tmp_path: Path) -> None:
        module = _module(tmp_path, """
            random_label = "control"


            def label() -> str:
                return random_label
        """)
        assert randomness_findings([module]) == []

    def test_a_string_constant_naming_the_patterns_is_not_randomness(
        self, tmp_path: Path
    ) -> None:
        """Exactly why the old probe had to exempt its own source file."""
        module = _module(tmp_path, """
            PATTERNS = ("random", "secrets", "default_rng", "shuffle")
        """)
        assert randomness_findings([module]) == []


class TestSamplingIsCaught:
    """The false-negative direction — the one that would hide a false green."""

    def test_default_rng_through_numpy_is_caught(self, tmp_path: Path) -> None:
        module = _module(tmp_path, """
            import numpy as np


            def draw(n):
                rng = np.random.default_rng()
                return rng.normal(size=n)
        """)
        assert randomness_findings([module]), "np.random.default_rng() missed"

    def test_default_rng_imported_bare_is_caught(self, tmp_path: Path) -> None:
        """The form the old pattern could not see at all."""
        module = _module(tmp_path, """
            from numpy.random import default_rng

            RNG = default_rng(7)
        """)
        assert randomness_findings([module]), "bare default_rng() missed"

    def test_import_random_and_a_call_is_caught(self, tmp_path: Path) -> None:
        module = _module(tmp_path, """
            import random


            def pick(items):
                return random.choice(items)
        """)
        assert randomness_findings([module])

    def test_from_random_import_shuffle_is_caught(self, tmp_path: Path) -> None:
        module = _module(tmp_path, """
            from random import shuffle


            def mix(items):
                shuffle(items)
                return items
        """)
        assert randomness_findings([module])

    def test_an_aliased_random_module_is_caught(self, tmp_path: Path) -> None:
        """Aliasing is the obvious way past a name-based check."""
        module = _module(tmp_path, """
            import random as rnd


            def pick(items):
                return rnd.choice(items)
        """)
        assert randomness_findings([module])

    def test_secrets_is_caught(self, tmp_path: Path) -> None:
        module = _module(tmp_path, """
            import secrets

            TOKEN = secrets.token_hex(8)
        """)
        assert randomness_findings([module])

    def test_os_urandom_is_caught(self, tmp_path: Path) -> None:
        module = _module(tmp_path, """
            import os

            SALT = os.urandom(16)
        """)
        assert randomness_findings([module])

    def test_a_locally_reexported_rng_factory_is_caught(self, tmp_path: Path) -> None:
        """The only form `_STOCHASTIC_NAMES` alone can catch.

        Found while probing this gate: removing `default_rng` from that set
        left the gate green, because `np.random.default_rng()` is caught by
        the numpy attribute rule and `from numpy.random import default_rng`
        by the module rule. A project-local re-export — a helper module that
        hands out the factory — is caught by neither, so without this case the
        set was untested and could have been deleted as dead.
        """
        module = _module(tmp_path, """
            from mylib.helpers import default_rng

            RNG = default_rng(7)
        """)
        assert randomness_findings([module]), "a re-exported rng factory was missed"

    def test_an_alias_chain_without_a_flagged_import_is_caught(
        self, tmp_path: Path
    ) -> None:
        """Isolates alias *resolution* from the import record.

        `import numpy as np` is not itself a finding, so if the alias were not
        tracked the later `np.random.choice(...)` would go unseen. Probing with
        `import random as rnd` could not show this, because there the import
        alone is already a finding.
        """
        module = _module(tmp_path, """
            import numpy as np


            def pick(items):
                return np.random.choice(items)
        """)
        findings = randomness_findings([module])
        assert findings
        assert all("import" not in f["construct"] for f in findings), (
            "the finding must come from the call, not from the numpy import"
        )

    def test_an_unused_import_alone_is_caught(self, tmp_path: Path) -> None:
        """An import with no call yet is still a stochastic dependency."""
        module = _module(tmp_path, """
            import random

            VALUE = 1
        """)
        assert randomness_findings([module])


class TestWhatAFindingSays:
    def test_a_finding_names_the_file_the_line_and_the_construct(
        self, tmp_path: Path
    ) -> None:
        """A bare filename makes the claim unauditable."""
        module = _module(tmp_path, """
            import random

            VALUE = random.random()
        """)
        findings = randomness_findings([module])
        assert findings
        first = findings[0]
        assert first["file"].endswith("probe.py")
        assert isinstance(first["line"], int)
        assert first["line"] > 0
        assert "random" in first["construct"]

    def test_an_unparseable_file_is_reported_rather_than_skipped(
        self, tmp_path: Path
    ) -> None:
        """A file the probe cannot read is unknown, not clean (invariant 2)."""
        module = _module(tmp_path, """
            def broken(
        """)
        findings = randomness_findings([module])
        assert findings, "a syntax error read as 'no randomness' is a false green"
        assert any("unparseable" in f["construct"] for f in findings)

    def test_findings_are_sorted_so_the_manifest_is_stable(self, tmp_path: Path) -> None:
        """Two runs of the same tree must produce byte-identical provenance."""
        first = _module(tmp_path, """
            import random

            A = random.random()
        """, name="a.py")
        second = _module(tmp_path, """
            import secrets

            B = secrets.token_hex(4)
        """, name="b.py")
        one = randomness_findings([second, first])
        two = randomness_findings([first, second])
        assert one == two


class TestTheLivePipeline:
    def test_the_pipeline_reports_no_randomness_and_says_how(self) -> None:
        claim = stochastic_components(ROOT)
        assert claim["present"] is False
        assert claim["files"] == []
        assert "ast" in claim["evidence"].lower(), (
            "the claim must say how it was established; a textual grep cannot "
            "tell code from a docstring"
        )
        assert "git grep" not in claim["evidence"]

    def test_the_probe_no_longer_needs_to_exempt_itself(self) -> None:
        """The textual probe skipped its own file; the AST one must not.

        `run_manifest.py` names `random`, `secrets` and `default_rng` as
        string constants in order to look for them. Under a grep that was a
        self-match needing a carve-out; under an AST walk a constant is
        neither an import nor a call, so the exemption goes — and this test is
        what stops it coming back silently.
        """
        import src.core.run_manifest as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        assert ":!src/core/run_manifest.py" not in source
        assert randomness_findings([Path(module.__file__)]) == []

    def test_the_probe_actually_looked_at_the_source_tree(self) -> None:
        """`present: False` from an empty file list would be vacuous."""
        claim = stochastic_components(ROOT)
        assert claim["scanned"] > 50, (
            f"the probe only scanned {claim['scanned']} files; a claim of "
            "'no randomness' over nothing is not a measurement"
        )
