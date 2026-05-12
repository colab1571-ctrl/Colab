"""
Tests: Profile bio ≤280 / obsessed ≤140 server-side enforcement.
Run: pytest tests/api/test_profile_validation.py -q
"""

import pytest
from pydantic import ValidationError

from app.schemas.profile import ProfilePatch


class TestBioLength:
    def test_bio_280_chars_accepted(self):
        p = ProfilePatch(bio="a" * 280)
        assert len(p.bio) == 280

    def test_bio_281_chars_rejected(self):
        with pytest.raises(ValidationError):
            ProfilePatch(bio="a" * 281)

    def test_bio_none_accepted(self):
        p = ProfilePatch(bio=None)
        assert p.bio is None


class TestObsessedLength:
    def test_obsessed_140_chars_accepted(self):
        p = ProfilePatch(obsessed_with="b" * 140)
        assert len(p.obsessed_with) == 140

    def test_obsessed_141_chars_rejected(self):
        with pytest.raises(ValidationError):
            ProfilePatch(obsessed_with="b" * 141)


class TestDisplayNameLength:
    def test_display_name_min_2(self):
        p = ProfilePatch(display_name="ab")
        assert p.display_name == "ab"

    def test_display_name_too_short(self):
        with pytest.raises(ValidationError):
            ProfilePatch(display_name="a")

    def test_display_name_max_40(self):
        p = ProfilePatch(display_name="a" * 40)
        assert len(p.display_name) == 40

    def test_display_name_too_long(self):
        with pytest.raises(ValidationError):
            ProfilePatch(display_name="a" * 41)
