"""vector_search module."""
from __future__ import annotations

import threading
import time
import typing
from datetime import UTC, datetime

import cv2
import numpy as np

if typing.TYPE_CHECKING:
    from src.core.camera_capture import CameraCapture


class VectorSearch:
    def __init__(self, camera: CameraCapture, interval: float = 10.0) -> None:
        self.camera = camera
        self.interval = interval
        self.collection: typing.Any = None
        self._encoder: typing.Any = None
        self._model_name: str | None = None
        self.ready: bool = False
        self.error: str = ""
        self._running: bool = False
        self._lock = threading.Lock()
        self._index_count: int = 0
        self._ready_chroma: bool = False
        self._chroma: typing.Any = None
        try:
            import chromadb

            self._chroma = chromadb.Client(
                chromadb.Settings(
                    anonymized_telemetry=False, is_persistent=True, persist_directory="./chroma_db"
                )
            )
            self.collection = self._chroma.get_or_create_collection("frames")
            self._ready_chroma = True
        except Exception as e:
            self._ready_chroma = False
            self.error = f"ChromaDB init failed: {e}"

    def _load_encoder(self) -> bool:
        if self._encoder is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer

            self._model_name = "clip-ViT-B-32"
            self._encoder = SentenceTransformer(self._model_name)
            self.ready = True
            return True
        except Exception as e:
            self.error = f"CLIP load failed: {e}"
            return False

    def _encode_image(self, frame_bytes: bytes) -> list[float] | None:
        if not self._load_encoder():
            return None
        try:
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            emb = self._encoder.encode(rgb)
            return emb.tolist()
        except Exception:
            return None

    def _encode_text(self, text: str) -> list[float] | None:
        if not self._load_encoder():
            return None
        try:
            emb = self._encoder.encode(text)
            return emb.tolist()
        except Exception:
            return None

    def start(self) -> None:
        if not self._ready_chroma:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        last_id: int = -1
        self._last_index_time: float = 0.0
        self._index_errors: int = 0
        while self._running:
            fid = self.camera.frame_id
            raw = self.camera.latest_frame
            if raw is not None and fid != last_id:
                last_id = fid
                emb = self._encode_image(raw)
                if emb is not None:
                    ts = datetime.now(UTC).isoformat()
                    try:
                        self.collection.add(
                            embeddings=[emb],
                            ids=[f"fid_{fid}"],
                            metadatas=[{"frame_id": fid, "timestamp": ts}],
                        )
                        with self._lock:
                            self._index_count += 1
                            self._last_index_time = time.time()
                    except Exception:
                        self._index_errors += 1
            time.sleep(self.interval)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, object]]:
        if not self.ready or not self._ready_chroma:
            return []
        text_emb = self._encode_text(query)
        if text_emb is None:
            return []
        try:
            results = self.collection.query(
                query_embeddings=[text_emb],
                n_results=min(top_k, self._index_count or 1),
            )
            hits: list[dict[str, object]] = []
            if results.get("ids") and results["ids"][0]:
                for i, fid in enumerate(results["ids"][0]):
                    meta = (
                        (results.get("metadatas") or [{}])[0].get(i, {})
                        if isinstance(results.get("metadatas"), list)
                        else {}
                    )
                    dist = (
                        (results.get("distances") or [[]])[0][i] if results.get("distances") else 0
                    )
                    hits.append(
                        {
                            "frame_id": meta.get("frame_id", fid),
                            "timestamp": meta.get("timestamp", ""),
                            "score": round(1.0 - float(dist), 4),
                        }
                    )
            return hits
        except Exception:
            return []

    @property
    def info(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "chroma_ok": self._ready_chroma,
            "index_count": self._index_count,
            "last_index_time": round(getattr(self, "_last_index_time", 0), 1),
            "index_errors": getattr(self, "_index_errors", 0),
            "error": self.error,
        }
