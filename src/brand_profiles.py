"""
Brand registry for brand-aware report runs.

This keeps brand selection separate from the Shopify analysis logic so we can
support multiple stores with different credentials without hardcoding secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, Tuple


def normalize_brand_slug(value: str | None) -> str:
    """
    Normalize a brand name into a stable slug.

    Accepts values like "Eddy", "/eddy", or "eddy market" and converts them
    into lowercase slug form for lookups and file naming.
    """
    if value is None:
        return ""

    slug = str(value).strip().lower()
    slug = slug.lstrip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


@dataclass(frozen=True)
class BrandProfile:
    slug: str
    display_name: str
    env_prefix: str
    aliases: Tuple[str, ...] = ()

    def env_var(self, suffix: str) -> str:
        return f"{self.env_prefix}_{suffix}"


BRAND_PROFILES: Tuple[BrandProfile, ...] = (
    BrandProfile(
        slug="eddy",
        display_name="Eddy",
        env_prefix="EDDY",
        aliases=("eddy market", "eddy-market", "eddy store"),
    ),
    BrandProfile(
        slug="steele",
        display_name="Steele",
        env_prefix="STEELE",
        aliases=("steele brand", "steele-store", "steele-label", "steel label"),
    ),
)


def _build_lookup_keys(profile: BrandProfile) -> Iterable[str]:
    yield profile.slug
    yield normalize_brand_slug(profile.display_name)
    yield normalize_brand_slug(profile.env_prefix)
    for alias in profile.aliases:
        yield normalize_brand_slug(alias)


BRAND_PROFILE_LOOKUP: Dict[str, BrandProfile] = {}
for profile in BRAND_PROFILES:
    for key in _build_lookup_keys(profile):
        if key:
            BRAND_PROFILE_LOOKUP[key] = profile


def resolve_brand_profile(value: str | None) -> BrandProfile:
    """
    Look up a brand profile from a command-line argument or environment value.
    """
    slug = normalize_brand_slug(value or "eddy")
    profile = BRAND_PROFILE_LOOKUP.get(slug)
    if profile is None:
        supported = ", ".join(profile.slug for profile in BRAND_PROFILES)
        raise ValueError(
            f"Unknown brand '{value}'. Supported brands: {supported}. "
            "Add a new BrandProfile entry in src/brand_profiles.py to support more stores."
        )
    return profile


def supported_brand_slugs() -> list[str]:
    """Return the supported brand slugs in display order."""
    return [profile.slug for profile in BRAND_PROFILES]
