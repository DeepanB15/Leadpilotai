from app.research.website.extractor import extract_content
from app.research.website.parser import Link, classify_page, parse_page, select_pages

HTML = """
<html><head><title> Acme  Software </title>
<meta name="description" content="Project management for teams">
<script type="application/ld+json">{"@type":"Organization","sameAs":["https://www.linkedin.com/company/acme","https://example.org/x"]}</script>
</head><body>
<nav><a href="/about">About us</a><a href="/pricing">Pricing</a><a href="/products/tracker">Tracker</a></nav>
<a href="https://www.youtube.com/@acme">YT</a>
<a href="https://twitter.com/intent/tweet?x=1">share</a>
<a href="https://other.com/page">external</a>
<a href="mailto:a@b.com">mail</a><a href="/brochure.pdf">pdf</a><a href="#top">top</a>
<main><h1>Acme builds project software</h1><p>""" + ("We help teams ship work on time. " * 20) + """</p></main>
<footer>Copyright junk footer</footer>
<script>var secret = "do not extract";</script>
</body></html>
"""


def test_parse_page_extracts_meta_links_and_socials():
    p = parse_page(HTML, "https://acme.com/")
    assert p.title == "Acme Software"
    assert p.description == "Project management for teams"
    urls = {link.url for link in p.links}
    assert "https://acme.com/about" in urls and "https://acme.com/pricing" in urls
    assert not any("other.com" in u or u.endswith(".pdf") or "mailto" in u for u in urls)
    assert "https://www.youtube.com/@acme" in p.social_urls
    assert "https://www.linkedin.com/company/acme" in p.social_urls  # from JSON-LD sameAs
    assert not any("intent" in s for s in p.social_urls)


def test_classify_and_select_pages():
    assert classify_page("https://acme.com/about-us")[0] == "about_page"
    assert classify_page("https://acme.com/pricing")[0] == "pricing_page"
    assert classify_page("https://acme.com/random/deep/path/here/x")[1] == 99
    links = [Link(f"https://acme.com/blog/post-{i}", "") for i in range(5)] + [
        Link("https://acme.com/about", ""), Link("https://acme.com/products", ""), Link("https://acme.com/misc", "")
    ]
    chosen = select_pages(links, limit=10)
    types = [t for _, t in chosen]
    assert types[0] == "about_page" and "product_page" in types
    assert types.count("blog_post") == 2  # capped
    assert all(link.url != "https://acme.com/misc" for link, _ in chosen)
    assert len(select_pages(links, limit=2)) == 2


def test_extract_content_removes_boilerplate():
    ex = extract_content(HTML, "https://acme.com/")
    assert "Acme builds project software" in ex.text
    assert "do not extract" not in ex.text
    assert len(ex.text) > 200


def test_extract_content_fallback_for_sparse_markup():
    ex = extract_content("<html><body><div>Short but real text about our consulting services for banks.</div></body></html>", "https://a.com")
    assert "consulting services" in ex.text
