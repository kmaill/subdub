import unittest
from subdub.server import extract_media_path_from_payload


class TestServer(unittest.TestCase):
    def test_extract_media_path_direct(self):
        payload = {"episode": "/media/tv/series/S01E01.mkv", "subtitles": "/media/tv/series/S01E01.pl.srt"}
        video, subs = extract_media_path_from_payload(payload)
        self.assertEqual(video, "/media/tv/series/S01E01.mkv")
        self.assertEqual(subs, "/media/tv/series/S01E01.pl.srt")

        # Bazarr movie payload
        movie_payload = {"movie": "/data/media/movies/Avatar/Avatar.mkv", "subtitles": "/data/media/movies/Avatar/Avatar.pl.srt"}
        video_m, subs_m = extract_media_path_from_payload(movie_payload)
        self.assertEqual(video_m, "/data/media/movies/Avatar/Avatar.mkv")
        self.assertEqual(subs_m, "/data/media/movies/Avatar/Avatar.pl.srt")

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

    def test_extract_media_path_radarr(self):
        payload = {
            "eventType": "Download",
            "movieFile": {"path": "/movies/Movie (2010)/Movie.mkv"}
        }
        video, _ = extract_media_path_from_payload(payload)
        self.assertEqual(video, "/movies/Movie (2010)/Movie.mkv")

    def test_extract_media_path_sonarr_v4(self):
        payload = {
            "eventType": "Download",
            "series": {"path": "/tv/Show"},
            "episodeFiles": [{"path": "/tv/Show/Season 01/S01E01.mkv"}]
        }
        video, _ = extract_media_path_from_payload(payload)
        self.assertEqual(video, "/tv/Show/Season 01/S01E01.mkv")

    def test_test_event_payload(self):
        payload = {"eventType": "Test", "instanceName": "Radarr"} 
        video, _ = extract_media_path_from_payload(payload) 
        self.assertIsNone(video)


if __name__ == "__main__":
    unittest.main()
