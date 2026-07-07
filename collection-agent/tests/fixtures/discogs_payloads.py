"""Recorded-shape Discogs payloads (docs/discogs_api_reference.md shapes).

Kept as Python builders rather than raw JSON files so tests can vary ids/
fields without duplicating whole documents; the *shapes* mirror the real
API responses exactly (pagination envelope, basic_information, community
block, videos, collection value strings).
"""

from __future__ import annotations

from typing import Any


def identity(username: str = "test_user") -> dict[str, Any]:
    return {"id": 1, "username": username, "resource_url": f"https://api.discogs.com/users/{username}"}


def folders() -> list[dict[str, Any]]:
    return [
        {"id": 0, "name": "All", "count": 5},
        {"id": 1, "name": "Uncategorized", "count": 3},
        {"id": 3, "name": "Techno", "count": 2},
    ]


def collection_value() -> dict[str, Any]:
    return {"minimum": "US$100.00", "median": "US$250.00", "maximum": "US$400.00"}


def instance(
    instance_id: int,
    release_id: int,
    title: str,
    artist: str,
    year: int = 1995,
    folder_id: int = 1,
    rating: int = 0,
    genres: list[str] | None = None,
    styles: list[str] | None = None,
    label: str = "Test Label",
) -> dict[str, Any]:
    return {
        "instance_id": instance_id,
        "id": release_id,
        "folder_id": folder_id,
        "rating": rating,
        "date_added": "2024-01-15T10:00:00-08:00",
        "basic_information": {
            "id": release_id,
            "title": title,
            "year": year,
            "artists": [{"name": artist, "id": release_id * 10}],
            "labels": [{"name": label, "catno": f"TL-{release_id}"}],
            "formats": [{"name": "Vinyl", "qty": "1", "descriptions": ['12"', "33 ⅓ RPM"]}],
            "genres": genres or ["Electronic"],
            "styles": styles or ["Techno"],
        },
    }


def collection_page(
    items: list[dict[str, Any]], page: int, pages: int, per_page: int = 100
) -> dict[str, Any]:
    return {
        "pagination": {
            "page": page,
            "pages": pages,
            "per_page": per_page,
            "items": sum(1 for _ in items),
            "urls": {},
        },
        "releases": items,
    }


def release_detail(
    release_id: int,
    country: str | None = "Germany",
    have: int | None = 120,
    want: int | None = 300,
    rating_avg: float | None = 4.3,
    rating_count: int | None = 57,
    num_for_sale: int | None = 4,
    lowest_price: float | None = 12.5,
    videos: list[dict[str, Any]] | None = None,
    genres: list[str] | None = None,
    styles: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": release_id,
        "title": f"Release {release_id}",
        "country": country,
        "genres": genres or ["Electronic"],
        "styles": styles or ["Techno"],
        "community": {
            "have": have,
            "want": want,
            "rating": {"average": rating_avg, "count": rating_count},
        },
        "num_for_sale": num_for_sale,
        "lowest_price": lowest_price,
        "videos": videos
        if videos is not None
        else [
            {
                "uri": f"https://www.youtube.com/watch?v=vid{release_id}",
                "title": f"Video for {release_id}",
                "duration": 360,
                "embed": True,
            }
        ],
    }


def search_result(
    release_id: int,
    title: str = "Test Artist - Test Record",
    year: str | None = "1995",
    country: str | None = "Germany",
    formats: list[str] | None = None,
    labels: list[str] | None = None,
    catno: str | None = "TL-001",
    thumb: str | None = None,
    cover_image: str | None = None,
    uri: str | None = None,
    omit: set[str] | None = None,
) -> dict[str, Any]:
    """One /database/search result item (022). `omit` drops keys entirely
    so absent-field handling can be exercised (verbatim rule: absent stays
    absent)."""
    item: dict[str, Any] = {
        "id": release_id,
        "type": "release",
        "title": title,
        "year": year,
        "country": country,
        "format": formats if formats is not None else ["Vinyl", "LP"],
        "label": labels if labels is not None else ["Test Label"],
        "catno": catno,
        "thumb": thumb
        if thumb is not None
        else f"https://i.discogs.com/thumb-{release_id}.jpg",
        "cover_image": cover_image
        if cover_image is not None
        else f"https://i.discogs.com/cover-{release_id}.jpg",
        "uri": uri if uri is not None else f"/release/{release_id}",
        "resource_url": f"https://api.discogs.com/releases/{release_id}",
    }
    for key in omit or set():
        item.pop(key, None)
    return item


def search_page(
    results: list[dict[str, Any]],
    items: int | None = None,
    page: int = 1,
    per_page: int = 8,
) -> dict[str, Any]:
    """/database/search envelope; `items` defaults to len(results) but can
    be larger to exercise the more_matches flag."""
    return {
        "pagination": {
            "page": page,
            "pages": 1,
            "per_page": per_page,
            "items": items if items is not None else len(results),
            "urls": {},
        },
        "results": results,
    }


def add_instance_response(
    instance_id: int, release_id: int, folder_id: int = 1
) -> dict[str, Any]:
    """POST /users/{u}/collection/folders/{f}/releases/{r} response (022)."""
    return {
        "instance_id": instance_id,
        "resource_url": (
            f"https://api.discogs.com/users/test_user/collection/folders/"
            f"{folder_id}/releases/{release_id}/instances/{instance_id}"
        ),
    }


def default_collection() -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """5 instances over 4 unique releases (one duplicate copy), 2 pages."""
    instances = [
        instance(9001, 101, "Simple Things", "Alex Smoke", year=2005, folder_id=3,
                 rating=4, genres=["Electronic"], styles=["Minimal"]),
        instance(9002, 102, "Navigation EP", "Noah Pred", year=2011, folder_id=3),
        instance(9003, 103, "Blue Album", "Jazz Cat", year=1974, folder_id=1,
                 genres=["Jazz"], styles=["Hard Bop"], label="Blue Note"),
        instance(9004, 101, "Simple Things", "Alex Smoke", year=2005, folder_id=1,
                 genres=["Electronic"], styles=["Minimal"]),  # duplicate copy
        instance(9005, 104, "No Video Record", "Quiet Artist", year=0, folder_id=1),
    ]
    details = {
        101: release_detail(101, country="UK", have=500, want=80, num_for_sale=25,
                            lowest_price=8.0),
        102: release_detail(102, country="Canada", have=40, want=200, num_for_sale=0,
                            lowest_price=None, rating_avg=4.8, rating_count=12),
        103: release_detail(103, country="US", have=2000, want=5000, num_for_sale=1,
                            lowest_price=150.0, rating_avg=4.9, rating_count=800,
                            genres=["Jazz"], styles=["Hard Bop"]),
        104: release_detail(104, country=None, have=None, want=None, rating_avg=None,
                            rating_count=None, num_for_sale=None, lowest_price=None,
                            videos=[]),
    }
    return instances, details
