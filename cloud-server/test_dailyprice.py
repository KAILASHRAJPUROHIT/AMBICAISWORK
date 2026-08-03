"""Regression test for the /dailyprice gold-rate poster route.

Locked down 2026-08-03 after manual verification on print.aradhanajewellers.com.
If this test breaks after an app.py change, re-verify the live page before
merging — this route has no other coverage.
"""
import re

import app as a


def test_dailyprice_form_loads():
    client = a.app.test_client()
    resp = client.get("/dailyprice")
    assert resp.status_code == 200
    assert b"rate" in resp.data


def test_dailyprice_renders_poster_with_todays_date():
    client = a.app.test_client()
    resp = client.post("/dailyprice", data={"rate": "135000"})
    assert resp.status_code == 200
    match = re.search(rb'src="(/dailyprice/media/[^"]+)"', resp.data)
    assert match, "expected a rendered poster <img> in the response"

    media_resp = client.get(match.group(1).decode())
    assert media_resp.status_code == 200
    assert media_resp.content_type == "image/jpeg"


def test_dailyprice_rejects_invalid_rate():
    client = a.app.test_client()
    resp = client.post("/dailyprice", data={"rate": "not a number"})
    assert resp.status_code == 200
    assert b"Enter a valid rate" in resp.data
