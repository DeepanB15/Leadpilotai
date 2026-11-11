import pytest

from app.utils.urls import InvalidURL, classify_social_url, normalize_website, validate_social_field


def test_normalize_adds_scheme_and_domain():
    s = normalize_website("Acme.com")
    assert s.url == "https://acme.com" and s.domain == "acme.com"


def test_normalize_strips_www_for_domain_but_keeps_host():
    s = normalize_website("https://www.Acme.com/about/?x=1#frag")
    assert s.domain == "acme.com" and s.host == "www.acme.com"
    assert s.url == "https://www.acme.com/about"


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "ftp://acme.com", "localhost", "http://127.0.0.1", "http://10.0.0.1/x", "acme", "https://user:pw@acme.com",
     "http://acme.com:8080", "foo.local", "http://[::1]/", "javascript:alert(1)", "a b.com"],
)
def test_normalize_rejects(bad):
    with pytest.raises(InvalidURL):
        normalize_website(bad)


def test_duplicate_domains_collapse():
    assert normalize_website("http://www.acme.com").domain == normalize_website("ACME.com/").domain


@pytest.mark.parametrize(
    "url,expected",
    [
        ("linkedin.com/company/acme", ("linkedin", "https://www.linkedin.com/company/acme")),
        ("https://www.linkedin.com/company/acme/about/", ("linkedin", "https://www.linkedin.com/company/acme")),
        ("https://instagram.com/acme?hl=en", ("instagram", "https://www.instagram.com/acme")),
        ("https://www.youtube.com/@acme", ("youtube", "https://www.youtube.com/@acme")),
        ("https://youtube.com/channel/UC123", ("youtube", "https://www.youtube.com/channel/UC123")),
        ("https://twitter.com/acme", ("x", "https://x.com/acme")),
        ("https://facebook.com/acme", ("facebook", "https://www.facebook.com/acme")),
    ],
)
def test_classify_social(url, expected):
    assert classify_social_url(url) == expected


@pytest.mark.parametrize(
    "url",
    ["https://www.linkedin.com/in/someone", "https://twitter.com/intent/tweet", "https://facebook.com/sharer/sharer.php",
     "https://instagram.com/p/abc", "https://youtube.com/watch?v=1", "https://example.com/acme", "not a url"],
)
def test_classify_social_rejects_non_profiles(url):
    assert classify_social_url(url) is None


def test_validate_social_field_platform_mismatch():
    with pytest.raises(InvalidURL):
        validate_social_field("linkedin", "instagram.com/acme")
    assert validate_social_field("x", None) is None
