import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from subdub.core.subtitles import (
    srt_time_to_seconds,
    clean_text,
    parse_srt,
    find_or_extract_srt,
)


class TestSubtitles(unittest.TestCase):
    def test_srt_time_to_seconds(self):
        self.assertAlmostEqual(srt_time_to_seconds("00:01:30,500"), 90.5)
        self.assertAlmostEqual(srt_time_to_seconds("01:00:00.000"), 3600.0)
        self.assertAlmostEqual(srt_time_to_seconds("00:00:05,25"), 5.25)

    def test_clean_text(self):
        # HTML tags
        self.assertEqual(clean_text("<i>Cześć</i> <b>Jan!</b>"), "Cześć Jan!")
        # ASS tags
        self.assertEqual(clean_text("{\\an8}Napis na górze"), "Napis na górze")
        # SDH bracketed / parenthesized sounds
        self.assertEqual(
            clean_text("[muzyka w tle] Dzień dobry! (śmiech)", strip_sdh=True),
            "Dzień dobry!",
        )
        # Preserve SDH when strip_sdh=False
        self.assertEqual(
            clean_text("[muzyka w tle] Dzień dobry! (śmiech)", strip_sdh=False),
            "[muzyka w tle] Dzień dobry! (śmiech)",
        )
        # Speaker prefix
        self.assertEqual(clean_text("TOMASZ: Gdzie idziesz?"), "Gdzie idziesz?")
        # Leading dash
        self.assertEqual(clean_text("- Nie wiem."), "Nie wiem.")
        # Leading quotes
        self.assertEqual(clean_text("„Dokąd zmierzasz?”"), "Dokąd zmierzasz?”")

    def test_parse_srt(self):
        sample_srt = """1
00:00:01,000 --> 00:00:03,000
<i>Dzień dobry</i> wszystkim.

2
00:00:05,500 --> 00:00:08,000
[Muzyka]
ANNA: Jak się masz?
"""
        with Path("/tmp/test_sample.srt").open("w", encoding="utf-8") as f:
            f.write(sample_srt)

        try:
            cues = parse_srt("/tmp/test_sample.srt")
            self.assertEqual(len(cues), 2)
            self.assertEqual(cues[0]["start"], 1.0)
            self.assertEqual(cues[0]["end"], 3.0)
            self.assertEqual(cues[0]["text"], "Dzień dobry wszystkim.")

            self.assertEqual(cues[1]["start"], 5.5)
            self.assertEqual(cues[1]["end"], 8.0)
            self.assertEqual(cues[1]["text"], "Jak się masz?")
        finally:
            Path("/tmp/test_sample.srt").unlink(missing_ok=True)

    def test_find_or_extract_srt_explicit(self):
        sample_file = Path("/tmp/explicit_subs.srt")
        sample_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nTest\n", encoding="utf-8")
        try:
            res = find_or_extract_srt(
                video_path="/media/movie.mkv",
                streams=[],
                temp_dir="/tmp",
                explicit_subs=str(sample_file),
            )
            self.assertEqual(res, str(sample_file.resolve()))
        finally:
            sample_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
