# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for nextcloud.docgen — the minimal .odt builder
(FEATURE-NEXTCLOUD-BACKEND.md §8, Byggordning steg 7)."""

from __future__ import annotations

import zipfile
from io import BytesIO

import defusedxml.ElementTree as ET

from memaix_gateway.nextcloud.docgen import pm_report_sections, render_odt


def _unzip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(BytesIO(data))


def test_render_odt_produces_a_valid_zip_with_required_entries():
    data = render_odt("Title", [{"heading": "H", "paragraphs": ["p1", "p2"]}])
    zf = _unzip(data)
    assert zf.namelist() == ["mimetype", "META-INF/manifest.xml", "content.xml"]


def test_mimetype_entry_is_first_and_uncompressed():
    data = render_odt("Title", [])
    zf = _unzip(data)
    info = zf.infolist()[0]
    assert info.filename == "mimetype"
    assert info.compress_type == zipfile.ZIP_STORED
    assert zf.read("mimetype") == b"application/vnd.oasis.opendocument.text"


def test_content_xml_and_manifest_are_well_formed_xml():
    data = render_odt("Title", [{"heading": "H", "paragraphs": ["p1"]}])
    zf = _unzip(data)
    ET.fromstring(zf.read("content.xml"))  # raises on malformed XML
    ET.fromstring(zf.read("META-INF/manifest.xml"))


def test_content_includes_title_heading_and_paragraphs():
    data = render_odt("My Report", [{"heading": "Section", "paragraphs": ["First", "Second"]}])
    content = _unzip(data).read("content.xml").decode()
    assert "My Report" in content
    assert "Section" in content
    assert "First" in content and "Second" in content


def test_special_characters_are_xml_escaped():
    data = render_odt("A & B <script>", [{"heading": "H", "paragraphs": ["<tag>"]}])
    zf = _unzip(data)
    # Would raise if the raw & or < broke XML well-formedness.
    root = ET.fromstring(zf.read("content.xml"))
    text = "".join(root.itertext())
    assert "A & B <script>" in text
    assert "<tag>" in text


def test_section_without_heading_still_renders_paragraphs():
    data = render_odt("Title", [{"paragraphs": ["orphan paragraph"]}])
    content = _unzip(data).read("content.xml").decode()
    assert "orphan paragraph" in content


def test_empty_sections_produce_just_the_title():
    data = render_odt("Solo Title", [])
    content = _unzip(data).read("content.xml").decode()
    assert "Solo Title" in content


# ------------------------------------------------------------------
# pm_report_sections
# ------------------------------------------------------------------


def test_pm_report_sections_milestones():
    report = {"milestones": [{"name": "Beta", "target_date": "2025-01-01", "overdue": True}]}
    sections = pm_report_sections(report)
    assert sections[0]["heading"] == "Milestones"
    assert "OVERDUE" in sections[0]["paragraphs"][0]


def test_pm_report_sections_variance_without_baseline():
    report = {"variance": {"ok": False, "error": "no baseline scenario yet"}}
    sections = pm_report_sections(report)
    assert sections[0]["heading"] == "Variance"
    assert "no baseline" in sections[0]["paragraphs"][0]


def test_pm_report_sections_variance_with_tasks():
    report = {"variance": {"ok": True, "tasks": [
        {"title": "Task A", "percent_complete": 50.0, "hours_logged": 4.0, "estimate_hours": 8.0, "slippage_days": 3},
    ]}}
    sections = pm_report_sections(report)
    assert "Task A" in sections[0]["paragraphs"][0]
    assert "3 day(s) behind" in sections[0]["paragraphs"][0]


def test_pm_report_sections_raid_empty():
    report = {"raid": {"entries": [], "count": 0}}
    sections = pm_report_sections(report)
    assert sections[0]["heading"] == "RAID"
    assert sections[0]["paragraphs"] == ["No open RAID entries."]


def test_pm_report_sections_utilization():
    report = {"utilization": {
        "period_start": "2025-01-06", "period_end": "2025-01-07",
        "resources": [{"name": "Anna", "utilization_pct": 100.0, "allocated_hours": 16.0, "capacity_hours": 16.0}],
    }}
    sections = pm_report_sections(report)
    assert "2025-01-06" in sections[0]["heading"]
    assert "Anna" in sections[0]["paragraphs"][0]


def test_pm_report_sections_status_bundles_all_present_keys():
    report = {
        "milestones": [], "variance": {"ok": False, "error": "x"}, "raid": {"entries": [], "count": 0},
    }
    sections = pm_report_sections(report)
    headings = [s["heading"] for s in sections]
    assert headings == ["Milestones", "Variance", "RAID"]
