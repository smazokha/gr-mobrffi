import os
import time
import logging
import numpy as np
from gnuradio import gr

try:
    import chromadb
    from chromadb.config import Settings
except Exception as e:
    raise ImportError("chromadb is required: `pip install chromadb`")

class reid(gr.sync_block):
    """
    docstring for block reid
    """
    def __init__(self,
                 embeddingLength=768,
                 chromaPath="/tmp/mobrffi_chroma",
                 collectionName="mobrffi",
                 cosineThreshold=0.1):
        gr.sync_block.__init__(
            self,
            name="MobRFFI Classifier",
            in_sig=[(np.float32, int(embeddingLength))],
            out_sig=[np.int32],
        )

        # Parameters
        self.embeddingLength = int(embeddingLength)
        self.chromaPath = str(chromaPath)
        self.collectionName = str(collectionName)
        self.threshold = float(cosineThreshold)

        # Logging
        self._log = logging.getLogger("mobrffi.reid")
        if not self._log.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
            self._log.addHandler(h)
        self._log.setLevel(logging.INFO)

        # Validation
        if self.embeddingLength < 512: raise ValueError("embeddingLength must be at least 512 values long.")
        if self.threshold < 0.0: raise ValueError("cosineThreshold must be non-negative.")
        if not self.chromaPath: raise ValueError("chromaPath must be a valid directory path.")

        os.makedirs(self.chromaPath, exist_ok=True)

        # Create client and fresh collection in Chroma (purge if exists)
        self._chroma = chromadb.PersistentClient(
            path=self.chromaPath,
            settings=Settings(allow_reset=True),
        )

        try:
            self._chroma.delete_collection(self.collectionName)
        except Exception:
            pass

        # Create a new collection to store cosine distances
        self._db_collection = self._chroma.create_collection(
            name=self.collectionName,
            metadata={"hnsw:space": "cosine"}
        )
        self._log.info(f"Chroma collection created: {self.collectionName}. Path: {self.chromaPath}")

        # Create a device label registry
        self._device_labels = {}
        self._next_label = 101

    def _enroll(self, embedding):
        label = self._next_label
        self._next_label += 1

        _id = str(label)
        now = time.time()
        self._db_collection.add(
            ids=[_id],
            embeddings=[embedding.astype(np.float32).tolist()],
            metadatas=[{"label": label, "enrolled_at": now}]
        )
        self._device_labels[label] = {"last_update": now, "count": 1}
        self._log.info(f"Enrolled new device; assigned label: {label}")
        return label
    
    def _update_label_stats(self, label):
        label_info = self._device_labels.get(label)
        if label_info is None:
            self._device_labels[label] = {"last_update": time.time(), "count": 1}
        else:
            label_info["last_update"] = time.time()
            label_info["count"] = label_info.get("count", 0) + 1

    def work(self, input_items, output_items):
        in_mat = input_items[0]
        out_vec = output_items[0]

        if in_mat.shape[1] != self.embeddingLength:
            self._log.error(f"Embedding length incorrect: received {in_mat.shape[1]}, but expected {self.embeddingLength}.")
            return 0
        
        produced = 0

        for i in range(in_mat.shape[0]):
            embedding = np.squeeze(in_mat[i].astype(np.float32, copy=False))

            try:
                query_res = self._db_collection.query(
                    query_embeddings=[embedding.tolist()],
                    n_results=1,
                    include=["distances", "metadatas"]
                )
            except Exception as e:
                self._log.error(f"Chroma query failed: {e}")
                return produced
            
            ids = (query_res.get("ids") or [[]])[0]
            distances = (query_res.get("distances") or [[]])[0]
            metadatas = (query_res.get("metadatas") or [[]])[0]

            if len(ids) == 0:
                # This means that there are no matches (likely empty DB); enrolling...
                label = self._enroll(embedding)
                out_vec[i] = np.int32(label)
                produced += 1

                self._log.info(f"NEW DEVICE: ID {label}")

                continue

            best_id = ids[0]
            best_distance = float(distances[0])

            # If device cos distance <= threshold -- this is a known device, returning ID
            if best_distance <= self.threshold:
                if isinstance(metadatas, dict) and "label" in metadatas:
                    label = int(metadatas["label"])
                else:
                    label = int(best_id)
                self._update_label_stats(label)
                out_vec[i] = np.int32(label)

                self._log.info(f"KNOWN DEVICE: ID {label}")
            else: 
                # Otherwise -- unknown; enrolling
                label = self._enroll(embedding)
                out_vec[i] = np.int32(label)

                self._log.info(f"NEW DEVICE: ID {label}")

            produced += 1

        return produced