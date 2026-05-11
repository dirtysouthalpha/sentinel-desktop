"""Smoke tests for the OCR and UIAutomation modules.

These don't require Tesseract or uiautomation to be installed — they verify
that the modules gracefully no-op when their backends are unavailable.
"""
import pytest

from core import ocr
from core import ui_tree


def test_ocr_find_text_no_tesseract_returns_none(monkeypatch):
    monkeypatch.setattr(ocr, "_have_tesseract", lambda: False)
    assert ocr.find_text("Hello") is None


def test_ocr_read_screen_text_no_tesseract_returns_empty(monkeypatch):
    monkeypatch.setattr(ocr, "_have_tesseract", lambda: False)
    assert ocr.read_screen_text() == ""


def test_ocr_find_text_empty_query():
    assert ocr.find_text("") is None
    assert ocr.find_text("   ") is None


def test_uia_list_controls_without_uia_is_empty(monkeypatch):
    monkeypatch.setattr(ui_tree, "_have_uia", lambda: False)
    assert ui_tree.list_controls() == []


def test_uia_click_control_without_uia_is_none(monkeypatch):
    monkeypatch.setattr(ui_tree, "_have_uia", lambda: False)
    assert ui_tree.click_control(name="Send") is None


def test_uia_set_text_without_uia_is_false(monkeypatch):
    monkeypatch.setattr(ui_tree, "_have_uia", lambda: False)
    assert ui_tree.set_text("hello", name="Subject") is False
