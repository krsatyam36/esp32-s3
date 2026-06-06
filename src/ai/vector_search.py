import base64
import io
import logging
import threading
import time
from datetime import datetime, timezone

import cv2
import numpy as np


class VectorSearch:
    def __init__(self, camera, interval=10.0):
        self.camera = camera
        self.interval = interval
        self.collection = None
        self._encoder = None
        self._model_name = None
        self.ready = False
        self.error = ""
        self._running = False
        self._lock = threading.Lock()
        self._index_count = 0
        try:
            import chromadb
            self._chroma = chromadb.Client(
                chromadb.Settings(anonymized_telemetry=False, is_persistent=True, persist_directory="./chroma_db")
            )
            self.collection = self._chroma.get_or_create_collection("frames")
            self._ready_chroma = True
        except Exception as e:
            self._ready_chroma = False
            self.error = f"ChromaDB init failed: {e}"

    def _load_encoder(self):
        if self._encoder is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer
            import torch
            self._model_name = "clip-ViT-B-32"
            self._encoder = SentenceTransformer(self._model_name)
            self.ready = True
            return True
        except Exception as e:
            self.error = f"CLIP load failed: {e}"
            return False

    def _encode_image(self, frame_bytes) -> list[float] | None:
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

    def start(self):
        if not self._ready_chroma:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def _loop(self):
        last_id = -1
        while self._running:
            fid = self.camera.frame_id
            raw = self.camera.latest_frame
            if raw is not None and fid != last_id:
                last_id = fid
                emb = self._encode_image(raw)
                if emb is not None:
                    ts = datetime.now(timezone.utc).isoformat()
                    try:
                        self.collection.add(
                            embeddings=[emb],
                            ids=[f"fid_{fid}"],
                            metadatas=[{"frame_id": fid, "timestamp": ts}],
                        )
                        with self._lock:
                            self._index_count += 1
                    except Exception:
                        pass
            time.sleep(self.interval)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
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
            hits = []
            if results.get("ids") and results["ids"][0]:
                for i, fid in enumerate(results["ids"][0]):
                    meta = (results.get("metadatas") or [{}])[0].get(i, {}) if isinstance(results.get("metadatas"), list) else {}
                    dist = (results.get("distances") or [[]])[0][i] if results.get("distances") else 0
                    hits.append({
                        "frame_id": meta.get("frame_id", fid),
                        "timestamp": meta.get("timestamp", ""),
                        "score": round(1.0 - float(dist), 4),
                    })
            return hits
        except Exception:
            return []

    @property
    def info(self) -> dict:
        return {
            "ready": self.ready,
            "chroma_ok": self._ready_chroma,
            "index_count": self._index_count,
            "error": self.error,
        }
