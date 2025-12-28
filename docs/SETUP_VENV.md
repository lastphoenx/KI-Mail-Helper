# Virtual Environment Setup

## Initial Setup (einmalig)

```bash
cd /home/thomas/projects/KI-Mail-Helper

# 1. Erstelle venv
python3 -m venv venv

# 2. Aktiviere venv
source venv/bin/activate

# 3. Installiere ML-Dependencies
pip install -r requirements-ml.txt

# 4. Oder installiere alle bekannten Dependencies
pip install -r requirements-venv.txt
```

## Vor jedem Start

```bash
# In den Projekt-Ordner gehen
cd /home/thomas/projects/KI-Mail-Helper

# venv aktivieren
source venv/bin/activate

# Dann kann man die App starten
python3 src/00_main.py
```

## Wichtig für Scripts

Alle Python-Scripts sollten mit der venv ausgeführt werden:

```bash
source venv/bin/activate
python3 scripts/train_classifier.py
python3 scripts/check_db.py
```

Oder direkt:
```bash
/home/thomas/projects/KI-Mail-Helper/venv/bin/python3 scripts/train_classifier.py
```

## Venv Status

✅ **venv/** ist in `.gitignore` eingetragen → wird nicht committed
✅ **ML-Packages sind isoliert** in der venv → kein System-Break mehr
✅ **requirements-ml.txt** existiert für zukünftige Setup
