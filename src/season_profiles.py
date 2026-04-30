"""
Season registry for season-aware product reporting.

This keeps season labels, Shopify tags, and analysis windows in one place so the
same reporting pipeline can be reused for Winter'25, Resort'25, Autumn'25, and
the other Steele season buckets without hardcoding tag spelling in multiple files.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, Tuple


def normalize_season_slug(value: str | None) -> str:
    """
    Normalize a season label into a stable slug.

    Examples:
      - Winter'25 -> winter25
      - Winter 25 -> winter25
      - winter25  -> winter25
    """
    if value is None:
        return ""

    slug = str(value).strip().lower()
    slug = slug.replace("'", "")
    slug = slug.lstrip("/")
    slug = re.sub(r"[^a-z0-9]+", "", slug)
    return slug.strip("-")


@dataclass(frozen=True)
class SeasonProfile:
    slug: str
    display_name: str
    shopify_tag: str
    since: str
    until: str
    aliases: Tuple[str, ...] = ()

    def output_label(self) -> str:
        """Return a filename-friendly label for report folders and image assets."""
        return self.slug


SEASON_PROFILES: Tuple[SeasonProfile, ...] = (
    SeasonProfile(
        slug="winter25",
        display_name="Winter'25",
        shopify_tag="Winter25",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("winter'25", "winter 25", "winter25"),
    ),
    SeasonProfile(
        slug="spring25",
        display_name="Spring'25",
        shopify_tag="Spring25",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("spring'25", "spring 25", "spring25"),
    ),
    SeasonProfile(
        slug="summer25",
        display_name="Summer'25",
        shopify_tag="Summer25",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("summer'25", "summer 25", "summer25"),
    ),
    SeasonProfile(
        slug="resort25",
        display_name="Resort'25",
        shopify_tag="Resort25",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("resort'25", "resort 25", "resort25"),
    ),
    SeasonProfile(
        slug="autumn25",
        display_name="Autumn'25",
        shopify_tag="Autumn25",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("autumn'25", "autumn 25", "autumn25"),
    ),
    SeasonProfile(
        slug="winter26",
        display_name="Winter'26",
        shopify_tag="Winter26",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("winter'26", "winter 26", "winter26"),
    ),
    SeasonProfile(
        slug="essentials25",
        display_name="Essentials'25",
        shopify_tag="Essentials25",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("essentials'25", "essentials 25", "essentials25"),
    ),
    SeasonProfile(
        slug="essentials26",
        display_name="Essentials'26",
        shopify_tag="Essentials26",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("essentials'26", "essentials 26", "essentials26"),
    ),
    SeasonProfile(
        slug="autumn26",
        display_name="Autumn'26",
        shopify_tag="Autumn26",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("autumn'26", "autumn 26", "autumn26"),
    ),
    SeasonProfile(
        slug="resort24",
        display_name="Resort'24",
        shopify_tag="Resort24",
        since="2024-12-01",
        until="2026-04-30",
        aliases=("resort'24", "resort 24", "resort24"),
    ),
)


def _build_lookup_keys(profile: SeasonProfile) -> Iterable[str]:
    yield profile.slug
    yield normalize_season_slug(profile.display_name)
    yield normalize_season_slug(profile.shopify_tag)
    for alias in profile.aliases:
        yield normalize_season_slug(alias)


SEASON_PROFILE_LOOKUP: Dict[str, SeasonProfile] = {}
for profile in SEASON_PROFILES:
    for key in _build_lookup_keys(profile):
        if key:
            SEASON_PROFILE_LOOKUP[key] = profile


def resolve_season_profile(value: str | None) -> SeasonProfile:
    """
    Look up a season profile from a user-provided label or environment value.
    """
    slug = normalize_season_slug(value or "winter25")
    profile = SEASON_PROFILE_LOOKUP.get(slug)
    if profile is None:
        supported = ", ".join(profile.slug for profile in SEASON_PROFILES)
        raise ValueError(
            f"Unknown season '{value}'. Supported seasons: {supported}. "
            "Add a new SeasonProfile entry in src/season_profiles.py to support more seasons."
        )
    return profile


def supported_season_slugs() -> list[str]:
    """Return the supported season slugs in display order."""
    return [profile.slug for profile in SEASON_PROFILES]
