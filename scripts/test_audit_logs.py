#!/usr/bin/env python3
"""
Test Script für Audit Logging
Simuliert verschiedene Security Events und prüft Log-Format
"""

import logging
import sys
import re

# Setup logging wie in Flask App
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Test Cases
test_cases = [
    {
        "name": "Failed Login - Invalid Credentials",
        "log": lambda: logger.warning(
            f"SECURITY[LOGIN_FAILED]: user=testuser ip=192.168.1.100 "
            f"attempts=1/5 reason=invalid_credentials"
        ),
        "expected_pattern": r"SECURITY\[LOGIN_FAILED\]:.*ip=192\.168\.1\.100"
    },
    {
        "name": "Account Lockout",
        "log": lambda: logger.warning(
            f"SECURITY[LOCKOUT]: user=testuser ip=192.168.1.100 "
            f"remaining=14min reason=account_locked"
        ),
        "expected_pattern": r"SECURITY\[LOCKOUT\]:.*ip=192\.168\.1\.100"
    },
    {
        "name": "Successful Login",
        "log": lambda: logger.info(
            f"SECURITY[LOGIN_SUCCESS]: user=testuser ip=192.168.1.100 "
            f"2fa=disabled method=password"
        ),
        "expected_pattern": r"SECURITY\[LOGIN_SUCCESS\]:.*ip=192\.168\.1\.100"
    },
    {
        "name": "2FA Failed",
        "log": lambda: logger.warning(
            f"SECURITY[2FA_FAILED]: user=testuser ip=192.168.1.100 "
            f"reason=invalid_token"
        ),
        "expected_pattern": r"SECURITY\[2FA_FAILED\]:.*ip=192\.168\.1\.100"
    },
    {
        "name": "Logout",
        "log": lambda: logger.info(
            f"SECURITY[LOGOUT]: user=testuser ip=192.168.1.100"
        ),
        "expected_pattern": r"SECURITY\[LOGOUT\]:.*ip=192\.168\.1\.100"
    }
]

print("🧪 Testing Audit Log Format for Fail2Ban Compatibility\n")
print("=" * 70)

for i, test in enumerate(test_cases, 1):
    print(f"\n{i}. {test['name']}")
    print("-" * 70)
    
    # Capture log output
    import io
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    
    # Generate log
    test['log']()
    
    # Get output
    output = log_capture.getvalue()
    logger.removeHandler(handler)
    
    # Check pattern
    if re.search(test['expected_pattern'], output):
        print(f"✅ Pattern matched: {test['expected_pattern']}")
        print(f"📝 Log output:\n{output}")
    else:
        print(f"❌ Pattern NOT matched: {test['expected_pattern']}")
        print(f"📝 Log output:\n{output}")

print("\n" + "=" * 70)
print("✅ All tests completed!")
print("\n📋 Fail2Ban Integration:")
print("   - Filter: fail2ban-filter.conf")
print("   - Jail: fail2ban-jail.conf")
print("   - Log paths: logs/gunicorn_error.log")
