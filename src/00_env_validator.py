"""
Mail Helper - Environment Validator
Prüft ob alle erforderlichen Umgebungsvariablen beim Start gesetzt sind
"""

import os
import sys


class EnvironmentValidator:
    """Validiert Umgebungsvariablen intelligent basierend auf Konfiguration"""

    CRITICAL_VARS = {
        "FLASK_SECRET_KEY": {
            "description": "Flask Session-Verschlüsselung (PRODUKTION erforderlich!)",
            "hint": 'Generiere mit: python -c "import secrets; print(secrets.token_hex(32))"',
            "required": False,
        },
    }

    AI_BACKEND_VARS = {
        "ollama": {
            "OLLAMA_BASE_URL": "Ollama Server URL (z.B. http://localhost:11434)",
            "OLLAMA_MODEL": "Ollama Modell Name (z.B. mistral:7b)",
        },
        "openai": {
            "OPENAI_API_KEY": "OpenAI API Key (sk-...)",
            "OPENAI_MODEL": "OpenAI Modell (z.B. gpt-4)",
        },
        "mistral": {
            "MISTRAL_API_KEY": "Mistral API Key",
            "MISTRAL_MODEL": "Mistral Modell",
        },
        "anthropic": {
            "ANTHROPIC_API_KEY": "Anthropic API Key",
            "ANTHROPIC_MODEL": "Anthropic Modell",
        },
    }

    @staticmethod
    def validate():
        """Hauptvalidierungs-Methode"""
        errors = []
        warnings = []

        errors.extend(EnvironmentValidator._check_critical_vars())
        errors.extend(EnvironmentValidator._check_ai_backend())

        if errors:
            EnvironmentValidator._print_errors(errors, warnings)
            sys.exit(1)

        if warnings:
            EnvironmentValidator._print_warnings(warnings)

        print("✅ Alle erforderlichen Umgebungsvariablen sind gesetzt\n")
        return True

    @staticmethod
    def _check_critical_vars():
        """Prüft kritische Variablen die immer erforderlich sind"""
        errors = []

        for var, info in EnvironmentValidator.CRITICAL_VARS.items():
            value = os.getenv(var)
            if not value or value.startswith("your-"):
                errors.append(
                    {
                        "var": var,
                        "description": info["description"],
                        "hint": info["hint"],
                        "severity": "CRITICAL",
                    }
                )

        return errors

    @staticmethod
    def _check_ai_backend():
        """Prüft AI-Backend basierend auf Konfiguration"""
        errors = []

        ai_backend = os.getenv("AI_BACKEND", "ollama")
        use_cloud_ai = os.getenv("USE_CLOUD_AI", "false").lower() == "true"

        if use_cloud_ai:
            selected_backend = None
            if os.getenv("OPENAI_API_KEY"):
                selected_backend = "openai"
            elif os.getenv("MISTRAL_API_KEY"):
                selected_backend = "mistral"
            elif os.getenv("ANTHROPIC_API_KEY"):
                selected_backend = "anthropic"

            if not selected_backend:
                errors.append(
                    {
                        "var": "CLOUD AI BACKEND",
                        "description": "USE_CLOUD_AI=true aber kein Cloud-API-Key gesetzt",
                        "hint": "Setze entweder OPENAI_API_KEY, MISTRAL_API_KEY oder ANTHROPIC_API_KEY",
                        "severity": "CRITICAL",
                    }
                )
        else:
            if (
                ai_backend == "ollama"
                or ai_backend not in EnvironmentValidator.AI_BACKEND_VARS
            ):
                required_vars = EnvironmentValidator.AI_BACKEND_VARS.get("ollama", {})
                for var, description in required_vars.items():
                    value = os.getenv(var)
                    if not value or value.startswith("your-"):
                        errors.append(
                            {
                                "var": var,
                                "description": description,
                                "hint": f"Setze {var} oder starte Ollama",
                                "severity": "CRITICAL",
                            }
                        )

        return errors

    @staticmethod
    def _print_errors(errors, warnings):
        """Gibt Fehler formatiert aus"""
        print("\n" + "=" * 70)
        print("🚨 FEHLER: Kritische Umgebungsvariablen fehlen oder sind ungültig")
        print("=" * 70 + "\n")

        for i, error in enumerate(errors, 1):
            print(f"{i}. ❌ {error['var']}")
            print(f"   Beschreibung: {error['description']}")
            print(f"   💡 Hinweis: {error['hint']}")
            print()

        print("=" * 70)
        print("📋 Lösung:")
        print("=" * 70)
        print("1. Kopiere .env.example zu .env (falls nicht vorhanden):")
        print("   cp .env.example .env\n")
        print("2. Bearbeite .env und setze die fehlenden Werte:\n")
        for error in errors:
            print(f"   {error['var']}=<wert>")
        print("\n3. Starte die App neu:")
        print("   python3 -m src.00_main --serve\n")

        if warnings:
            print("=" * 70)
            print("⚠️  WARNUNGEN:")
            print("=" * 70 + "\n")
            for warning in warnings:
                print(f"⚠️  {warning}\n")

    @staticmethod
    def _print_warnings(warnings):
        """Gibt Warnungen aus"""
        print("\n⚠️  WARNUNGEN:\n")
        for warning in warnings:
            print(f"  ⚠️  {warning}")
        print()


def validate_environment():
    """Entry-Point für Environment Validation"""
    EnvironmentValidator.validate()


if __name__ == "__main__":
    validate_environment()
