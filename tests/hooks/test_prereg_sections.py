"""Every pre-registration section has an owner, and every owner names a real one.

Roadmap A13. `FAZ A`'s items were written against a template that was never
built: one where item *n* fills section *n* (`A2`→§2, `A3`→§3, … `A11`→§11).
The template the `pre-register` skill generates has ten semantically-organised
sections, so the two coincide only at `A1`→§1. `A11`'s criterion pointed at
**§11, which does not exist**.

Left alone this is not cosmetic. Each criterion is what `fix-done` checks at
closure, so every item from `A2` on would have closed against the wrong
section — and `A12` locks the document permanently (invariant 6). A
pre-registration whose sample description sits under "Primary metric" cannot
be fixed afterwards.

**The measurement that shaped these tests.** The first version checked that
every section number appeared in some criterion, and it passed — because `A8`
named §8 and `A9` named §9 purely because the digits matched, while `A8` is a
detectability filter and §8 is the stopping rule. A check that counts numbers
passes on exactly the arrangement it exists to catch. So the mapping is
declared in `.claude/prereg_sections.yaml` with each section's expected title,
and it is checked against both the template and the roadmap, in both
directions.

The hole that mapping exposed: **§8 (stopping rule) and §9 (negative result)
had no owner.** Nothing in the roadmap mentioned a stopping rule, though the
`pre-register` skill lists it among the fields that cannot be revised later;
and invariant 7 made the negative-result path feel covered, which is how its
absence from the *plan* stayed invisible — a rule is not a written plan.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs" / "PRE_REGISTRATION.md"
ROADMAP = ROOT / "SCIENTIFIC_ROADMAP.md"
MAP = ROOT / ".claude" / "prereg_sections.yaml"

sys.path.insert(0, str(ROOT / ".claude" / "hooks"))

import _status  # noqa: E402


def template_sections() -> dict[int, str]:
    """Numbered `## N. Title` headings in the pre-registration."""
    out: dict[int, str] = {}
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^##\s+(\d+)\.\s+(.+?)\s*$", line)
        if match:
            out[int(match.group(1))] = match.group(2)
    return out


def section_map() -> dict[int, dict[str, object]]:
    raw = yaml.safe_load(MAP.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw["sections"].items()}


def roadmap_items() -> dict[str, _status.Item]:
    return {i.id: i for i in _status.parse_roadmap(ROADMAP.read_text(encoding="utf-8"))}


def sections_named_by(item: _status.Item) -> set[int]:
    return {int(n) for n in re.findall(r"§\s*(\d+)", item.criterion or "")}


@pytest.fixture(scope="module")
def sections() -> dict[int, str]:
    found = template_sections()
    assert found, "no numbered sections parsed from the pre-registration"
    return found


@pytest.fixture(scope="module")
def mapping() -> dict[int, dict[str, object]]:
    return section_map()


class TestTheMapMatchesTheTemplate:
    def test_every_mapped_section_exists_with_that_title(
        self, sections: dict[int, str], mapping: dict[int, dict[str, object]]
    ) -> None:
        bad: list[str] = []
        for number, entry in mapping.items():
            if number not in sections:
                bad.append(f"map names §{number}, template has §1-§{max(sections)}")
                continue
            title = str(entry["title"])
            if title.lower() not in sections[number].lower():
                bad.append(
                    f"§{number} is titled {sections[number]!r}, map expects "
                    f"{title!r}"
                )
        assert not bad, "; ".join(bad)

    def test_every_template_section_is_in_the_map(
        self, sections: dict[int, str], mapping: dict[int, dict[str, object]]
    ) -> None:
        """A new section with no map entry is a section nobody will fill."""
        missing = {n: t for n, t in sections.items() if n not in mapping}
        assert not missing, (
            "template sections absent from the map: "
            + ", ".join(f"§{n} ({t})" for n, t in sorted(missing.items()))
        )


class TestEverySectionHasARealOwner:
    def test_no_section_is_unclaimed(
        self, mapping: dict[int, dict[str, object]]
    ) -> None:
        unowned = [
            number
            for number, entry in mapping.items()
            if not entry.get("owners") and not entry.get("unowned_by_design")
        ]
        assert not unowned, f"sections with no owner: {sorted(unowned)}"

    def test_every_owner_is_a_real_roadmap_item(
        self, mapping: dict[int, dict[str, object]]
    ) -> None:
        """A typo'd owner id is an unowned section that looks owned."""
        items = roadmap_items()
        bad: list[str] = []
        for number, entry in mapping.items():
            for owner in entry.get("owners") or []:
                if owner not in items:
                    bad.append(f"§{number} is owned by {owner}, which is not an item")
        assert not bad, "; ".join(bad)

    def test_the_stopping_rule_and_negative_result_are_owned(
        self, sections: dict[int, str], mapping: dict[int, dict[str, object]]
    ) -> None:
        """The two A13 found empty. Named explicitly so they stay named."""
        for keyword in ("Durdurma", "Negatif"):
            number = next((n for n, t in sections.items() if keyword in t), None)
            assert number is not None, f"the template lost its {keyword} section"
            owners = (mapping.get(number) or {}).get("owners") or []
            assert owners, f"§{number} ({keyword}) has no owner"


class TestTheRoadmapCriteriaAgreeWithTheMap:
    def test_each_owner_criterion_names_its_mapped_section(
        self, mapping: dict[int, dict[str, object]]
    ) -> None:
        """This is the direction that was wrong for every item but A1."""
        items = roadmap_items()
        bad: list[str] = []
        for number, entry in mapping.items():
            for owner in entry.get("owners") or []:
                item = items.get(owner)
                if item is None:
                    continue  # covered by its own test
                named = sections_named_by(item)
                if named and number not in named:
                    bad.append(
                        f"{owner} is mapped to §{number} but its criterion names "
                        f"{sorted(named) or 'no section'}"
                    )
        assert not bad, "; ".join(bad)

    def test_no_criterion_names_a_section_it_does_not_own(
        self, mapping: dict[int, dict[str, object]]
    ) -> None:
        owned: dict[str, set[int]] = {}
        for number, entry in mapping.items():
            for owner in entry.get("owners") or []:
                owned.setdefault(owner, set()).add(number)
        bad: list[str] = []
        for item_id, item in roadmap_items().items():
            if not re.fullmatch(r"A\d+[a-z]?|E1", item_id):
                continue
            for number in sections_named_by(item):
                if number not in owned.get(item_id, set()):
                    bad.append(f"{item_id} names §{number} but does not own it")
        assert not bad, "; ".join(bad)


class TestTheLockWaitsForEverySection:
    def test_a12_depends_on_every_section_owner(
        self, mapping: dict[int, dict[str, object]]
    ) -> None:
        """A12 commits the document; it must not be reachable while it is partial.

        Dependencies resolve transitively, the same way `next-fix` resolves
        them — so a missing edge here would also have let `next-fix` offer A12
        before the plan was written.
        """
        items = roadmap_items()
        assert "A12" in items, "A12 is gone"

        def ancestors(item_id: str, seen: set[str] | None = None) -> set[str]:
            seen = set() if seen is None else seen
            item = items.get(item_id)
            if item is None:
                return seen
            for dep in item.deps:
                if dep not in seen:
                    seen.add(dep)
                    ancestors(dep, seen)
            return seen

        reachable = ancestors("A12")
        owners = {
            owner
            for entry in mapping.values()
            for owner in (entry.get("owners") or [])
        } - {"A12", "A1"}  # A1 is closed; its section is written
        missing = {owner for owner in owners if owner not in reachable}
        assert not missing, (
            f"A12 is reachable without these section owners: {sorted(missing)}"
        )
