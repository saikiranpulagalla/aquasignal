from html.parser import HTMLParser

from fastapi.testclient import TestClient
from apps.api.main import app


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stylesheets = []
        self.inline_styles = []
        self.policies = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'style' or 'style' in attrs:
            self.inline_styles.append(tag)
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.stylesheets.append(attrs['href'])
        if tag == 'meta' and attrs.get('http-equiv', '').lower() == 'content-security-policy':
            self.policies.append(attrs['content'])


def test_page_stylesheet_is_served_and_allowed_by_every_csp():
    client = TestClient(app)
    page = client.get('/')
    assert page.status_code == 200
    parsed = PageAssets()
    parsed.feed(page.text)
    assert parsed.stylesheets == ['/app.css']
    assert not parsed.inline_styles
    for policy in [page.headers['content-security-policy'], *parsed.policies]:
        directives = {parts[0]: parts[1:] for clause in policy.split(';')
                      if (parts := clause.strip().split())}
        assert directives['style-src'] == ["'self'"]
    css = client.get(parsed.stylesheets[0])
    assert css.status_code == 200
    assert css.headers['content-type'].startswith('text/css')
    assert ':root{' in css.text and '.status.block' in css.text
    assert css.headers['x-content-type-options'] == 'nosniff'
