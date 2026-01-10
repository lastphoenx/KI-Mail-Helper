#!/usr/bin/env python3
"""
train_classifier.py
Training-Skript für ML-Klassifikatoren (Dringlichkeit, Wichtigkeit, etc.)

Wird später verwendet, um Embeddings + Labeled-Daten → .pkl-Models zu trainieren.
Für jetzt: Skelett mit Placeholder-Struktur.

Ablauf:
1. Trainingsdaten laden (DB oder CSV)
2. Mit all-minilm:22m Embeddings erzeugen
3. scikit-learn Klassifikatoren trainieren
4. .pkl-Dateien in src/classifiers/ speichern
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import json

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent.parent
CLASSIFIER_DIR = BASE_DIR / "src" / "classifiers"
CLASSIFIER_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(BASE_DIR / "src"))

from ai_client_03 import LocalOllamaClient


class EmbeddingClassifierTrainer:
    """Trainiert Klassifikatoren mit Embeddings + scikit-learn."""

    def __init__(self, embedding_model: str = "all-minilm:22m", ollama_url: str = "http://127.0.0.1:11434"):
        self.embedding_client = LocalOllamaClient(model=embedding_model, base_url=ollama_url)
        self.classifiers = {
            "dringlichkeit": None,
            "wichtigkeit": None,
            "kategorie": None,
            "spam": None,
        }
        self.label_encoders = {}

    def get_embeddings_for_texts(self, texts: List[str]) -> np.ndarray:
        """Erzeugt Embeddings für eine Liste von Texten."""
        embeddings = []
        for i, text in enumerate(texts):
            if i % 10 == 0:
                logger.info(f"Embedding {i}/{len(texts)}...")
            embedding = self.embedding_client._get_embedding(text)
            if embedding:
                embeddings.append(embedding)
            else:
                logger.warning(f"Embedding fehlgeschlagen für Text {i}: {text[:50]}...")
                embeddings.append(np.zeros(384))
        return np.array(embeddings)

    def train_classifier_from_csv(self, csv_file: str, label_column: str, text_column: str):
        """
        Trainiert Klassifikator aus CSV-Datei.
        
        Args:
            csv_file: Pfad zur CSV mit Spalten [text_column, label_column]
            label_column: Name der Label-Spalte (z.B. 'dringlichkeit')
            text_column: Name der Text-Spalte (z.B. 'subject_body')
        """
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas nicht installiert. Bitte: pip install pandas")
            return False

        logger.info(f"Lade Trainingsdaten aus {csv_file}...")
        df = pd.read_csv(csv_file)

        if text_column not in df.columns or label_column not in df.columns:
            logger.error(f"Spalten '{text_column}' oder '{label_column}' nicht gefunden in CSV")
            return False

        texts = df[text_column].tolist()
        labels = df[label_column].tolist()

        logger.info(f"Generiere Embeddings für {len(texts)} Texte...")
        X = self.get_embeddings_for_texts(texts)

        logger.info(f"Trainiere {label_column}-Klassifikator...")
        le = LabelEncoder()
        y = le.fit_transform(labels)

        clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        clf.fit(X, y)

        self.classifiers[label_column] = clf
        self.label_encoders[label_column] = le

        output_file = CLASSIFIER_DIR / f"{label_column}_clf.pkl"
        joblib.dump(clf, output_file)
        logger.info(f"✅ Klassifikator gespeichert: {output_file}")

        encoder_file = CLASSIFIER_DIR / f"{label_column}_encoder.pkl"
        joblib.dump(le, encoder_file)
        logger.info(f"✅ Label-Encoder gespeichert: {encoder_file}")

        return True

    def train_classifier_from_db(self, label_column: str, min_samples: int = 10):
        """
        Trainiert Klassifikator aus Datenbank.
        
        Args:
            label_column: Spalte zu trainieren (z.B. 'dringlichkeit')
            min_samples: Minimale Anzahl von Samples pro Label
        
        Note:
            Benötigt Datenbankzugriff. Später implementieren, wenn Schema bekannt.
        """
        logger.warning(f"train_classifier_from_db ist noch nicht implementiert für '{label_column}'")
        logger.warning("Nutzen Sie stattdessen train_classifier_from_csv mit exportierten Daten")
        return False


def main():
    """Hauptfunktion für Demo/Testen."""
    logger.info("🎓 Training-Skelett geladen.")
    logger.info("")
    logger.info("Beispiel-Nutzung (wenn CSV vorliegt):")
    logger.info("")
    logger.info("  trainer = EmbeddingClassifierTrainer()")
    logger.info("  trainer.train_classifier_from_csv(")
    logger.info("    'data/labeled_mails.csv',")
    logger.info("    label_column='dringlichkeit',")
    logger.info("    text_column='subject_body'")
    logger.info("  )")
    logger.info("")
    logger.info("Später: Klassifikatoren werden automatisch in LocalOllamaClient geladen.")


if __name__ == "__main__":
    main()
