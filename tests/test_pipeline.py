import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from subdub.config import Config
from subdub.core.pipeline import process_video


class TestPipeline(unittest.TestCase):
    @patch("subdub.core.pipeline.probe_media")
    def test_skip_when_polish_audio_present(self, mock_probe):
        mock_info = MagicMock()
        mock_info.has_target_audio = True
        mock_probe.return_value = mock_info

        dummy_file = Path("/tmp/dummy_movie.mkv")
        dummy_file.touch()
        try:
            cfg = Config(force=False)
            res = process_video(dummy_file, cfg)
            self.assertTrue(res)
        finally:
            dummy_file.unlink(missing_ok=True)

    @patch("subdub.core.pipeline.probe_media")
    @patch("subdub.core.pipeline.find_or_extract_srt")
    def test_skip_when_no_subtitles(self, mock_find_subs, mock_probe):
        mock_info = MagicMock()
        mock_info.has_target_audio = False
        mock_info.streams = []
        mock_probe.return_value = mock_info
        mock_find_subs.return_value = None

        dummy_file = Path("/tmp/dummy_movie_no_sub.mkv")
        dummy_file.touch()
        try:
            cfg = Config()
            res = process_video(dummy_file, cfg)
            self.assertTrue(res)
        finally:
            dummy_file.unlink(missing_ok=True)

    @patch("subdub.core.pipeline.probe_media")
    @patch("subdub.core.pipeline.find_or_extract_srt")
    @patch("subdub.core.pipeline.parse_srt")
    def test_dry_run_mode(self, mock_parse, mock_find_subs, mock_probe):
        mock_info = MagicMock()
        mock_info.has_target_audio = False
        mock_probe.return_value = mock_info
        mock_find_subs.return_value = "/tmp/sample.srt"
        mock_parse.return_value = [{"start": 1.0, "end": 2.0, "text": "Test"}]

        dummy_file = Path("/tmp/dummy_dryrun.mkv")
        dummy_file.touch()
        try:
            cfg = Config(dry_run=True)
            res = process_video(dummy_file, cfg)
            self.assertTrue(res)
        finally:
            dummy_file.unlink(missing_ok=True)

    @patch("subdub.core.pipeline.probe_media")
    @patch("subdub.core.pipeline.find_or_extract_srt")
    @patch("subdub.core.pipeline.parse_srt")
    def test_lock_skip_when_busy(self, mock_parse, mock_find_subs, mock_probe):
        import fcntl
        mock_info = MagicMock()
        mock_info.has_target_audio = False
        mock_probe.return_value = mock_info
        mock_find_subs.return_value = "/tmp/sample.srt"
        mock_parse.return_value = [{"start": 1.0, "end": 2.0, "text": "Test"}]

        dummy_file = Path("/tmp/dummy_lock.mkv")
        dummy_file.touch()
        lock_file = Path("/tmp/test_subdub.lock")
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Pre-lock file to simulate another active rendering job
        fp = open(lock_file, "w")
        fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            cfg = Config(lock_file=str(lock_file), dry_run=False)
            res = process_video(dummy_file, cfg, blocking_lock=False)
            self.assertFalse(res)
        finally:
            fcntl.flock(fp, fcntl.LOCK_UN)
            fp.close()
            lock_file.unlink(missing_ok=True)
            dummy_file.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
