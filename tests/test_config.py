from pathlib import Path
import os
import tempfile
from subdub.config import Config, load_config, init_default_config_if_missing


def test_default_config():
    cfg = Config()
    assert cfg.voice == "pl-PL-MarekNeural"
    assert cfg.lang == "pol"
    assert cfg.batch_seconds == 900.0
    assert cfg.max_tts_concurrency == 4
    assert cfg.bitrate_51 == "448k"
    assert cfg.bitrate_stereo == "256k"
    assert "/media/movies" in cfg.scan_dirs
    assert ".cache/subdub" in cfg.temp_dir or "subdub" in cfg.temp_dir
    assert cfg.temp_dir != "/tmp/subdub"
    assert cfg.server_port == 9999


def test_init_default_config(tmp_path: Path):
    custom_path = tmp_path / "subdub" / "config.toml"
    assert not custom_path.exists()
    
    init_default_config_if_missing(custom_path)
    assert custom_path.exists()
    
    content = custom_path.read_text(encoding="utf-8")
    assert "pl-PL-MarekNeural" in content
    assert "batch_seconds" in content


def test_load_config_with_overrides(tmp_path: Path):
    custom_path = tmp_path / "config.toml"
    custom_path.write_text("""
[tts]
voice = "pl-PL-AgnieszkaNeural"
lang = "pol"

[audio]
batch_seconds = 600.0

[storage]
scan_dirs = ["/test/movies"]
""", encoding="utf-8")

    cfg = load_config(custom_path)
    assert cfg.voice == "pl-PL-AgnieszkaNeural"
    assert cfg.batch_seconds == 600.0
    assert cfg.scan_dirs == ["/test/movies"]

    # Test CLI overrides (Tier 3)
    cfg_override = load_config(custom_path, voice="pl-PL-MarekNeural", force=True)
    assert cfg_override.voice == "pl-PL-MarekNeural"
    assert cfg_override.force is True
