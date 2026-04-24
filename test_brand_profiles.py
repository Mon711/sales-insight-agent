import unittest
from unittest.mock import patch

from src.brand_profiles import resolve_brand_profile, supported_brand_slugs
from src.shopify_client import ShopifyGraphQLClient


class TestBrandProfiles(unittest.TestCase):
    def test_supported_brand_slugs(self):
        self.assertEqual(supported_brand_slugs(), ["eddy", "steele"])

    def test_resolve_brand_profile_accepts_aliases_and_slashes(self):
        self.assertEqual(resolve_brand_profile("Eddy").slug, "eddy")
        self.assertEqual(resolve_brand_profile("/steele").slug, "steele")

    def test_shopify_client_prefers_brand_specific_env_vars(self):
        with patch.dict(
            "os.environ",
            {
                "STEELE_SHOPIFY_SHOP_NAME": "steele-store",
                "STEELE_SHOPIFY_ACCESS_TOKEN": "steele-token",
            },
            clear=False,
        ):
            client = ShopifyGraphQLClient(brand_slug="steele")

        self.assertEqual(client.shop_name, "steele-store")
        self.assertEqual(client.access_token, "steele-token")
        self.assertEqual(client.brand_slug, "steele")

    def test_shopify_client_falls_back_to_generic_env_vars(self):
        with patch.dict(
            "os.environ",
            {
                "SHOPIFY_SHOP_NAME": "generic-store",
                "SHOPIFY_ACCESS_TOKEN": "generic-token",
            },
            clear=False,
        ):
            client = ShopifyGraphQLClient()

        self.assertEqual(client.shop_name, "generic-store")
        self.assertEqual(client.access_token, "generic-token")


if __name__ == "__main__":
    unittest.main()
