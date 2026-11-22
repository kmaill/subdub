import unittest
from subdub.server import extract_media_path_from_payload


class TestServer(unittest.TestCase):
    def test_extract_media_path_direct(self):
        payload = {"episode": "/media/tv/series/S01E01.mkv", "subtitles": "/media/tv/series/S01E01.pl.srt"}
        video, subs = extract_media_path_from_payload(payload)
        self.assertEqual(video, "/media/tv/series/S01E01.mkv")
        self.assertEqual(subs, "/media/tv/series/S01E01.pl.srt")

    def test_extract_media_path_generic(self):
        payload = {"path": "/movies/Test (2024)/Test.mp4"}
        video, subs = extract_media_path_from_payload(payload)
        self.assertEqual(video, "/movies/Test (2024)/Test.mp4")
        self.assertIsNone(subs)

    def test_extract_media_path_apprise_json_message(self):
        payload = {"message": '{"video_path": "/data/movie.mkv", "subs_path": "/data/movie.srt"}'}
        video, subs = extract_media_path_from_payload(payload)
        self.assertEqual(video, "/data/movie.mkv")
        self.assertEqual(subs, "/data/movie.srt")


if __name__ == "__main__":
    unittest.main()
