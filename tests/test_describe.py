from omaforge.core.describe import clean_html, clean_markdown, describe, markdown_images


def test_html_keeps_text_and_safe_tags_only():
    out = clean_html('<p style="x"><img src="https://a/b.png"></p><h1>Title</h1><p>Hi <b>there<i>you</b> '
                     '<span onclick="x">now</span></p><script>alert(1)</script><iframe src="y">z</iframe>')
    assert out == "<h3>Title</h3><p>Hi <b>there<i>you</i></b> now</p>"


def test_html_links_are_absolute_http_and_linkouts_unwrapped():
    out = clean_html('<a href="/linkout?remoteUrl=https%253a%252f%252fexample.com%252fx">ex</a>'
                     '<a href="/wow/addons/y">rel</a> <a href="javascript:alert(1)">js</a> <a href="https://ok/?a=1&b=2">ok</a>')
    assert out == ('<a href="https://example.com/x">ex</a>rel js <a href="https://ok/?a=1&amp;b=2">ok</a>')


def test_html_escapes_text():
    assert clean_html("<p>a &lt;b&gt; &amp; c</p>") == "<p>a &lt;b&gt; &amp; c</p>"


def test_bbcode():
    fmt, out = describe("Hello [b]bold[/b] <x>\r\n[url=https://e.com]site[/url] [img]https://i/x.png[/img]"
                        "[color=red]red[/color]\n[list][*]one\n[*]two\n[/list][list=1][*]a[/list]", "bbcode")
    assert fmt == "html"
    assert out == ('Hello <b>bold</b> &lt;x&gt;<br><a href="https://e.com">site</a> red'
                   "<ul><li>one</li><li>two</li></ul><ol><li>a</li></ol>")


def test_plain_text_keeps_line_breaks_and_markdown_is_detected():
    assert describe("one\ntwo", "bbcode") == ("html", "one<br>two")
    assert describe("# Title\n\n* item", "bbcode") == ("markdown", "# Title\n\n* item")
    assert describe("", "html") == ("html", "")


def test_markdown_drops_images_and_html():
    md = ("[![Build](https://shields.io/x.svg)](https://ci) ![shot](shot.png)\n<p align=center><img src=\"logo.png\"></p>\n"
          "# Name\n\n```sh\n# comment\n```\n<script>x</script>text")
    assert clean_markdown(md) == "<p align=center></p>\n# Name\n\n```sh\n# comment\n```\ntext"


def test_markdown_images_resolve_and_skip_badges():
    md = ('![b](https://img.shields.io/x) ![a](docs/a.png) <img src="https://x/y.jpg" width=3> '
          '![c](https://x/logo.svg) ![again](docs/a.png) [![donate](https://www.paypal.com/btn.gif)](x)')
    assert markdown_images(md, "https://raw.githubusercontent.com/o/r/main/README.md") == [
        "https://raw.githubusercontent.com/o/r/main/docs/a.png", "https://x/y.jpg"]
