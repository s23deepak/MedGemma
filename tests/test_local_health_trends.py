import os

from src.trends.local_health_trends import LocalHealthTrendsService
import xml.etree.ElementTree as ET


os.environ["DISABLE_EXTERNAL_MEDICAL_VOCAB"] = "1"


def test_correlate_matches_respiratory_trend_signals():
    service = LocalHealthTrendsService()

    service._fetch_signals = lambda location, max_items=12: [
        {
            "title": "Wildfire smoke degrades air quality across Florida",
            "source": "Local News",
            "published": "Tue, 24 Feb 2026 12:00:00 GMT",
            "link": "https://example.org/wildfire",
            "categories": ["respiratory_irritant"],
        },
        {
            "title": "Hospital updates visiting policy",
            "source": "Local News",
            "published": "Tue, 24 Feb 2026 12:00:00 GMT",
            "link": "https://example.org/hospital",
            "categories": [],
        },
    ]

    result = service.correlate(
        location="Florida",
        symptoms=["cough", "shortness of breath"],
        force_refresh=True,
    )

    assert result["matched_signal_count"] == 1
    assert result["matched_signals"][0]["matched_categories"] == ["respiratory_irritant"]
    assert result["recommendation"] is not None


def test_correlate_returns_no_matches_for_unrelated_symptoms():
    service = LocalHealthTrendsService()

    service._fetch_signals = lambda location, max_items=12: [
        {
            "title": "Wildfire smoke degrades air quality across Florida",
            "source": "Local News",
            "published": "Tue, 24 Feb 2026 12:00:00 GMT",
            "link": "https://example.org/wildfire",
            "categories": ["respiratory_irritant"],
        }
    ]

    result = service.correlate(
        location="Florida",
        symptoms=["knee pain"],
        force_refresh=True,
    )

    assert result["matched_signal_count"] == 0
    assert result["matched_signals"] == []
    assert result["recommendation"] is None


def test_fetch_signals_filters_non_local_articles():
    service = LocalHealthTrendsService()

    local_item = ET.fromstring(
        """
        <item>
            <title>Florida issues air quality advisory after wildfire smoke</title>
            <source>State Health Desk</source>
            <pubDate>Tue, 24 Feb 2026 12:00:00 GMT</pubDate>
            <link>https://example.org/florida-smoke</link>
            <description>Respiratory patients in Florida are advised to limit outdoor exposure.</description>
        </item>
        """
    )
    non_local_item = ET.fromstring(
        """
        <item>
            <title>Oregon smoke event update</title>
            <source>Regional News</source>
            <pubDate>Tue, 24 Feb 2026 13:00:00 GMT</pubDate>
            <link>https://example.org/oregon-smoke</link>
            <description>Air quality worsens in Portland metro area.</description>
        </item>
        """
    )

    service._fetch_rss_items = lambda query: [local_item, non_local_item]
    signals = service._fetch_signals("Florida", max_items=10)

    assert len(signals) == 1
    assert "Florida" in signals[0]["title"]
