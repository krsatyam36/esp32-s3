"""Tests for VectorSearch CLIP+ChromaDB (mock chromadb)."""

from unittest.mock import patch, MagicMock


class TestVectorSearch:
    def test_initialization_chroma_fails_gracefully(self):
        with patch("chromadb.Client", side_effect=Exception("mock")):
            from src.ai.vector_search import VectorSearch
            camera = MagicMock()
            vs = VectorSearch(camera, interval=10.0)
            assert vs._ready_chroma is False

    def test_import_error_handled(self):
        import builtins
        orig_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "chromadb":
                raise ImportError("chromadb not available")
            return orig_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=mock_import):
            import sys
            for m in list(sys.modules.keys()):
                if "vector_search" in m or m == "chromadb":
                    del sys.modules[m]
            from src.ai.vector_search import VectorSearch
            camera = MagicMock()
            vs = VectorSearch(camera, interval=10.0)
            assert vs._ready_chroma is False

    def test_info_defaults(self):
        from src.ai.vector_search import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        info = vs.info
        assert "ready" in info
        assert "chroma_ok" in info
        assert "index_count" in info
        assert "error" in info

    def test_search_returns_empty_when_not_ready(self):
        with patch("chromadb.Client", side_effect=Exception("mock")):
            from src.ai.vector_search import VectorSearch
            camera = MagicMock()
            vs = VectorSearch(camera, interval=10.0)
            results = vs.search("person with laptop")
            assert results == []

    def test_search_returns_empty_when_no_encoder(self):
        from src.ai.vector_search import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        vs._ready_chroma = True
        results = vs.search("test query")
        assert results == []

    def test_start_does_nothing_when_chroma_unavailable(self):
        with patch("chromadb.Client", side_effect=Exception("mock")):
            from src.ai.vector_search import VectorSearch
            camera = MagicMock()
            vs = VectorSearch(camera, interval=10.0)
            vs.start()
            assert not vs._running

    def test_stop_toggles_running(self):
        from src.ai.vector_search import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        vs._running = True
        vs.stop()
        assert not vs._running

    def test_index_count_starts_zero(self):
        from src.ai.vector_search import VectorSearch
        camera = MagicMock()
        vs = VectorSearch(camera, interval=10.0)
        assert vs._index_count == 0
