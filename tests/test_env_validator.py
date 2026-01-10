"""
Test für Environment Validator
Prüft dass die Umgebungs-Validierung korrekt funktioniert
"""

import os
import sys
import unittest
from io import StringIO
from unittest.mock import patch
import importlib


class TestEnvironmentValidator(unittest.TestCase):
    """Tests für src/00_env_validator.py"""

    def setUp(self):
        """Setup vor jedem Test"""
        self.original_env = os.environ.copy()

    def tearDown(self):
        """Cleanup nach jedem Test"""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_flask_secret_key_optional(self):
        """Teste dass gültige Umgebung mit FLASK_SECRET_KEY validiert wird"""
        os.environ['FLASK_SECRET_KEY'] = 'test-secret-key-12345'
        os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'
        os.environ['OLLAMA_MODEL'] = 'mistral:7b'
        os.environ['AI_BACKEND'] = 'ollama'
        os.environ['USE_CLOUD_AI'] = 'false'

        env_validator = importlib.import_module('.00_env_validator', 'src')

        result = env_validator.EnvironmentValidator.validate()
        self.assertTrue(result)

    def test_valid_environment(self):
        """Teste dass gültige Umgebung akzeptiert wird"""
        os.environ['FLASK_SECRET_KEY'] = 'test-secret-key-12345'
        os.environ['OLLAMA_BASE_URL'] = 'http://localhost:11434'
        os.environ['OLLAMA_MODEL'] = 'mistral:7b'
        os.environ['AI_BACKEND'] = 'ollama'
        os.environ['USE_CLOUD_AI'] = 'false'

        env_validator = importlib.import_module('.00_env_validator', 'src')

        result = env_validator.EnvironmentValidator.validate()
        self.assertTrue(result)

    def test_missing_ollama_vars(self):
        """Teste dass Ollama-Variablen validiert werden"""
        os.environ['AI_BACKEND'] = 'ollama'
        os.environ['USE_CLOUD_AI'] = 'false'
        os.environ.pop('OLLAMA_BASE_URL', None)
        os.environ.pop('OLLAMA_MODEL', None)

        env_validator = importlib.import_module('.00_env_validator', 'src')

        with self.assertRaises(SystemExit) as cm:
            env_validator.EnvironmentValidator.validate()

        self.assertEqual(cm.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
