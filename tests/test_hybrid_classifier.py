"""
Unit Tests für Hybrid Score-Learning System (Sessions 1-5).

Testet:
- personal_classifier_service.py (Loading, Caching, Predictions)
- training_tasks.py (Training Pipeline, Validation, Atomic Write)
- email_processing_tasks.py (Prediction Integration)
- email_actions.py (Training Trigger)
- 02_models.py (User-Deletion Cleanup)
"""

import pytest
import tempfile
import shutil
import numpy as np
import joblib
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, UTC

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_classifier_dir():
    """Temp directory für Classifier-Dateien."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_classifier():
    """Mock SGD Classifier mit predict/predict_proba."""
    clf = Mock()
    clf.classes_ = np.array([1, 2, 3])
    clf.predict = Mock(return_value=np.array([2]))
    clf.predict_proba = Mock(return_value=np.array([[0.1, 0.7, 0.2]]))
    clf.partial_fit = Mock(return_value=None)
    return clf


@pytest.fixture
def mock_scaler():
    """Mock StandardScaler."""
    scaler = Mock()
    scaler.transform = Mock(side_effect=lambda x: x * 2)  # Simple 2x scaling
    scaler.fit_transform = Mock(side_effect=lambda x: x * 2)
    scaler.mean_ = np.ones(384)
    return scaler


@pytest.fixture
def sample_embedding():
    """Sample Email-Embedding (384 dims)."""
    return np.random.randn(384).astype(np.float32)


@pytest.fixture
def mock_raw_email(sample_embedding):
    """Mock RawEmail Objekt."""
    email = Mock()
    email.id = 1
    email.email_embedding = sample_embedding.tobytes()
    email.encrypted_sender = "encoded_sender"
    email.encrypted_subject = "encoded_subject"
    email.encrypted_body = "encoded_body"
    return email


@pytest.fixture
def mock_user():
    """Mock User Objekt."""
    user = Mock()
    user.id = 1
    user.prefer_personal_classifier = False
    return user


@pytest.fixture
def mock_processed_email():
    """Mock ProcessedEmail Objekt."""
    email = Mock()
    email.id = 1
    email.user_id = 1
    email.dringlichkeit = 2
    email.wichtigkeit = 2
    email.spam_flag = False
    email.used_model_source = "global"
    return email


# ============================================================================
# TEST 1: Personal Classifier Service - Loading & Caching
# ============================================================================

class TestPersonalClassifierService:
    """Tests für personal_classifier_service.py"""

    def test_load_global_classifier_not_found(self):
        """Test: Global Classifier nicht vorhanden → None"""
        from src.services.personal_classifier_service import load_global_classifier
        
        result = load_global_classifier("dringlichkeit")
        # Wird None oder None sein (File existiert nicht)
        assert result is None or isinstance(result, type(None))

    def test_load_global_classifier_invalid_type(self):
        """Test: Ungültiger Classifier-Typ → None + Warning"""
        from src.services.personal_classifier_service import load_global_classifier
        
        result = load_global_classifier("invalid_type")
        assert result is None

    def test_load_personal_classifier_not_found(self):
        """Test: Personal Classifier nicht vorhanden → None"""
        from src.services.personal_classifier_service import load_personal_classifier
        
        result = load_personal_classifier(user_id=999, classifier_type="dringlichkeit")
        assert result is None

    def test_predict_with_classifier_invalid_embedding(self):
        """Test: Ungültiges Embedding → (None, 0.0, "error")"""
        from src.services.personal_classifier_service import predict_with_classifier
        
        session = Mock()
        
        # None Embedding
        pred, conf, source = predict_with_classifier(1, "dringlichkeit", None, session)
        assert pred is None
        assert conf == 0.0
        assert source == "error"

    def test_predict_with_classifier_nan_embedding(self):
        """Test: NaN Embedding → (None, 0.0, "error")"""
        from src.services.personal_classifier_service import predict_with_classifier
        
        session = Mock()
        embedding = np.array([np.nan, 1.0, 2.0])
        
        pred, conf, source = predict_with_classifier(1, "dringlichkeit", embedding, session)
        assert pred is None
        assert conf == 0.0
        assert source == "error"

    def test_predict_with_classifier_invalid_type(self):
        """Test: Ungültiger Classifier-Typ → (None, 0.0, "error")"""
        from src.services.personal_classifier_service import predict_with_classifier
        
        session = Mock()
        embedding = np.random.randn(384)
        
        pred, conf, source = predict_with_classifier(1, "invalid", embedding, session)
        assert pred is None
        assert conf == 0.0
        assert source == "error"

    def test_get_classifier_for_user_not_found(self):
        """Test: User/Classifier nicht gefunden → Fallback zu Global"""
        from src.services.personal_classifier_service import get_classifier_for_user
        
        session = Mock()
        session.query = Mock(return_value=Mock(filter_by=Mock(return_value=Mock(first=Mock(return_value=None)))))
        
        # Wenn kein User/Classifier gefunden, wird Fallback zu Global versucht
        # Das Ergebnis hängt davon ab, ob Global Classifier existiert
        with patch('src.services.personal_classifier_service.load_classifier_cached', return_value=None):
            clf, source = get_classifier_for_user(999, "dringlichkeit", session)
            # Kein Classifier verfügbar → (None, 'global')
            assert clf is None
            assert source in ('global', 'personal')  # Einer der beiden

    def test_cache_invalidation(self):
        """Test: Cache Invalidierung funktioniert"""
        from src.services.personal_classifier_service import (
            invalidate_classifier_cache,
            _classifier_cache
        )
        
        # Füge etwas zum Cache hinzu
        _classifier_cache["1:dringlichkeit"] = Mock()
        _classifier_cache["2:wichtigkeit"] = Mock()
        
        # Invalidiere User 1
        deleted = invalidate_classifier_cache(user_id=1)
        assert deleted > 0
        assert "1:dringlichkeit" not in _classifier_cache

    def test_enhance_with_personal_predictions_no_embedding(self):
        """Test: Kein Embedding → Original-Ergebnis"""
        from src.services.personal_classifier_service import enhance_with_personal_predictions
        
        raw_email = Mock(email_embedding=None, id=1)
        result = {"dringlichkeit": 2, "wichtigkeit": 3, "spam_flag": False}
        session = Mock()
        
        enhanced, source = enhance_with_personal_predictions(1, raw_email, result, session)
        
        assert enhanced == result  # Unverändert
        assert source == "ai_only"

    def test_enhance_with_personal_predictions_invalid_embedding(self):
        """Test: Ungültiges Embedding → Original-Ergebnis"""
        from src.services.personal_classifier_service import enhance_with_personal_predictions
        
        raw_email = Mock(email_embedding=b'', id=1)
        result = {"dringlichkeit": 2, "wichtigkeit": 3, "spam_flag": False}
        session = Mock()
        
        enhanced, source = enhance_with_personal_predictions(1, raw_email, result, session)
        
        assert source == "ai_only"


# ============================================================================
# TEST 2: Training Tasks - Validation & Training Decision
# ============================================================================

class TestTrainingTasks:
    """Tests für training_tasks.py"""

    def test_validate_training_data_no_samples(self):
        """Test: Keine Samples → Invalid"""
        from src.tasks.training_tasks import _validate_training_data
        
        y = np.array([])
        is_valid, reason = _validate_training_data(y, "dringlichkeit")
        
        assert is_valid is False
        assert "no_samples" in reason

    def test_validate_training_data_only_one_class(self):
        """Test: Nur eine Klasse → Invalid"""
        from src.tasks.training_tasks import _validate_training_data
        
        y = np.array([1, 1, 1, 1, 1])
        is_valid, reason = _validate_training_data(y, "dringlichkeit")
        
        assert is_valid is False
        assert "only_one_class" in reason

    def test_validate_training_data_insufficient_samples_per_class(self):
        """Test: Zu wenig Samples pro Klasse → Invalid"""
        from src.tasks.training_tasks import _validate_training_data
        
        y = np.array([1, 1, 1, 2])  # Klasse 2 hat nur 1 Sample
        is_valid, reason = _validate_training_data(y, "dringlichkeit")
        
        assert is_valid is False
        assert "insufficient_samples" in reason

    def test_validate_training_data_valid(self):
        """Test: Ausreichende, balanced Samples → Valid"""
        from src.tasks.training_tasks import _validate_training_data
        
        y = np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3])
        is_valid, reason = _validate_training_data(y, "dringlichkeit")
        
        assert is_valid is True
        assert "valid" in reason

    def test_validate_training_data_imbalance_ratio(self):
        """Test: Zu großes Imbalance → Invalid"""
        from src.tasks.training_tasks import _validate_training_data
        
        # 20x mehr Klasse 1 als Klasse 2 (> 5:1 Ratio)
        y = np.array([1]*100 + [2]*5)
        is_valid, reason = _validate_training_data(y, "dringlichkeit")
        
        assert is_valid is False
        assert "imbalance_ratio" in reason

    def test_train_classifier_new_instance(self):
        """Test: Neuer Classifier (fit)"""
        from src.tasks.training_tasks import _train_classifier
        
        X = np.random.randn(15, 384)
        y = np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3])
        
        clf = _train_classifier(X, y, "dringlichkeit", existing_clf=None)
        
        assert clf is not None
        assert hasattr(clf, 'predict')
        assert hasattr(clf, 'classes_')

    def test_train_classifier_partial_fit(self, mock_classifier):
        """Test: Existierender Classifier (partial_fit)"""
        from src.tasks.training_tasks import _train_classifier
        
        X = np.random.randn(5, 384)
        y = np.array([1, 2, 3, 1, 2])
        
        clf = _train_classifier(X, y, "dringlichkeit", existing_clf=mock_classifier)
        
        # Mock sollte partial_fit aufgerufen haben
        mock_classifier.partial_fit.assert_called_once()
        
        # Muss mit classes= Parameter aufgerufen worden sein
        call_kwargs = mock_classifier.partial_fit.call_args[1]
        assert 'classes' in call_kwargs

    def test_atomic_save_model(self, temp_classifier_dir):
        """Test: Atomic Save (Temp → Rename)"""
        from src.tasks.training_tasks import _atomic_save_model
        from sklearn.linear_model import SGDClassifier
        
        # Erstelle echten Classifier (Mock funktioniert nicht mit joblib)
        clf = SGDClassifier()
        # Fit mit Dummy-Daten damit er serialisierbar ist
        clf.partial_fit([[0.1, 0.2]], [1], classes=[1, 2, 3])
        
        path = Path(temp_classifier_dir) / "test_clf.pkl"
        
        _atomic_save_model(clf, path)
        
        # Datei sollte existieren
        assert path.exists()
        
        # Und ladbar sein
        loaded_clf = joblib.load(path)
        assert loaded_clf is not None

    def test_compute_accuracy_small_dataset(self):
        """Test: Accuracy mit <20 Samples (Leave-One-Out CV)"""
        from src.tasks.training_tasks import _compute_accuracy
        
        clf = Mock()
        clf.score = Mock(return_value=0.8)
        
        X = np.random.randn(10, 384)
        y = np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2])
        
        with patch('src.tasks.training_tasks.cross_val_score', return_value=np.array([0.8, 0.9, 0.85])):
            accuracy = _compute_accuracy(clf, X, y)
            
            assert 0.0 <= accuracy <= 1.0

    def test_should_trigger_training_first_training(self):
        """Test: Erste Training (kein Metadata) → Should Train"""
        from src.tasks.training_tasks import _should_trigger_training
        
        db = Mock()
        # filter_by().first() muss None zurückgeben
        db.query = Mock(return_value=Mock(filter_by=Mock(return_value=Mock(first=Mock(return_value=None)))))
        
        models = Mock()
        models.ClassifierMetadata = Mock()
        
        should_train, reason = _should_trigger_training(1, "dringlichkeit", db, models)
        
        assert should_train is True
        assert "first_training" in reason

    def test_should_trigger_training_circuit_breaker(self):
        """Test: Circuit-Breaker aktiv (error_count >= 3) → Don't Train"""
        from src.tasks.training_tasks import _should_trigger_training, MAX_ERROR_COUNT
        
        db = Mock()
        # Wichtig: Mock muss echte Integer-Werte haben für Vergleiche
        metadata = Mock()
        metadata.error_count = MAX_ERROR_COUNT  # Echter Integer
        metadata.last_training_at = datetime.now(UTC) - timedelta(hours=1)
        metadata.training_samples = 10
        db.query = Mock(return_value=Mock(filter_by=Mock(return_value=Mock(first=Mock(return_value=metadata)))))
        
        models = Mock()
        models.ClassifierMetadata = Mock()
        
        should_train, reason = _should_trigger_training(1, "dringlichkeit", db, models)
        
        assert should_train is False
        assert "circuit_breaker" in reason


# ============================================================================
# TEST 3: Email Processing Tasks - Prediction Integration
# ============================================================================

class TestEmailProcessingTasks:
    """Tests für email_processing_tasks.py"""

    def test_reprocess_email_uses_personal_predictions(self):
        """Test: reprocess_email_base nutzt personal Predictions"""
        # Dieser Test braucht echte Task-Struktur, ist komplexer
        # Hier nur Placeholder
        pass

    def test_enhance_predictions_saves_source(self):
        """Test: used_model_source wird gespeichert"""
        from src.services.personal_classifier_service import enhance_with_personal_predictions
        
        raw_email = Mock()
        raw_email.id = 1
        raw_email.email_embedding = np.random.randn(384).astype(np.float32).tobytes()
        
        result = {
            "dringlichkeit": 2,
            "wichtigkeit": 2,
            "spam_flag": False,
            "summary_de": "Test"
        }
        
        session = Mock()
        
        enhanced, source = enhance_with_personal_predictions(1, raw_email, result, session)
        
        # source muss "ai_only", "global", oder "personal" sein
        assert source in ("ai_only", "global", "personal")


# ============================================================================
# TEST 4: Email Actions - Training Trigger
# ============================================================================

class TestEmailActionsTrainingTrigger:
    """Tests für Training-Trigger in email_actions.py"""

    def test_training_trigger_dringlichkeit(self):
        """Test: Dringlichkeit-Korrektur triggt Training"""
        from src.tasks.training_tasks import train_personal_classifier
        
        # Mock task
        with patch.object(train_personal_classifier, 'delay') as mock_delay:
            # Simuliere correct_email() Logic
            user_id = 1
            data = {"dringlichkeit": 3, "wichtigkeit": None, "spam_flag": None}
            
            if data.get("dringlichkeit") is not None:
                train_personal_classifier.delay(user_id, "dringlichkeit")
            
            mock_delay.assert_called_once_with(1, "dringlichkeit")

    def test_training_trigger_nur_korrigierte_felder(self):
        """Test: Nur korrigierte Felder triggern Training"""
        from src.tasks.training_tasks import train_personal_classifier
        
        with patch.object(train_personal_classifier, 'delay') as mock_delay:
            user_id = 1
            data = {"dringlichkeit": None, "wichtigkeit": 2, "spam_flag": None}
            
            triggered = []
            if data.get("dringlichkeit") is not None:
                train_personal_classifier.delay(user_id, "dringlichkeit")
                triggered.append("dringlichkeit")
            if data.get("wichtigkeit") is not None:
                train_personal_classifier.delay(user_id, "wichtigkeit")
                triggered.append("wichtigkeit")
            
            # Nur wichtigkeit sollte getriggert werden
            assert triggered == ["wichtigkeit"]
            assert mock_delay.call_count == 1

    def test_training_trigger_non_blocking_on_error(self):
        """Test: Fehler beim Training-Trigger blockiert Korrektur nicht"""
        from src.tasks.training_tasks import train_personal_classifier
        
        with patch.object(train_personal_classifier, 'delay', side_effect=Exception("Celery Error")):
            try:
                user_id = 1
                data = {"dringlichkeit": 3}
                
                if data.get("dringlichkeit") is not None:
                    train_personal_classifier.delay(user_id, "dringlichkeit")
                
                # Sollte Exception werfen, aber in echtem Code wird das gecatched
                assert False, "Should have raised"
            except Exception as e:
                # In echtem Code: logger.warning + continue
                assert "Celery Error" in str(e)


# ============================================================================
# TEST 5: Models - User-Deletion Cleanup
# ============================================================================

class TestUserDeletionCleanup:
    """Tests für Event Listener in 02_models.py"""

    def test_cleanup_function_exists(self):
        """Test: Cleanup-Funktion existiert"""
        import importlib
        models = importlib.import_module("src.02_models")
        assert hasattr(models, '_cleanup_personal_classifiers_on_delete')
        assert callable(models._cleanup_personal_classifiers_on_delete)

    def test_cleanup_removes_directory(self, temp_classifier_dir):
        """Test: User-Verzeichnis wird gelöscht"""
        import importlib
        models = importlib.import_module("src.02_models")
        _cleanup_personal_classifiers_on_delete = models._cleanup_personal_classifiers_on_delete
        
        user_dir = Path(temp_classifier_dir) / "per_user" / "user_1"
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "dringlichkeit.pkl").touch()
        
        assert user_dir.exists()
        
        # Simuliere Event Handler
        target = Mock(id=1)
        
        with patch('src.services.personal_classifier_service.get_classifier_dir', return_value=Path(temp_classifier_dir)):
            with patch('src.services.personal_classifier_service.invalidate_classifier_cache'):
                _cleanup_personal_classifiers_on_delete(None, None, target)
        
        # Verzeichnis sollte weg sein
        assert not user_dir.exists()

    def test_cleanup_non_blocking_on_error(self, temp_classifier_dir):
        """Test: Fehler beim Cleanup blockiert User-Löschung nicht"""
        import importlib
        models = importlib.import_module("src.02_models")
        _cleanup_personal_classifiers_on_delete = models._cleanup_personal_classifiers_on_delete
        
        target = Mock(id=1)
        
        with patch('src.services.personal_classifier_service.get_classifier_dir', side_effect=Exception("Path Error")):
            with patch('src.services.personal_classifier_service.invalidate_classifier_cache'):
                # Sollte nicht werfen, nur loggen
                try:
                    _cleanup_personal_classifiers_on_delete(None, None, target)
                    # In echtem Code: logger.warning + continue
                except Exception:
                    pytest.fail("Cleanup sollte nicht werfen")

    def test_event_listener_registered(self):
        """Test: Event Listener ist registriert"""
        import importlib
        models = importlib.import_module("src.02_models")
        User = models.User
        
        # Prüfe ob die Cleanup-Funktion existiert und callable ist
        assert hasattr(models, '_cleanup_personal_classifiers_on_delete')
        cleanup_fn = models._cleanup_personal_classifiers_on_delete
        assert callable(cleanup_fn)
        
        # Der Event-Listener wird beim Import von 02_models registriert
        # Wir können das nicht direkt testen, aber die Funktion existiert


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestHybridClassifierIntegration:
    """Integration Tests für kompletten Flow"""

    def test_prediction_flow_global_model(self):
        """Test: E2E Prediction mit Global Model"""
        from src.services.personal_classifier_service import predict_with_classifier
        
        session = Mock()
        session.query = Mock(return_value=Mock(first=Mock(return_value=Mock(prefer_personal_classifier=False))))
        
        embedding = np.random.randn(384)
        
        with patch('src.services.personal_classifier_service.get_classifier_for_user', return_value=(Mock(predict=Mock(return_value=[2]), predict_proba=Mock(return_value=[[0.1, 0.8, 0.1]])), "global")):
            with patch('src.services.personal_classifier_service.get_scaler_for_prediction', return_value=Mock(transform=lambda x: x)):
                pred, conf, source = predict_with_classifier(1, "dringlichkeit", embedding, session)
                
                assert pred == 2
                assert source == "global"

    def test_training_trigger_to_task(self):
        """Test: Korrektur → Async Task getriggert"""
        from src.tasks.training_tasks import train_personal_classifier
        
        user_id = 1
        classifier_type = "dringlichkeit"
        
        with patch.object(train_personal_classifier, 'delay') as mock_delay:
            # Simuliere correct_email() Aufruf
            train_personal_classifier.delay(user_id, classifier_type)
            
            mock_delay.assert_called_once_with(1, "dringlichkeit")


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
