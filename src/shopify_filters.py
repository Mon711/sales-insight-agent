"""
Business rule filters for Shopify orders.

These functions apply business rules to determine which orders represent
"real revenue" and should be included in analysis.

Each filter is:
- Independent: operates on a list of orders
- Transparent: explains what it excludes and why
- Composable: can be applied in sequence
- Easy to modify: simple logic, clear comments
"""

from typing import List, Dict, Any, Callable


# =============================================================================
# TIER 1: Safe, Always-Exclude Filters
# =============================================================================


def exclude_test_orders(orders: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Exclude orders marked as test orders.

    Shopify's `test` flag explicitly marks orders created during testing.
    These should never be counted as real revenue.

    Args:
        orders: List of raw orders from Shopify API

    Returns:
        Tuple of (filtered_orders, exclusion_stats)
        - filtered_orders: Orders where test == False
        - exclusion_stats: {"test_orders_excluded": count}
    """
    filtered = [order for order in orders if not order.get("test", False)]
    excluded_count = len(orders) - len(filtered)

    return filtered, {"test_orders_excluded": excluded_count}


def exclude_cancelled_orders(orders: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Exclude orders that were cancelled.

    A cancelled order has a `cancelledAt` timestamp, indicating when it was cancelled.
    Cancelled orders should not be counted as revenue.

    Note: This is a simple approach. In future, we may need to:
    - Check if the order was partially fulfilled before cancellation
    - Handle refunded amounts separately
    - Understand if "cancelled" means fully refunded or just status change

    Args:
        orders: List of orders (ideally already filtered by exclude_test_orders)

    Returns:
        Tuple of (filtered_orders, exclusion_stats)
        - filtered_orders: Orders where cancelledAt is null
        - exclusion_stats: {"cancelled_orders_excluded": count}
    """
    filtered = [order for order in orders if order.get("cancelledAt") is None]
    excluded_count = len(orders) - len(filtered)

    return filtered, {"cancelled_orders_excluded": excluded_count}


# =============================================================================
# TIER 2: TODO - Needs Business Decision
# =============================================================================
# The following filters are NOT YET IMPLEMENTED because they require
# understanding Eddy's business rules. Before implementing these, we need to:
# 1. Inspect real order data
# 2. Discuss with Eddy team which orders count as "real revenue"
# 3. Understand edge cases


def filter_by_payment_status(orders: List[Dict[str, Any]], fully_paid_only: bool = True) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    TODO: Decide payment status filtering rules.

    Question: Do partially paid orders count as revenue?
    - If `fully_paid_only=True`: Only orders where `fullyPaid == True`
    - If `fully_paid_only=False`: All orders, regardless of payment status

    Depends on: How Eddy recognizes revenue (accrual vs cash basis)

    Args:
        orders: List of orders
        fully_paid_only: If True, exclude partially paid orders

    Returns:
        Tuple of (filtered_orders, exclusion_stats)
    """
    if fully_paid_only:
        filtered = [order for order in orders if order.get("fullyPaid", False)]
        excluded_count = len(orders) - len(filtered)
        return filtered, {"partially_paid_orders_excluded": excluded_count}
    else:
        return orders, {"partially_paid_orders_excluded": 0}


def filter_by_fulfillment_status(
    orders: List[Dict[str, Any]],
    include_statuses: List[str] = None
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    TODO: Decide fulfillment status filtering rules.

    Question: Which fulfillment statuses count as revenue?
    - "shipped": Order has been shipped
    - "unshipped": Order not yet shipped
    - "partial": Order partially shipped
    - "cancelled": Order cancellation (may overlap with cancelled orders)
    - "restocked": Order cancelled and inventory returned

    Depends on: Whether revenue is recognized on order creation or shipment

    Args:
        orders: List of orders
        include_statuses: List of displayFulfillmentStatus values to include
                         If None, includes all non-cancelled orders

    Returns:
        Tuple of (filtered_orders, exclusion_stats)
    """
    # Placeholder implementation - not yet decided
    if include_statuses is None:
        include_statuses = ["shipped", "partial", "unshipped"]

    filtered = [
        order for order in orders
        if order.get("displayFulfillmentStatus") in include_statuses
    ]
    excluded_count = len(orders) - len(filtered)

    return filtered, {"fulfillment_status_excluded": excluded_count}


def filter_by_channel(
    orders: List[Dict[str, Any]],
    exclude_channels: List[str] = None
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    TODO: Decide which channels are "real revenue".

    Question: Are all sales channels real revenue? Or are some internal/test?
    Eddy mentioned: website, physical store/POS, wholesale, dropship

    Need to determine:
    - Are all channels external sales? Or are some internal transfers?
    - Should wholesale and dropship be separate from website/POS?
    - Are there any "fake" channels used for internal orders?

    Args:
        orders: List of orders
        exclude_channels: List of channel displayNames to exclude
                         Example: ["internal", "test_channel"]
                         If None, includes all channels

    Returns:
        Tuple of (filtered_orders, exclusion_stats)
    """
    if exclude_channels is None:
        exclude_channels = []

    filtered = [
        order for order in orders
        if order.get("channelInformation", {}).get("displayName") not in exclude_channels
    ]
    excluded_count = len(orders) - len(filtered)

    return filtered, {"channel_excluded": excluded_count}


def filter_by_draft_or_internal(orders: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    TODO: Understand and filter draft/internal orders.

    Question: What indicates a "draft" or "internal operational" order?
    - Is there a specific status field?
    - Does the `closed` field indicate draft status?
    - Are there specific channel names for internal use?

    Current Shopify order fields that might help:
    - `closed`: Boolean field (meaning TBD - is this draft status?)
    - Order status (may be available in other queries)

    Need to:
    1. Inspect real orders to understand what "draft" looks like
    2. Determine if we should exclude these orders
    3. Understand Eddy's internal ordering process

    Args:
        orders: List of orders

    Returns:
        Tuple of (filtered_orders, exclusion_stats)
    """
    # Placeholder - not yet implemented
    # For now, include all orders; revisit when we understand the data better
    return orders, {"draft_or_internal_excluded": 0}


def filter_refunds(orders: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    TODO: Handle refunds and adjustments.

    Question: How should refunds be treated?
    - Should refunded orders be excluded entirely?
    - Should only the refunded amount be subtracted from revenue?
    - Are refunds tracked in the order record or separately?

    Current approach: The totalPriceSet includes the final amount.
    For most analysis, this is probably correct.

    But we should handle:
    - Fully refunded orders (totalPrice = 0)
    - Partially refunded orders (need to track separately?)
    - Refund timing (do we count by order date or refund date?)

    Args:
        orders: List of orders

    Returns:
        Tuple of (filtered_orders, exclusion_stats)
    """
    # Placeholder - not yet implemented
    return orders, {"refund_adjustments": 0}


# =============================================================================
# FILTER PIPELINE
# =============================================================================


def apply_filters(orders: List[Dict[str, Any]], verbose: bool = True) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Apply all active filters in sequence.

    Currently active filters (Tier 1 - safe):
    1. Exclude test orders
    2. Exclude cancelled orders

    Args:
        orders: Raw orders from Shopify API
        verbose: If True, print status of each filter

    Returns:
        Tuple of (filtered_orders, exclusion_summary)
        - filtered_orders: Orders passing all filters
        - exclusion_summary: Dict with counts of what was excluded
    """
    all_stats = {}
    current_orders = orders

    if verbose:
        print(f"\n{'='*60}")
        print("Applying Business Filters")
        print(f"{'='*60}")
        print(f"Starting with: {len(current_orders)} orders\n")

    # Apply Tier 1 filters (safe, always-on)
    current_orders, stats = exclude_test_orders(current_orders)
    all_stats.update(stats)
    if verbose:
        print(f"After excluding test orders: {len(current_orders)} remaining")
        if stats["test_orders_excluded"] > 0:
            print(f"  → Excluded: {stats['test_orders_excluded']} test orders")

    current_orders, stats = exclude_cancelled_orders(current_orders)
    all_stats.update(stats)
    if verbose:
        print(f"After excluding cancelled orders: {len(current_orders)} remaining")
        if stats["cancelled_orders_excluded"] > 0:
            print(f"  → Excluded: {stats['cancelled_orders_excluded']} cancelled orders")

    # Tier 2 filters (TODO - not yet active)
    # Uncomment when business rules are decided:
    # current_orders, stats = filter_by_payment_status(current_orders)
    # all_stats.update(stats)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Final result: {len(current_orders)} orders")
        print(f"{'='*60}")
        print(f"\nExclusion summary:")
        for filter_name, count in all_stats.items():
            if count > 0:
                print(f"  • {filter_name}: {count}")

    return current_orders, all_stats


if __name__ == "__main__":
    # Simple test: show filter behavior with mock data
    mock_orders = [
        {"name": "#001", "test": False, "cancelledAt": None},
        {"name": "#002", "test": True, "cancelledAt": None},  # Will be excluded
        {"name": "#003", "test": False, "cancelledAt": "2024-01-15T10:00:00Z"},  # Will be excluded
        {"name": "#004", "test": False, "cancelledAt": None},
        {"name": "#005", "test": False, "cancelledAt": None},
    ]

    filtered, stats = apply_filters(mock_orders)
    print(f"\nFiltered orders: {[o['name'] for o in filtered]}")
