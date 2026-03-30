"""
Central configuration for sub-channel definitions, commission rates, and reporting dates.

This is the single source of truth for:
- Report date range (REPORT_SINCE, REPORT_UNTIL)
- Sub-channel definitions and Shopify sales_channel mappings
- Commission rates per sub-channel
- Excluded channels and order tags
"""

from typing import Dict, Any, List

# Report date range — Q1 2026 (Jan 1 to Mar 31)
REPORT_SINCE = "2026-01-01"
REPORT_UNTIL = "2026-03-31"

# Sub-channel configuration: defines how each sub-channel is identified in Shopify,
# what commission rates apply, and special business rules (e.g., wholesale revenue estimation).
#
# Key concepts:
# - commission_rate: used to compute true_net_sales = net_sales * (1 - commission_rate)
# - filter_type: how to identify orders in this sub-channel (sales_channel, order_tag, etc.)
# - parent: logical grouping (e.g., all dropship_* have parent="dropship_group")
#
# The dropship_* sub-channels have shopify_channel=None because their exact sales_channel
# names must be confirmed via a discovery query. Update these after running discovery.
SUB_CHANNEL_CONFIG: Dict[str, Dict[str, Any]] = {
    "online_store": {
        "parent": "online_store_group",
        "commission_rate": 0.0,
        "filter_type": "sales_channel_multi",
        "shopify_channels": ["Online Store", "Shop", "Facebook & Instagram"],
        "exclude_tags": ["Manymoons", "shopmy"],
        "description": "Direct online sales (website, social, shop app)",
    },
    "pos": {
        "parent": "pos",
        "commission_rate": 0.0,
        "filter_type": "sales_channel",
        "shopify_channel": "Point of Sale",
        "description": "In-store point of sale transactions",
    },
    "wholesale": {
        "parent": "wholesale",
        "commission_rate": 0.0,
        "filter_type": "order_tag",
        "tag": "wholesale",
        "estimated_revenue_factor": 0.5,
        "description": "Wholesale orders (identified by 'wholesale' tag); payment offline, net_sales=$0",
    },
    "dropship_nordstrom": {
        "parent": "dropship_group",
        "commission_rate": 0.20,
        "filter_type": "order_tag",
        "tag": "Nordstrom",
        "description": "Nordstrom via Mirakl (commission: 20%)",
    },
    "dropship_bloomingdales": {
        "parent": "dropship_group",
        "commission_rate": 0.25,
        "filter_type": "order_tag",
        "tag": "Bloomingdale''s",
        "description": "Bloomingdale's via Mirakl (commission: 25%)",
    },
    "dropship_macys": {
        "parent": "dropship_group",
        "commission_rate": 0.18,
        "filter_type": "order_tag",
        "tag": "Macy''s",
        "description": "Macy's (commission: 18%)",
    },
    "dropship_shop_couper": {
        "parent": "dropship_group",
        "commission_rate": 0.40,
        "filter_type": "order_tag",
        "tag": "couper",
        "description": "Shop Couper (commission: 40%)",
    },
    "dropship_over_the_moon": {
        "parent": "dropship_group",
        "commission_rate": 0.40,
        "filter_type": "order_tag",
        "tag": "Over The Moon",
        "description": "Over the Moon via fabric (commission: 40%)",
    },
}

# Channels to exclude from reports (not real revenue)
EXCLUDED_CHANNELS: List[str] = [
    "Draft Orders",
    "Shopmy Integration",
    "Loop Returns & Exchanges",
    "Shopify Mobile for iPhone",
]

# Order tags to exclude from reports (not real revenue)
EXCLUDED_TAGS: List[str] = [
    "shopmy",      # Gifting / influencer orders (sent for free)
    "Manymoons",   # Heavy discount orders, distort metrics
]


def get_active_sub_channels() -> List[str]:
    """Return list of sub-channel keys that have confirmed shopify_channel values."""
    return [
        key for key, cfg in SUB_CHANNEL_CONFIG.items()
        if cfg.get("shopify_channel") is not None or cfg.get("filter_type") != "sales_channel"
    ]


def get_unconfirmed_sub_channels() -> List[str]:
    """Return list of dropship sub-channels waiting for discovery query confirmation."""
    return [
        key for key, cfg in SUB_CHANNEL_CONFIG.items()
        if cfg.get("shopify_channel") is None and cfg.get("filter_type") == "sales_channel"
    ]
