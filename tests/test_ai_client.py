"""
Tests für KI-Client Interface
"""

import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Numerische Module mit importlib laden
ai_client_module = importlib.import_module(".03_ai_client", "src")
AIClient = ai_client_module.AIClient
LocalOllamaClient = ai_client_module.LocalOllamaClient
get_ai_client = ai_client_module.get_ai_client


def test_ai_client_interface():
    """Test dass AIClient ein abstraktes Interface ist"""
    try:
        client = AIClient()
        assert False, "AIClient sollte nicht direkt instanziierbar sein"
    except TypeError:
        pass  # Erwartet


def test_ollama_client_instantiation():
    """Test Ollama-Client Erstellung"""
    client = LocalOllamaClient(model="mistral:7b")
    assert client.model == "mistral:7b"
    # 127.0.0.1 statt localhost (wie in Produktion konfiguriert)
    assert "11434" in client.base_url  # Port prüfen, nicht exakte URL


def test_ollama_analyze_returns_dict():
    """Test dass analyze_email ein Dict zurückgibt"""
    client = LocalOllamaClient()
    result = client.analyze_email(
        subject="Test",
        body="Dies ist ein Test"
    )
    
    assert isinstance(result, dict)
    assert 'dringlichkeit' in result
    assert 'wichtigkeit' in result
    assert 'kategorie_aktion' in result
    assert 'tags' in result
    assert 'spam_flag' in result
    assert 'summary_de' in result
    assert 'text_de' in result


def test_ollama_analyze_value_ranges():
    """Test dass Rückgabewerte im erwarteten Bereich liegen"""
    client = LocalOllamaClient()
    result = client.analyze_email(
        subject="Wichtig: Rechnung",
        body="Bitte zahlen Sie die Rechnung."
    )
    
    assert 1 <= result['dringlichkeit'] <= 3
    assert 1 <= result['wichtigkeit'] <= 3
    assert isinstance(result['spam_flag'], bool)
    assert isinstance(result['tags'], list)


def test_get_ai_client_factory():
    """Test Factory-Funktion für verschiedene Backends"""
    client = get_ai_client("ollama")
    assert isinstance(client, LocalOllamaClient)
    
    try:
        get_ai_client("invalid_backend")
        assert False, "Sollte ValueError werfen"
    except ValueError:
        pass  # Erwartet


def test_ai_client_with_custom_params():
    """Test Client mit benutzerdefinierten Parametern"""
    client = get_ai_client(
        "ollama",
        model="llama3:8b",
        base_url="http://192.168.1.100:11434"
    )
    
    assert client.model == "llama3:8b"
    assert client.base_url == "http://192.168.1.100:11434"


if __name__ == "__main__":
    print("🧪 Führe AI-Client-Tests aus...\n")
    
    tests = [
        test_ai_client_interface,
        test_ollama_client_instantiation,
        test_ollama_analyze_returns_dict,
        test_ollama_analyze_value_ranges,
        test_get_ai_client_factory,
        test_ai_client_with_custom_params
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"⚠️  {test_func.__name__}: {e}")
            failed += 1
    
    print(f"\n📊 Ergebnis: {passed} bestanden, {failed} fehlgeschlagen")
