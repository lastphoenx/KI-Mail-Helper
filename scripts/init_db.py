#!/usr/bin/env python3
import importlib
models = importlib.import_module('.02_models', 'src')
models.init_db('emails.db')
print("Database initialized successfully!")
