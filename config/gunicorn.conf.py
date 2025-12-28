"""
Gunicorn Configuration für KI-Mail-Helper
Production WSGI Server Setup

Usage:
    gunicorn -c config/gunicorn.conf.py src.01_web_app:app
"""

import multiprocessing
import os

# Server Socket
bind = "0.0.0.0:5001"  # HTTPS Port (HTTP Redirector läuft auf 5000)
backlog = 2048  # Max pending connections

# Worker Processes
workers = multiprocessing.cpu_count() * 2 + 1  # Recommendation: (2 x CPU cores) + 1
worker_class = "sync"  # Sync workers für Flask (alternativ: gevent, eventlet)
worker_connections = 1000  # Max connections per worker
max_requests = 1000  # Restart worker after 1000 requests (memory leak prevention)
max_requests_jitter = 50  # Add randomness to max_requests
timeout = 30  # Worker timeout (seconds)
keepalive = 2  # Keep-alive connections

# SSL/TLS Configuration (HTTPS)
# Note: For production use proper certificates from Let's Encrypt
keyfile = None  # Set to cert path or use reverse proxy (nginx/caddy)
certfile = None  # Set to key path or use reverse proxy
ssl_version = None  # TLS version (default: auto)

# Logging
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"  # debug, info, warning, error, critical
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process Naming
proc_name = "ki-mail-helper"

# Security
limit_request_line = 4094  # Max HTTP request line size
limit_request_fields = 100  # Max HTTP headers
limit_request_field_size = 8190  # Max HTTP header size

# Server Mechanics
daemon = False  # Run in foreground (systemd handles daemonization)
pidfile = None  # PID file (systemd tracks process)
umask = 0o007  # File creation mask
user = None  # Run as user (set in systemd service)
group = None  # Run as group (set in systemd service)
tmp_upload_dir = None  # Temp directory for file uploads

# Application
# Environment variables for Flask
raw_env = [
    "FLASK_ENV=production",
    "FLASK_DEBUG=False",
]

def on_starting(server):
    """Called just before the master process is initialized."""
    print("🚀 Starting Gunicorn server...")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    print("🔄 Reloading workers...")

def when_ready(server):
    """Called just after the server is started."""
    print(f"✅ Gunicorn ready with {workers} workers on {bind}")

def on_exit(server):
    """Called just before exiting Gunicorn."""
    print("👋 Shutting down Gunicorn...")
