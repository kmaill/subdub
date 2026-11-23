import unittest
from unittest.mock import patch, MagicMock
from subdub.core.probe import (
    check_audio_language,
    determine_audio_layout,
    probe_media,
    get_video_duration,
)
from subdub.core.languages import resolve_language

class TestProbe(unittest.TestCase):
    def test_check_polish_audio_detection(self):
        # Case 1: English only
        lang_spec = resolve_language("pol")
        eng_streams = [
            {"codec_type": "audio", "tags": {"language": "eng", "title": "Original English"}}
        ]
        self.assertFalse(check_audio_language(eng_streams, lang_spec))

        # Case 2: Language code 'pol'
        pol_streams = [
            {"codec_type": "audio", "tags": {"language": "pol", "title": "Stereo"}}
        ]
        self.assertTrue(check_audio_language(pol_streams, lang_spec))

        # Case 3: Title contains 'lektor'
        lektor_streams = [
            {"codec_type": "audio", "tags": {"language": "und", "title": "Polski Lektor AI"}}
        ]
        self.assertTrue(check_audio_language(lektor_streams, lang_spec))

        # Case 4: Title contains 'dubbing pl'
        dub_streams = [
            {"codec_type": "audio", "tags": {"language": "und", "title": "Dubbing PL 5.1"}}
        ]
        self.assertTrue(check_audio_language(dub_streams, lang_spec))

    def test_determine_audio_layout(self):
        # 6 channels on MKV -> 5.1
        audio_51 = [{"channels": 6}]
        layout_mkv = determine_audio_layout(audio_51, is_mp4=False)
        self.assertEqual(layout_mkv.layout, "5.1")
        self.assertEqual(layout_mkv.channels, 6)
        self.assertEqual(layout_mkv.bitrate, "448k")

        # 6 channels on MP4 -> Stereo
        layout_mp4 = determine_audio_layout(audio_51, is_mp4=True)
        self.assertEqual(layout_mp4.layout, "stereo")
        self.assertEqual(layout_mp4.channels, 2)
        self.assertEqual(layout_mp4.bitrate, "256k")

        # 2 channels on MKV -> Stereo
        audio_20 = [{"channels": 2}]
        layout_20 = determine_audio_layout(audio_20, is_mp4=False)
        self.assertEqual(layout_20.layout, "stereo")
        self.assertEqual(layout_20.channels, 2)

    def test_supported_extensions(self):
        from subdub.core.probe import SUPPORTED_VIDEO_EXTENSIONS, MP4_EXTENSIONS
        self.assertIn(".mkv", SUPPORTED_VIDEO_EXTENSIONS)
        self.assertIn(".mp4", SUPPORTED_VIDEO_EXTENSIONS)
        self.assertIn(".m4v", SUPPORTED_VIDEO_EXTENSIONS)
        self.assertIn(".mov", SUPPORTED_VIDEO_EXTENSIONS)
        self.assertIn(".mov", MP4_EXTENSIONS)

    @patch("subprocess.run")
    def test_get_video_duration(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="3600.50\n")
        duration = get_video_duration("movie.mkv")
        self.assertEqual(duration, 3600.5)

    @patch("subdub.core.probe.probe_streams")
    @patch("subdub.core.probe.get_video_duration")
    def test_probe_media(self, mock_duration, mock_streams):
        mock_duration.return_value = 120.0
        mock_streams.return_value = [
            {"codec_type": "video", "index": 0},
            {"codec_type": "audio", "index": 1, "channels": 6, "tags": {"language": "eng"}},
            {"codec_type": "subtitle", "index": 2, "codec_name": "subrip", "tags": {"language": "pol"}},
        ]

        info = probe_media("test_movie.mkv")
        self.assertEqual(info.duration, 120.0)
        self.assertFalse(info.has_target_audio)
        self.assertEqual(info.audio_layout.layout, "5.1")
        self.assertEqual(info.safe_sub_indices, [2])


if __name__ == "__main__":
    unittest.main()
