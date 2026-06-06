"""Tests for VectorSearch CLIP+ChromaDB (mock chromadb)."""

from unittest.mock import patch, MagicMock


class TestVectorSearch:
    def test_initialization_chroma_fails_gracefully(self):
        from src.app import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        assert vs._ready_chroma is False

    def test_import_error_handled(self):
        import sys
        had_chromadb = "chromadb" in sys.modules
        if had_chromadb:
            chromadb_mod = sys.modules.pop("chromadb")
        try:
            from src.app import VectorSearch
            camera = MagicMock()
            vs = VectorSearch(camera, interval=10.0)
            assert vs._ready_chroma is False
        finally:
            if had_chromadb:
                sys.modules["chromadb"] = chromadb_mod

    def test_info_defaults(self):
        from src.app import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        info = vs.info
        assert "ready" in info
        assert "chroma_ok" in info
        assert "index_count" in info
        assert "error" in info

    def test_search_returns_empty_when_not_ready(self):
        from src.app import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        results = vs.search("person with laptop")
        assert results == []

    def test_search_returns_empty_when_no_encoder(self):
        from src.app import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        vs._ready_chroma = True
        results = vs.search("test query")
        assert results == []

    def test_start_does_nothing_when_chroma_unavailable(self):
        from src.app import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        vs.start()
        assert not vs._running

    def test_stop_toggles_running(self):
        from src.app import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        vs._running = True
        vs.stop()
        assert not vs._running

    def test_index_count_starts_zero(self):
        from src.app import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        assert vs._index_count == 0
