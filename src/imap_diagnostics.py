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
    
    def _get_connection(self, timeout=None):
        """Helper: Create IMAP connection with optional custom timeout"""
        return IMAPClient(
            host=self.host,
            port=self.port,
            ssl=self.ssl,
            timeout=timeout or self.timeout
        )
    
    def test_connection(self, client=None) -> Dict[str, Any]:
        """
        Test IMAP connection and authentication
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with success status, message, and server welcome
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection()
                client.login(self.username, self.password)
                should_close = True
            
            welcome = client.welcome.decode('ascii', errors='replace') if isinstance(client.welcome, bytes) else str(client.welcome)
            
            return {
                'success': True,
                'message': 'Connection successful',
                'welcome': welcome,
                'host': self.host,
                'port': self.port,
                'ssl': self.ssl
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
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def get_capabilities(self, client=None) -> Dict[str, Any]:
        """
        Get server capabilities
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with capabilities set and feature flags
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection()
                client.login(self.username, self.password)
                should_close = True
            
            # Get raw capabilities
            caps_raw = client.capabilities()
            
            # Convert bytes to strings (capabilities are ASCII)
            caps_str = {cap.decode('ascii') if isinstance(cap, bytes) else cap 
                       for cap in caps_raw}
            
            return {
                'success': True,
                'capabilities': sorted(caps_str),
                'supports_idle': 'IDLE' in caps_str,
                'supports_namespace': 'NAMESPACE' in caps_str,
                'supports_id': 'ID' in caps_str,
                'supports_children': 'CHILDREN' in caps_str,
                'supports_uidplus': 'UIDPLUS' in caps_str
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
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def get_namespace(self, client=None) -> Dict[str, Any]:
        """
        Get IMAP namespace information
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with namespace info and delimiter
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection()
                client.login(self.username, self.password)
                should_close = True
            
            # Get namespace (may not be supported by all servers)
            ns = client.namespace()
            
            # Extract delimiter from personal namespace and convert bytes
            delimiter = '/'  # default
            if ns.personal and len(ns.personal) > 0:
                delim_raw = ns.personal[0][1] if len(ns.personal[0]) > 1 else '/'
                delimiter = delim_raw.decode('ascii') if isinstance(delim_raw, bytes) else str(delim_raw)
            
            # Convert namespace tuples to strings (decode bytes properly)
            def convert_ns(ns_data):
                if not ns_data:
                    return None
                result = []
                for item in ns_data:
                    converted = []
                    for val in item:
                        if isinstance(val, bytes):
                            converted.append(val.decode('utf-7'))  # IMAP uses modified UTF-7
                        else:
                            converted.append(val)
                    result.append(tuple(converted))
                return result
            
            return {
                'success': True,
                'personal': convert_ns(ns.personal),
                'other': convert_ns(ns.other),
                'shared': convert_ns(ns.shared),
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
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def test_folder_access(self, folder_name: str = 'INBOX', client=None) -> Dict[str, Any]:
        """
        Test access to a specific folder
        
        Args:
            folder_name: Folder to test (default: INBOX)
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with folder info (exists, recent, flags)
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection()
                client.login(self.username, self.password)
                should_close = True
            
            # Try to select folder (readonly)
            folder_info = client.select_folder(folder_name, readonly=True)
            
            # Convert flags bytes to strings for JSON serialization (gemäß IMAP Doku)
            flags_raw = folder_info.get(b'FLAGS', ())
            flags_str = [f.decode('ascii') if isinstance(f, bytes) else str(f) for f in flags_raw]
            
            return {
                'success': True,
                'folder': folder_name,
                'exists': int(folder_info.get(b'EXISTS', 0)),
                'recent': int(folder_info.get(b'RECENT', 0)),
                'unseen': int(folder_info.get(b'UNSEEN', 0)) if folder_info.get(b'UNSEEN') else 0,
                'uidvalidity': int(folder_info.get(b'UIDVALIDITY', 0)) if folder_info.get(b'UIDVALIDITY') else None,
                'flags': flags_str
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
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def list_all_folders(self, client=None, subscribed_only=False) -> Dict[str, Any]:
        """
        List folders with their flags and delimiters
        
        Args:
            client: Optional pre-existing IMAPClient connection
            subscribed_only: If True, list only subscribed folders. If False, list all folders.
        
        Returns:
            Dict with folder list and metadata
        """
        should_close = False
        list_type = 'all'
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            if subscribed_only:
                folders_raw = client.list_sub_folders()
                list_type = 'subscribed'
            else:
                folders_raw = client.list_folders()
                list_type = 'all'
            
            folders = []
            
            for flags_raw, delimiter, folder_name in folders_raw:
                flags_str = [f.decode('ascii') if isinstance(f, bytes) else str(f) 
                            for f in flags_raw]
                
                folders.append({
                    'name': folder_name,
                    'delimiter': delimiter if isinstance(delimiter, str) else (
                        delimiter.decode('ascii') if isinstance(delimiter, bytes) else str(delimiter)
                    ),
                    'flags': flags_str,
                    'has_children': '\\HasChildren' in flags_str,
                    'has_no_children': '\\HasNoChildren' in flags_str,
                    'noselect': '\\Noselect' in flags_str,
                    'is_drafts': '\\Drafts' in flags_str,
                    'is_sent': '\\Sent' in flags_str,
                    'is_trash': '\\Trash' in flags_str,
                    'is_junk': '\\Junk' in flags_str,
                    'is_archive': '\\Archive' in flags_str
                })
            
            return {
                'success': True,
                'folders': folders,
                'total': len(folders),
                'delimiter': folders[0]['delimiter'] if folders else '/',
                'subscribed_only': subscribed_only,
                'list_type': list_type
            }
        
        except TimeoutError as e:
            logger.warning(f"Folder listing timeout (server may have many folders): {e}")
            return {
                'success': False,
                'error': 'Timeout beim Laden der Ordner - Server hat möglicherweise sehr viele Ordner',
                'folders': [],
                'total': 0,
                'subscribed_only': subscribed_only,
                'list_type': list_type if subscribed_only else 'all'
            }
        except Exception as e:
            logger.error(f"Failed to list folders: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': str(e),
                'folders': [],
                'total': 0,
                'subscribed_only': subscribed_only,
                'list_type': list_type if subscribed_only else 'all'
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def test_flags(self, client=None) -> Dict[str, Any]:
        """
        Test flag detection on sample messages from INBOX
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with flag statistics and sample messages
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            # Select INBOX
            client.select_folder('INBOX', readonly=True)
            
            # Search for all messages
            all_msgs = client.search()
            
            if not all_msgs:
                return {
                    'success': True,
                    'message': 'INBOX is empty - no messages to test',
                    'total_messages': 0,
                    'flags_found': [],
                    'statistics': {
                        'seen': 0,
                        'unseen': 0,
                        'flagged': 0,
                        'answered': 0,
                        'deleted': 0
                    },
                    'sample_messages': []
                }
            
            # Get the last 10 messages (most recent)
            sample_ids = sorted(all_msgs)[-10:] if len(all_msgs) > 10 else all_msgs
            
            # Fetch flags for these messages
            flags_data = client.get_flags(sample_ids)
            
            # Collect statistics
            unique_flags = set()
            stats = {
                'seen': 0,
                'unseen': 0,
                'flagged': 0,
                'answered': 0,
                'deleted': 0
            }
            
            sample_messages = []
            
            for msg_id, flags_raw in flags_data.items():
                # Decode flags from bytes to strings
                flags_str = [f.decode('ascii') if isinstance(f, bytes) else str(f) 
                           for f in flags_raw]
                
                # Collect unique flags
                for flag in flags_str:
                    unique_flags.add(flag)
                
                # Update statistics
                if b'\\Seen' in flags_raw or '\\Seen' in flags_str:
                    stats['seen'] += 1
                else:
                    stats['unseen'] += 1
                
                if b'\\Flagged' in flags_raw or '\\Flagged' in flags_str:
                    stats['flagged'] += 1
                
                if b'\\Answered' in flags_raw or '\\Answered' in flags_str:
                    stats['answered'] += 1
                
                if b'\\Deleted' in flags_raw or '\\Deleted' in flags_str:
                    stats['deleted'] += 1
                
                # Add sample message
                sample_messages.append({
                    'uid': msg_id,
                    'flags': flags_str,
                    'is_seen': b'\\Seen' in flags_raw or '\\Seen' in flags_str,
                    'is_flagged': b'\\Flagged' in flags_raw or '\\Flagged' in flags_str,
                    'is_answered': b'\\Answered' in flags_raw or '\\Answered' in flags_str
                })
            
            return {
                'success': True,
                'total_messages': len(all_msgs),
                'sample_count': len(sample_ids),
                'flags_found': sorted(unique_flags),
                'statistics': stats,
                'sample_messages': sample_messages,
                'has_custom_flags': any(flag for flag in unique_flags if not flag.startswith('\\'))
            }
        
        except Exception as e:
            logger.error(f"Failed to test flags: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_messages': 0,
                'flags_found': [],
                'statistics': {},
                'sample_messages': []
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def get_server_id(self, client=None) -> Dict[str, Any]:
        """
        Get server implementation details via ID extension
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with server info and detected provider
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            # Get server ID info
            server_info = client.id_({'name': 'KI-Mail-Helper', 'version': '1.0'})
            
            # Convert bytes to strings (handle both dict and tuple returns)
            server_info_str = {}
            if server_info:
                if isinstance(server_info, dict):
                    for key, value in server_info.items():
                        key_str = key.decode('ascii') if isinstance(key, bytes) else str(key)
                        val_str = value.decode('ascii') if isinstance(value, bytes) else str(value)
                        server_info_str[key_str] = val_str
                elif isinstance(server_info, (list, tuple)):
                    for i in range(0, len(server_info), 2):
                        if i + 1 < len(server_info):
                            key = server_info[i]
                            value = server_info[i + 1]
                            key_str = key.decode('ascii') if isinstance(key, bytes) else str(key)
                            val_str = value.decode('ascii') if isinstance(value, bytes) else str(value)
                            server_info_str[key_str] = val_str
            
            # Detect provider based on server info and host
            provider = self._detect_provider(server_info_str)
            
            return {
                'success': True,
                'server_info': server_info_str,
                'provider': provider,
                'host': self.host,
                'message': f'Server-ID erfolgreich abgerufen: {provider}'
            }
        
        except Exception as e:
            logger.warning(f"Server-ID nicht verfügbar (nicht kritisch): {type(e).__name__}: {e}")
            # Fallback: detect from host only
            provider = self._detect_provider({})
            return {
                'success': False,
                'error': 'ID-Extension nicht unterstützt (nicht kritisch)',
                'server_info': {},
                'provider': provider,
                'host': self.host
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def _detect_provider(self, server_info: Dict[str, str]) -> str:
        """
        Detect email provider based on server info and hostname
        
        Args:
            server_info: Server ID information dict
        
        Returns:
            Provider name string
        """
        # Check server_info first (most reliable)
        if server_info:
            name = server_info.get('name', '').lower()
            
            if 'dovecot' in name:
                return 'Dovecot (GMX/T-Online)'
            elif 'gmail' in name or 'google' in name:
                return 'Gmail (Google)'
            elif 'outlook' in name or 'microsoft' in name:
                return 'Outlook (Microsoft)'
            elif 'yahoo' in name:
                return 'Yahoo Mail'
            elif 'fastmail' in name:
                return 'FastMail'
            elif 'proton' in name:
                return 'ProtonMail'
        
        # Fallback: detect from host
        host_lower = self.host.lower()
        
        if 'gmx' in host_lower or 'imap.gmx' in host_lower:
            return 'GMX (Dovecot)'
        elif 'gmail' in host_lower or 'google' in host_lower:
            return 'Gmail'
        elif 'imap.mail.yahoo' in host_lower:
            return 'Yahoo Mail'
        elif 'outlook' in host_lower or 'hotmail' in host_lower:
            return 'Outlook/Hotmail'
        elif 'mail.proton' in host_lower:
            return 'ProtonMail'
        elif 'fastmail' in host_lower:
            return 'FastMail'
        elif 't-online' in host_lower:
            return 'T-Online'
        else:
            return 'Unknown Provider'
    
    def test_enable_extensions(self, client=None) -> Dict[str, Any]:
        """
        Test and enable optional server extensions
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with extension support info
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            # Get current capabilities
            caps = client.capabilities()
            caps_str = {cap.decode('ascii') if isinstance(cap, bytes) else cap 
                       for cap in caps}
            
            extensions_to_test = {
                'CONDSTORE': 'Änderungen seit letztem Sync (MODSEQ)',
                'UTF8': 'UTF-8 Unterstützung',
                'ENABLE': 'Extension-Aktivierung',
                'COMPRESS': 'Datenkompression',
                'STARTTLS': 'TLS-Upgrade'
            }
            
            supported = {}
            enabled = {}
            
            for ext_name, ext_desc in extensions_to_test.items():
                has_cap = ext_name in caps_str or any(ext_name in cap for cap in caps_str)
                supported[ext_name] = {
                    'name': ext_desc,
                    'available': has_cap
                }
                
                # Try to enable CONDSTORE (safe to enable)
                if ext_name == 'CONDSTORE' and has_cap:
                    try:
                        result = client.enable('CONDSTORE')
                        enabled[ext_name] = bool(result)
                    except Exception as e:
                        logger.debug(f"Could not enable {ext_name}: {e}")
                        enabled[ext_name] = False
            
            return {
                'success': True,
                'supported_extensions': supported,
                'enabled': enabled,
                'total_available': sum(1 for ext in supported.values() if ext['available']),
                'message': f'{sum(1 for ext in supported.values() if ext["available"])} Extensions verfügbar'
            }
        
        except Exception as e:
            logger.warning(f"Failed to test extensions: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': str(e),
                'supported_extensions': {},
                'enabled': {}
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def run_diagnostics(self, subscribed_only: bool = False) -> Dict[str, Any]:
        """
        Run complete diagnostics suite using a single connection
        
        Args:
            subscribed_only: If True, list only subscribed folders. If False, list all folders.
        
        Returns:
            Dict with all diagnostic results
        """
        logger.info(f"Starting IMAP diagnostics for {self.host}:{self.port}")
        
        results = {
            'host': self.host,
            'port': self.port,
            'username': self.username
        }
        
        client = None
        try:
            # Create single connection for all tests (90s timeout for comprehensive diagnostics)
            client = self._get_connection(timeout=90.0)
            client.login(self.username, self.password)
            
            # Test 1: Connection
            logger.info("Test 1/8: Testing connection...")
            results['connection'] = self.test_connection(client)
            
            if not results['connection']['success']:
                results['summary'] = 'Connection failed - stopping diagnostics'
                return results
            
            # Test 2: Capabilities
            logger.info("Test 2/8: Getting capabilities...")
            results['capabilities'] = self.get_capabilities(client)
            
            # Test 3: Namespace
            logger.info("Test 3/8: Getting namespace...")
            results['namespace'] = self.get_namespace(client)
            
            # Test 4: INBOX access
            logger.info("Test 4/8: Testing INBOX access...")
            results['inbox_access'] = self.test_folder_access('INBOX', client)
            
            # Test 5: Folder listing
            logger.info("Test 5/8: Listing all folders...")
            results['folders'] = self.list_all_folders(client, subscribed_only=subscribed_only)
            
            # Test 6: Flag detection
            logger.info("Test 6/8: Testing flag detection...")
            results['flags'] = self.test_flags(client)
            
            # Test 7: Server ID & Provider Detection
            logger.info("Test 7/8: Getting server ID and detecting provider...")
            results['server_id'] = self.get_server_id(client)
            
            # Test 8: Extensions Support
            logger.info("Test 8/8: Testing extension support...")
            results['extensions'] = self.test_enable_extensions(client)
            
            # Summary (server_id is optional, so always count as ok)
            all_success = all([
                results['connection']['success'],
                results['capabilities']['success'],
                results['inbox_access']['success'],
                results['folders']['success'],
                results['flags']['success'],
                results['extensions']['success']
            ])
            
            results['summary'] = 'All tests passed' if all_success else 'Some tests failed'
            
            logger.info(f"Diagnostics complete: {results['summary']}")
            return results
        
        except TimeoutError as e:
            logger.error(f"Diagnostics timeout: {e}")
            return {
                'success': False,
                'summary': 'SSL Handshake Timeout - Server antwortet nicht schnell genug',
                'connection': {'success': False, 'error': str(e)},
                'capabilities': {'success': False},
                'namespace': {'success': False},
                'inbox_access': {'success': False},
                'folders': {'success': False},
                'flags': {'success': False},
                'server_id': {'success': False},
                'extensions': {'success': False}
            }
        
        except Exception as e:
            logger.error(f"Unexpected error in diagnostics: {type(e).__name__}: {e}")
            return {
                'success': False,
                'summary': f'Fehler: {type(e).__name__}',
                'connection': {'success': False, 'error': str(e)},
                'capabilities': {'success': False},
                'namespace': {'success': False},
                'inbox_access': {'success': False},
                'folders': {'success': False},
                'flags': {'success': False},
                'server_id': {'success': False},
                'extensions': {'success': False}
            }
        
        finally:
            if client:
                try:
                    client.logout()
                except:
                    pass
