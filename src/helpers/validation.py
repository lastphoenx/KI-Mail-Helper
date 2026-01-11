# src/helpers/validation.py
"""Input validation helpers for API endpoints.

Extracted from 01_web_app.py lines 415-520.
"""


def validate_string(value, field_name, min_len=1, max_len=1000, allow_empty=False):
    """Validate string input for API endpoints.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        min_len: Minimum length (default: 1)
        max_len: Maximum length (default: 1000)
        allow_empty: Allow empty strings (default: False)
        
    Returns:
        Cleaned string or None if allow_empty=True and value is empty
        
    Raises:
        ValueError: If validation fails
    """
    if value is None:
        if allow_empty:
            return None
        raise ValueError(f"{field_name} ist erforderlich")
    
    if not isinstance(value, str):
        raise ValueError(f"{field_name} muss ein String sein")
    
    value = value.strip()
    
    if len(value) == 0:
        if allow_empty:
            return None
        raise ValueError(f"{field_name} darf nicht leer sein")
    
    if len(value) < min_len:
        raise ValueError(f"{field_name} muss mindestens {min_len} Zeichen lang sein")
    
    if len(value) > max_len:
        raise ValueError(f"{field_name} darf maximal {max_len} Zeichen lang sein")
    
    return value


def validate_integer(value, field_name, min_val=None, max_val=None):
    """Validate integer input for API endpoints.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        min_val: Minimum value (optional)
        max_val: Maximum value (optional)
        
    Returns:
        Integer value
        
    Raises:
        ValueError: If validation fails
    """
    if value is None:
        raise ValueError(f"{field_name} ist erforderlich")
    
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise ValueError(f"{field_name} muss eine Zahl sein")
    
    if min_val is not None and value < min_val:
        raise ValueError(f"{field_name} muss mindestens {min_val} sein")
    
    if max_val is not None and value > max_val:
        raise ValueError(f"{field_name} darf maximal {max_val} sein")
    
    return value


def validate_email(value, field_name):
    """Validate email address.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        
    Returns:
        Normalized email address (lowercase, stripped)
        
    Raises:
        ValueError: If validation fails
    """
    if value is None or not isinstance(value, str):
        raise ValueError(f"{field_name} ist erforderlich")
    
    value = value.strip().lower()
    
    if len(value) == 0:
        raise ValueError(f"{field_name} darf nicht leer sein")
    
    if len(value) > 320:  # RFC 5321 Maximum
        raise ValueError(f"{field_name} ist zu lang (max. 320 Zeichen)")
    
    # Simple email pattern check
    if "@" not in value:
        raise ValueError(f"{field_name} hat kein gültiges E-Mail-Format")
    
    local_part, domain = value.rsplit("@", 1)
    
    if not local_part or not domain:
        raise ValueError(f"{field_name} hat kein gültiges E-Mail-Format")
    
    if "." not in domain:
        raise ValueError(f"{field_name} hat kein gültiges E-Mail-Format")
    
    return value
