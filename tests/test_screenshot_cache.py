"""Comprehensive tests for screenshot caching system in core/screenshot.py.

Tests internal cache functions: _screenshot_cache_key, _get_screenshot_from_cache,
_store_screenshot_in_cache, get_screenshot_cache_stats, clear_screenshot_cache,
invalidate_screenshot_cache, and cache integration in capture_screen/capture_region.
"""

import time
from unittest.mock import patch

from PIL import Image

from core import screenshot as sc


class TestScreenshotCacheKey:
    """Tests for _screenshot_cache_key function (lines 71-75)."""

    def test_region_key_format(self):
        """Region key should include x,y,w,h coordinates."""
        key = sc._screenshot_cache_key(region=(10, 20, 100, 200))
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length

    def test_monitor_key_format(self):
        """Monitor key should include monitor index."""
        key = sc._screenshot_cache_key(monitor=2)
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hash length

    def test_different_regions_produce_different_keys(self):
        """Different region parameters should produce different cache keys."""
        key1 = sc._screenshot_cache_key(region=(10, 20, 100, 200))
        key2 = sc._screenshot_cache_key(region=(10, 20, 100, 201))
        assert key1 != key2

    def test_different_monitors_produce_different_keys(self):
        """Different monitor indices should produce different cache keys."""
        key1 = sc._screenshot_cache_key(monitor=1)
        key2 = sc._screenshot_cache_key(monitor=2)
        assert key1 != key2

    def test_region_vs_monitor_produce_different_keys(self):
        """Region and monitor keys should be different even for same screen area."""
        region_key = sc._screenshot_cache_key(region=(0, 0, 1920, 1080))
        monitor_key = sc._screenshot_cache_key(monitor=1)
        assert region_key != monitor_key


class TestGetScreenshotFromCache:
    """Tests for _get_screenshot_from_cache function (lines 91-101)."""

    def setup_method(self):
        """Clear cache before each test."""
        sc._SCREENSHOT_CACHE.clear()
        sc._screenshot_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    def test_cache_miss_when_empty(self):
        """Should return None when cache is empty."""
        result = sc._get_screenshot_from_cache("nonexistent", time.monotonic())
        assert result is None
        assert sc._screenshot_cache_stats["misses"] == 1

    def test_cache_hit_within_ttl(self):
        """Should return cached image if within TTL."""
        img = Image.new("RGB", (100, 100), "red")
        cache_key = "test_key"
        current_time = time.monotonic()

        sc._SCREENSHOT_CACHE[cache_key] = (img, current_time)
        result = sc._get_screenshot_from_cache(cache_key, current_time + 0.1)

        assert result is img
        assert sc._screenshot_cache_stats["hits"] == 1
        assert sc._screenshot_cache_stats["misses"] == 0

    def test_cache_miss_after_ttl_expires(self):
        """Should return None and remove expired entry."""
        img = Image.new("RGB", (100, 100), "blue")
        cache_key = "test_key"
        old_time = time.monotonic() - sc._SCREENSHOT_CACHE_TTL - 1

        sc._SCREENSHOT_CACHE[cache_key] = (img, old_time)
        current_time = time.monotonic()
        result = sc._get_screenshot_from_cache(cache_key, current_time)

        assert result is None
        assert cache_key not in sc._SCREENSHOT_CACHE
        assert sc._screenshot_cache_stats["misses"] == 1

    def test_cache_miss_at_exact_ttl_boundary(self):
        """Should expire exactly at TTL boundary (not within)."""
        img = Image.new("RGB", (100, 100), "green")
        cache_key = "test_key"
        old_time = time.monotonic() - sc._SCREENSHOT_CACHE_TTL

        sc._SCREENSHOT_CACHE[cache_key] = (img, old_time)
        current_time = time.monotonic()
        result = sc._get_screenshot_from_cache(cache_key, current_time)

        # At exactly TTL, it should be expired (not "current_time - timestamp < TTL")
        assert result is None
        assert sc._screenshot_cache_stats["misses"] == 1


class TestStoreScreenshotInCache:
    """Tests for _store_screenshot_in_cache function (lines 117-133)."""

    def setup_method(self):
        """Clear cache and reset stats before each test."""
        sc._SCREENSHOT_CACHE.clear()
        sc._screenshot_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    def test_store_and_retrieve(self):
        """Should store image and retrieve it with same identity."""
        img = Image.new("RGB", (50, 50), "yellow")
        cache_key = "store_test"
        current_time = time.monotonic()

        sc._store_screenshot_in_cache(cache_key, img, current_time)
        retrieved = sc._get_screenshot_from_cache(cache_key, current_time + 0.1)

        assert retrieved is img  # Same object identity

    def test_removes_expired_entries_before_storing(self):
        """Should remove expired entries even when not at max capacity."""
        img1 = Image.new("RGB", (50, 50), "red")
        img2 = Image.new("RGB", (50, 50), "blue")
        key1 = "expired_key"
        key2 = "fresh_key"
        old_time = time.monotonic() - sc._SCREENSHOT_CACHE_TTL - 1
        current_time = time.monotonic()

        # Store expired entry
        sc._SCREENSHOT_CACHE[key1] = (img1, old_time)
        # Store new entry (should trigger cleanup of expired)
        sc._store_screenshot_in_cache(key2, img2, current_time)

        assert key1 not in sc._SCREENSHOT_CACHE
        assert key2 in sc._SCREENSHOT_CACHE

    def test_evicts_oldest_when_full(self):
        """Should evict oldest entry when cache reaches max size."""
        # Fill cache to max size
        current_time = time.monotonic()
        for i in range(sc._SCREENSHOT_CACHE_MAX_SIZE):
            key = f"key_{i}"
            img = Image.new("RGB", (10, 10), "red")
            # Store with staggered timestamps to establish age order
            sc._SCREENSHOT_CACHE[key] = (img, current_time - sc._SCREENSHOT_CACHE_TTL + i + 10)

        # Add one more (should trigger eviction)
        new_key = "new_key"
        new_img = Image.new("RGB", (10, 10), "green")
        sc._store_screenshot_in_cache(new_key, new_img, current_time)

        # New entry should be present
        assert new_key in sc._SCREENSHOT_CACHE
        # Oldest entry should be evicted (approximately)
        assert sc._screenshot_cache_stats["evictions"] > 0
        # Cache size should not exceed max
        assert len(sc._SCREENSHOT_CACHE) <= sc._SCREENSHOT_CACHE_MAX_SIZE

    def test_multiple_stores_same_key_overwrites(self):
        """Storing with same key should overwrite previous entry."""
        img1 = Image.new("RGB", (50, 50), "red")
        img2 = Image.new("RGB", (50, 50), "blue")
        cache_key = "same_key"
        current_time = time.monotonic()

        sc._store_screenshot_in_cache(cache_key, img1, current_time)
        sc._store_screenshot_in_cache(cache_key, img2, current_time + 0.1)

        retrieved = sc._get_screenshot_from_cache(cache_key, current_time + 0.2)
        assert retrieved is img2  # Should get the second image


class TestGetScreenshotCacheStats:
    """Tests for get_screenshot_cache_stats function (line 142)."""

    def setup_method(self):
        """Reset stats before each test."""
        sc._screenshot_cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

    def test_returns_copy_not_reference(self):
        """Should return a copy, not direct reference to stats dict."""
        stats = sc.get_screenshot_cache_stats()
        stats["hits"] = 999

        original = sc.get_screenshot_cache_stats()
        assert original["hits"] == 0  # Should not be modified

    def test_returns_all_stat_fields(self):
        """Should include hits, misses, and evictions."""
        sc._screenshot_cache_stats["hits"] = 5
        sc._screenshot_cache_stats["misses"] = 3
        sc._screenshot_cache_stats["evictions"] = 1

        stats = sc.get_screenshot_cache_stats()
        assert stats["hits"] == 5
        assert stats["misses"] == 3
        assert stats["evictions"] == 1


class TestClearScreenshotCache:
    """Tests for clear_screenshot_cache function (lines 147-148)."""

    def setup_method(self):
        """Populate cache before each test."""
        sc._SCREENSHOT_CACHE.clear()
        for i in range(5):
            img = Image.new("RGB", (10, 10), "red")
            sc._SCREENSHOT_CACHE[f"key_{i}"] = (img, time.monotonic())

    def test_clears_all_entries(self):
        """Should remove all entries from cache."""
        assert len(sc._SCREENSHOT_CACHE) == 5
        sc.clear_screenshot_cache()
        assert len(sc._SCREENSHOT_CACHE) == 0

    def test_idempotent(self):
        """Can be called multiple times safely."""
        sc.clear_screenshot_cache()
        sc.clear_screenshot_cache()
        assert len(sc._SCREENSHOT_CACHE) == 0


class TestInvalidateScreenshotCache:
    """Tests for invalidate_screenshot_cache function (lines 158-163)."""

    def setup_method(self):
        """Populate cache before each test."""
        sc._SCREENSHOT_CACHE.clear()
        # Add entries for different "monitors"
        for i in range(1, 4):
            img = Image.new("RGB", (10, 10), "red")
            key = sc._screenshot_cache_key(monitor=i)
            sc._SCREENSHOT_CACHE[key] = (img, time.monotonic())

    def test_invalidate_all_clears_everything(self):
        """Should clear all cache when monitor=None."""
        assert len(sc._SCREENSHOT_CACHE) > 0
        sc.invalidate_screenshot_cache(monitor=None)
        assert len(sc._SCREENSHOT_CACHE) == 0

    def test_invalidate_specific_monitor(self):
        """Should only clear cache for specified monitor."""
        monitor_1_key = sc._screenshot_cache_key(monitor=1)
        monitor_2_key = sc._screenshot_cache_key(monitor=2)

        # Ensure both are in cache
        assert monitor_1_key in sc._SCREENSHOT_CACHE
        assert monitor_2_key in sc._SCREENSHOT_CACHE

        # Invalidate monitor 1 only
        sc.invalidate_screenshot_cache(monitor=1)

        # Monitor 1 should be gone, monitor 2 should remain
        assert monitor_1_key not in sc._SCREENSHOT_CACHE
        assert monitor_2_key in sc._SCREENSHOT_CACHE

    def test_invalidate_nonexistent_monitor_no_error(self):
        """Should not error when invalidating monitor that's not cached."""
        # Should not raise exception
        sc.invalidate_screenshot_cache(monitor=999)


class TestCacheIntegrationCaptureScreen:
    """Tests for cache integration in capture_screen (lines 298-302, 332-334)."""

    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot._IN_TEST_MODE", False)
    def test_cache_hit_in_capture_screen(self, mock_pyautogui):
        """Should return cached image on second call with same monitor."""
        img1 = Image.new("RGB", (100, 100), "red")
        mock_pyautogui.screenshot.return_value = img1

        # First call should capture
        result1 = sc.capture_screen(monitor=1, use_cache=True)
        # Second call should return cached
        result2 = sc.capture_screen(monitor=1, use_cache=True)

        # Should return same object (cache hit)
        assert result1 is result2

    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot._IN_TEST_MODE", False)
    def test_cache_storage_after_capture(self, mock_pyautogui):
        """Should store captured image in cache after successful capture."""
        img = Image.new("RGB", (100, 100), "green")
        mock_pyautogui.screenshot.return_value = img

        # Clear any existing cache
        sc.clear_screenshot_cache()

        # Capture should cache the image
        result = sc.capture_screen(monitor=1, use_cache=True)

        # Verify it was stored in cache
        cache_key = sc._screenshot_cache_key(monitor=1)
        assert cache_key in sc._SCREENSHOT_CACHE
        cached_img, _ = sc._SCREENSHOT_CACHE[cache_key]
        assert cached_img is img  # Same object

    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot._IN_TEST_MODE", True)
    def test_cache_disabled_in_test_mode(self, mock_pyautogui):
        """Should bypass cache when in test mode."""
        img1 = Image.new("RGB", (100, 100), "red")
        img2 = Image.new("RGB", (100, 100), "blue")
        mock_pyautogui.screenshot.side_effect = [img1, img2]

        # Both calls should capture (no cache)
        result1 = sc.capture_screen(monitor=1, use_cache=True)
        result2 = sc.capture_screen(monitor=1, use_cache=True)

        # Should return different objects (no cache)
        assert result1 is not result2

    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot._IN_TEST_MODE", False)
    def test_cache_bypassed_with_use_cache_false(self, mock_pyautogui):
        """Should bypass cache when use_cache=False."""
        img1 = Image.new("RGB", (100, 100), "red")
        img2 = Image.new("RGB", (100, 100), "blue")
        mock_pyautogui.screenshot.side_effect = [img1, img2]

        # First call
        result1 = sc.capture_screen(monitor=1, use_cache=True)
        # Second call with cache disabled
        result2 = sc.capture_screen(monitor=1, use_cache=False)

        # Should return different objects (cache bypassed)
        assert result1 is not result2


class TestCacheIntegrationCaptureRegion:
    """Tests for cache integration in capture_region (lines 431-436, 457-460)."""

    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot._IN_TEST_MODE", False)
    def test_cache_hit_in_capture_region(self, mock_pyautogui):
        """Should return cached image on second call with same region."""
        img1 = Image.new("RGB", (50, 50), "red")
        img2 = Image.new("RGB", (50, 50), "blue")
        mock_pyautogui.screenshot.side_effect = [img1, img2]

        # First call should capture
        result1 = sc.capture_region(10, 20, 50, 50, use_cache=True)
        # Second call should return cached
        result2 = sc.capture_region(10, 20, 50, 50, use_cache=True)

        # Should return same object (cache hit)
        assert result1 is result2
        # Should only call screenshot once (cached second time)
        assert mock_pyautogui.screenshot.call_count == 1

    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot._IN_TEST_MODE", False)
    def test_cache_miss_different_regions(self, mock_pyautogui):
        """Should not cache hit for different regions."""
        img1 = Image.new("RGB", (50, 50), "red")
        img2 = Image.new("RGB", (50, 50), "blue")

        # Configure mock to return different images based on region parameter
        def mock_screenshot_func(region=None):
            if region and region[1] == 20:  # First call (y=20)
                return img1
            else:  # Second call (y=21)
                return img2

        mock_pyautogui.screenshot.side_effect = mock_screenshot_func

        # Capture different regions
        result1 = sc.capture_region(10, 20, 50, 50, use_cache=True)
        result2 = sc.capture_region(10, 21, 50, 50, use_cache=True)  # Different y

        # Should return different objects (different cache keys)
        assert result1 is not result2

    @patch("core.screenshot.pyautogui")
    @patch("core.screenshot._HAS_MSS", False)
    @patch("core.screenshot._IN_TEST_MODE", False)
    def test_cache_disabled_in_test_mode_region(self, mock_pyautogui):
        """Should bypass cache when in test mode for region capture."""
        img1 = Image.new("RGB", (50, 50), "red")
        img2 = Image.new("RGB", (50, 50), "blue")
        mock_pyautogui.screenshot.side_effect = [img1, img2]

        # Enable test mode
        sc._IN_TEST_MODE = True

        # Both calls should capture (no cache)
        result1 = sc.capture_region(10, 20, 50, 50, use_cache=True)
        result2 = sc.capture_region(10, 20, 50, 50, use_cache=True)

        # Should return different objects (no cache)
        assert result1 is not result2
        # Should call screenshot twice
        assert mock_pyautogui.screenshot.call_count == 2
