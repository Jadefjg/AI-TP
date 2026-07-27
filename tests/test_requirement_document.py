"""Requirement document parsing."""

from backend.services.requirement_document import (
    _parse_feishu_doc_url,
    _parse_html,
    fetch_requirement_from_url,
    parse_requirement_document,
)


def test_parse_html_document():
    content = b"<html><body><h1>Login</h1><p>User must enter password with at least 8 chars.</p></body></html>"
    text, fmt = parse_requirement_document(filename="page.html", content=content)
    assert fmt == "html"
    assert "password" in text


def test_parse_plain_text():
    text, fmt = parse_requirement_document(filename="req.txt", content=b"hello world requirement spec")
    assert fmt == "txt"
    assert "requirement" in text


def test_parse_html_helper_strips_tags():
    text = _parse_html(b"<div>Alpha<br/>Beta</div>")
    assert "Alpha" in text and "Beta" in text


def test_parse_feishu_wiki_url():
    kind, token = _parse_feishu_doc_url(
        "https://tenhuijxo5s2.feishu.cn/wiki/TExHwEdyiIVFsekPuTqcqPc9ntb"
    )
    assert kind == "wiki"
    assert token == "TExHwEdyiIVFsekPuTqcqPc9ntb"


def test_feishu_login_wall_gives_actionable_error():
    html = b"""<!doctype html><html><head>
    <meta name="suite-passport-compile-at" content="x">
    </head><body>passport login</body></html>"""
    try:
        _parse_html(html, source_url="https://foo.feishu.cn/wiki/AbcDefGhijk")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "飞书" in str(exc)
        assert "FEISHU_APP_ID" in str(exc) or "上传" in str(exc)


def test_fetch_feishu_url_without_credentials_is_actionable(monkeypatch):
    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        content = (
            b'<!doctype html><html><head>'
            b'<meta name="suite-passport-compile-at" content="x">'
            b"</head><body></body></html>"
        )

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResp()

    monkeypatch.setattr("backend.services.requirement_document.httpx.Client", FakeClient)
    try:
        fetch_requirement_from_url("https://tenhuijxo5s2.feishu.cn/wiki/TExHwEdyiIVFsekPuTqcqPc9ntb")
        assert False, "expected ValueError"
    except ValueError as exc:
        msg = str(exc)
        assert "飞书" in msg
        assert "网页内容过短" not in msg
