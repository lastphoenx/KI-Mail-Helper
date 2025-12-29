"""
IMAP Connection Diagnostics (Phase 11.5a)

Diagnostics für IMAP-Verbindungen:
- Connection Testing
- Capability Detection
- Namespace Discovery
- Folder Access Testing

Test-First Development: Implementation folgt Tests!
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

logger = logging.getLogger(__name__)


class IMAPDiagnostics:
    """
    IMAP Connection Diagnostics Tool
    
    Testet IMAP-Verbindungen und sammelt Server-Informationen
    für besseres Error-Handling und Provider-spezifische Optimierungen.
    """
    
    def __init__(
        self,
        host: str,
        port: int = 993,
        username: str = "",
        password: str = "",
        timeout: float = 30.0,
        ssl: bool = True
    ):
        """
        Initialize IMAP Diagnostics
        
        Args:
            host: IMAP server hostname
            port: IMAP port (default 993 for SSL)
            username: Email username
            password: Email password
            timeout: Connection timeout in seconds
            ssl: Use SSL/TLS encryption
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.ssl = ssl
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test IMAP connection and authentication
        
        Returns:
            Dict with success status, message, and server welcome
        """
        try:
            with IMAPClient(
                host=self.host,
                port=self.port,
                ssl=self.ssl,
                timeout=self.timeout
            ) as client:
                # Try login
                client.login(self.username, self.password)
                
                return {
                    'success': True,
                    'message': 'Connection successful',
                    'welcome': client.welcome,
                    'host': self.host,
                    'port': self.port
                }
        
        except TimeoutError as e:
            logger.error(f"Connection timeout: {e}")
            return {
                'success': False,
                'error': f'Connection timeout: {str(e)}',
                'host': self.host,
                'port': self.port
            }
        
        except IMAPClientError as e:
            error_msg = str(e).lower()
            if 'auth' in error_msg or 'login' in error_msg:
                logger.error(f"Authentication failed: {e}")
                return {
                    'success': False,
                    'error': f'Authentication failed: {str(e)}'
                }
            else:
                logger.error(f"IMAP error: {e}")
                return {
                    'success': False,
                    'error': f'IMAP error: {str(e)}'
                }
        
        except Exception as e:
            logger.error(f"Connection failed: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': f'{type(e).__name__}: {str(e)}'
            }
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get server capabilities
        
        Returns:
            Dict with capabilities set and feature flags
        """
        try:
            with IMAPClient(
                host=self.host,
                port=self.port,
                ssl=self.ssl,
                timeout=self.timeout
            ) as client:
                client.login(self.username, self.password)
                
                # Get raw capabilities
                caps_raw = client.capabilities()
                
                # Convert bytes to strings
                caps_str = {cap.decode('utf-8') if isinstance(cap, bytes) else cap 
                           for cap in caps_raw}
                
                return {
                    'success': True,
                    'capabilities': sorted(caps_str),
                    'supports_idle': 'IDLE' in caps_str,
                    'supports_namespace': 'NAMESPACE' in caps_str,
                    'supports_id': 'ID' in caps_str,
                    'supports_children': 'CHILDREN' in caps_str,
                    'supports_uidplus': 'UIDPLUS' in caps_str,
                    'raw_capabilities': caps_raw
                }
        
        except Exception as e:
            logger.error(f"Failed to get capabilities: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': f'{type(e).__name__}: {str(e)}',
                'capabilities': [],
                'supports_idle': False,
                'supports_namespace': False
            }
    
    def get_namespace(self) -> Dict[str, Any]:
        """
        Get IMAP namespace information
        
        Returns:
            Dict with namespace info and delimiter
        """
        try:
            with IMAPClient(
                host=self.host,
                port=self.port,
                ssl=self.ssl,
                timeout=self.timeout
            ) as client:
                client.login(self.username, self.password)
                
                # Get namespace (may not be supported by all servers)
                ns = client.namespace()
                
                # Extract delimiter from personal namespace
                delimiter = '/'  # default
                if ns.personal and len(ns.personal) > 0:
                    delimiter = ns.personal[0][1] if len(ns.personal[0]) > 1 else '/'
                
                return {
                    'success': True,
                    'personal': ns.personal,
                    'other': ns.other,
                    'shared': ns.shared,
                    'delimiter': delimiter
                }
        
        except Exception as e:
            logger.warning(f"Namespace not supported or failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'personal': None,
                'other': None,
                'shared': None,
                'delimiter': '/'  # fallback
            }
    
    def test_folder_access(self, folder_name: str = 'INBOX') -> Dict[str, Any]:
        """
        Test access to a specific folder
        
        Args:
            folder_name: Folder to test (default: INBOX)
        
        Returns:
            Dict with folder info (exists, recent, flags)
        """
        try:
            with IMAPClient(
                host=self.host,
                port=self.port,
                ssl=self.ssl,
                timeout=self.timeout
            ) as client:
                client.login(self.username, self.password)
                
                # Try to select folder (readonly)
                folder_info = client.select_folder(folder_name, readonly=True)
                
                return {
                    'success': True,
                    'folder': folder_name,
                    'exists': folder_info.get(b'EXISTS', 0),
                    'recent': folder_info.get(b'RECENT', 0),
                    'uidvalidity': folder_info.get(b'UIDVALIDITY'),
                    'flags': folder_info.get(b'FLAGS', ()),
                    'raw_info': folder_info
                }
        
        except Exception as e:
            error_msg = str(e).lower()
            if 'not found' in error_msg or 'does not exist' in error_msg:
                logger.warning(f"Folder '{folder_name}' not found: {e}")
                return {
                    'success': False,
                    'error': f'Folder not found: {str(e)}',
                    'folder': folder_name
                }
            else:
                logger.error(f"Failed to access folder '{folder_name}': {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'folder': folder_name
                }
    
    def run_diagnostics(self) -> Dict[str, Any]:
        """
        Run complete diagnostics suite
        
        Returns:
            Dict with all diagnostic results
        """
        logger.info(f"Starting IMAP diagnostics for {self.host}:{self.port}")
        
        results = {
            'host': self.host,
            'port': self.port,
            'username': self.username
        }
        
        # Test 1: Connection
        logger.info("Test 1/4: Testing connection...")
        results['connection'] = self.test_connection()
        
        if not results['connection']['success']:
            results['summary'] = 'Connection failed - stopping diagnostics'
            return results
        
        # Test 2: Capabilities
        logger.info("Test 2/4: Getting capabilities...")
        results['capabilities'] = self.get_capabilities()
        
        # Test 3: Namespace
        logger.info("Test 3/4: Getting namespace...")
        results['namespace'] = self.get_namespace()
        
        # Test 4: INBOX access
        logger.info("Test 4/4: Testing INBOX access...")
        results['inbox_access'] = self.test_folder_access('INBOX')
        
        # Summary
        all_success = all([
            results['connection']['success'],
            results['capabilities']['success'],
            results['inbox_access']['success']
        ])
        
        results['summary'] = 'All tests passed' if all_success else 'Some tests failed'
        
        logger.info(f"Diagnostics complete: {results['summary']}")
        return results
