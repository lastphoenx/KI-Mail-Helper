# src/helpers/responses.py
"""Standardized API response helpers.

Extracted from 01_web_app.py lines 521-565.
"""

from flask import jsonify


def api_success(data=None, message=None, status_code=200):
    """Create a standardized success response.
    
    Args:
        data: Response data (optional)
        message: Success message (optional)
        status_code: HTTP status code (default: 200)
        
    Returns:
        Tuple of (JSON response, status code)
        
    Example:
        return api_success(data={"user_id": 123}, message="User created")
        # Returns: ({"success": True, "data": {"user_id": 123}, "message": "User created"}, 200)
    """
    response = {"success": True}
    
    if data is not None:
        response["data"] = data
    
    if message:
        response["message"] = message
    
    return jsonify(response), status_code


def api_error(message, code=None, status_code=400, details=None):
    """Create a standardized error response.
    
    Args:
        message: Error message (required)
        code: Error code like "VALIDATION_ERROR", "NOT_FOUND" (optional)
        status_code: HTTP status code (default: 400)
        details: Additional error details (optional)
        
    Returns:
        Tuple of (JSON response, status code)
        
    Example:
        return api_error("User not found", code="NOT_FOUND", status_code=404)
        # Returns: ({"success": False, "error": {"message": "User not found", "code": "NOT_FOUND"}}, 404)
    """
    error_data = {"message": message}
    
    if code:
        error_data["code"] = code
    
    if details:
        error_data["details"] = details
    
    return jsonify({"success": False, "error": error_data}), status_code
