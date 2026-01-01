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
import re
from typing import Dict, Any, List, Tuple, Optional, Union
from email.header import decode_header
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
        
        Raises:
            ValueError: If input validation fails
        """
        self._validate_inputs(host, port, username, timeout)
        
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.ssl = ssl
    
    def _validate_inputs(self, host: str, port: int, username: str, timeout: float) -> None:
        """
        Validate initialization inputs to prevent injection/misc issues
        
        Args:
            host: Hostname to validate
            port: Port number to validate
            username: Username to validate
            timeout: Timeout value to validate
        
        Raises:
            ValueError: If any input is invalid
        """
        if not isinstance(host, str) or not host or len(host) > 255:
            raise ValueError("Invalid hostname: must be non-empty string, max 255 chars")
        
        if not re.match(r'^[a-zA-Z0-9\-\.]+$', host):
            raise ValueError(f"Invalid hostname: contains invalid characters: {host}")
        
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(f"Invalid port: must be 1-65535, got {port}")
        
        if not isinstance(username, str) or len(username) > 1024:
            raise ValueError("Invalid username: must be string, max 1024 chars")
        
        if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 3600:
            raise ValueError(f"Invalid timeout: must be 0-3600 seconds, got {timeout}")
        
        logger.debug(f"Input validation passed for {host}:{port}")
    
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
            
            # Helper function to safely convert to int (handle lists and other types)
            def safe_int(value, default=0):
                if value is None:
                    return default
                if isinstance(value, (list, tuple)):
                    # Take first element if it's a list/tuple
                    value = value[0] if value else default
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return default
            
            return {
                'success': True,
                'folder': folder_name,
                'exists': safe_int(folder_info.get(b'EXISTS', 0)),
                'recent': safe_int(folder_info.get(b'RECENT', 0)),
                'unseen': safe_int(folder_info.get(b'UNSEEN', 0)),
                'uidvalidity': safe_int(folder_info.get(b'UIDVALIDITY'), None),
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
        Test flag detection on sample messages from all folders
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with flag statistics and sample messages (max 50 total)
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            # Get all folders first
            folders_raw = client.list_folders()
            folders = []
            for flags_raw, delimiter, folder_name in folders_raw:
                flags_str = [f.decode('ascii') if isinstance(f, bytes) else str(f) for f in flags_raw]
                # Skip Noselect folders
                if '\\Noselect' not in flags_str:
                    folders.append(folder_name)
            
            # Collect statistics across all folders
            unique_flags = set()
            stats = {
                'seen': 0,
                'unseen': 0,
                'flagged': 0,
                'answered': 0,
                'deleted': 0
            }
            
            sample_messages = []
            total_messages_all_folders = 0
            max_samples = 50  # Max 50 sample messages total
            folder_uidvalidities = {}  # Track UIDVALIDITY per folder
            
            for folder in folders:
                if len(sample_messages) >= max_samples:
                    break
                
                try:
                    # Select folder (readonly) and capture UIDVALIDITY
                    folder_info = client.select_folder(folder, readonly=True)
                    
                    # Extract UIDVALIDITY (important for UID consistency checks)
                    uidvalidity = folder_info.get(b'UIDVALIDITY')
                    if uidvalidity:
                        uidvalidity = int(uidvalidity[0]) if isinstance(uidvalidity, list) else int(uidvalidity)
                        folder_uidvalidities[folder] = uidvalidity
                    
                    # Search for all messages in this folder
                    all_msgs = client.search()
                    
                    if not all_msgs:
                        continue
                    
                    total_messages_all_folders += len(all_msgs)
                    
                    # Get samples from this folder (up to remaining quota)
                    remaining_quota = max_samples - len(sample_messages)
                    sample_count = min(len(all_msgs), remaining_quota)
                    sample_ids = sorted(all_msgs)[-sample_count:] if len(all_msgs) > sample_count else all_msgs
                    
                    # Fetch flags AND envelope for subject/message-id
                    flags_data = client.get_flags(sample_ids)
                    envelope_data = client.fetch(sample_ids, ['ENVELOPE'])
                    
                    for msg_id in sample_ids:
                        flags_raw = flags_data.get(msg_id, [])
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
                        
                        # Extract envelope data (subject + message-id)
                        envelope = envelope_data.get(msg_id, {}).get(b'ENVELOPE')
                        subject = '(no subject)'
                        message_id = '(no message-id)'
                        
                        if envelope:
                            # Subject is in envelope.subject (bytes)
                            if envelope.subject:
                                try:
                                    subject = envelope.subject.decode('utf-8', errors='replace')[:100]
                                except:
                                    subject = str(envelope.subject)[:100]
                            
                            # Message-ID is in envelope.message_id (bytes)
                            if envelope.message_id:
                                try:
                                    message_id = envelope.message_id.decode('ascii', errors='replace')
                                except:
                                    message_id = str(envelope.message_id)
                        
                        # Add sample message with extended info
                        sample_messages.append({
                            'uid': msg_id,
                            'folder': folder,
                            'uidvalidity': folder_uidvalidities.get(folder),
                            'message_id': message_id,
                            'subject': subject,
                            'flags': flags_str,
                            'is_seen': b'\\Seen' in flags_raw or '\\Seen' in flags_str,
                            'is_flagged': b'\\Flagged' in flags_raw or '\\Flagged' in flags_str,
                            'is_answered': b'\\Answered' in flags_raw or '\\Answered' in flags_str
                        })
                
                except Exception as folder_error:
                    logger.warning(f"Fehler beim Zugriff auf Ordner '{folder}': {folder_error}")
                    continue
            
            if not sample_messages:
                return {
                    'success': True,
                    'message': 'Keine Mails gefunden - alle Ordner leer',
                    'total_messages': 0,
                    'flags_found': [],
                    'statistics': stats,
                    'sample_messages': []
                }
            
            return {
                'success': True,
                'total_messages': total_messages_all_folders,
                'sample_count': len(sample_messages),
                'folder_uidvalidities': folder_uidvalidities,
                'folders_checked': len(folders),
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
            
            # Parse server info (robust format handling)
            server_info_str = self._parse_server_id(server_info)
            
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
    
    def _parse_server_id(self, server_info: Any) -> Dict[str, str]:
        """
        Parse server ID information (robust for various formats)
        
        RFC 2971 allows multiple formats:
        - Dict: {'name': 'Dovecot', ...}
        - Flat list: ['name', 'Dovecot', 'version', '2.3']
        - Nested tuples: [('name', 'Dovecot'), ('version', '2.3')]
        
        Args:
            server_info: Raw server ID response from IMAPClient
        
        Returns:
            Dict with string keys and values
        """
        result = {}
        
        if not server_info:
            return result
        
        try:
            if isinstance(server_info, dict):
                for key, value in server_info.items():
                    key_str = key.decode('ascii') if isinstance(key, bytes) else str(key)
                    val_str = value.decode('ascii') if isinstance(value, bytes) else str(value)
                    result[key_str] = val_str
            
            elif isinstance(server_info, (list, tuple)):
                if len(server_info) == 0:
                    return result
                
                if isinstance(server_info[0], (list, tuple)) and len(server_info[0]) == 2:
                    for item in server_info:
                        if isinstance(item, (list, tuple)) and len(item) == 2:
                            key, value = item
                            key_str = key.decode('ascii') if isinstance(key, bytes) else str(key)
                            val_str = value.decode('ascii') if isinstance(value, bytes) else str(value)
                            result[key_str] = val_str
                elif len(server_info) % 2 == 0:
                    for i in range(0, len(server_info), 2):
                        key = server_info[i]
                        value = server_info[i + 1]
                        key_str = key.decode('ascii') if isinstance(key, bytes) else str(key)
                        val_str = value.decode('ascii') if isinstance(value, bytes) else str(value)
                        result[key_str] = val_str
        
        except Exception as e:
            logger.debug(f"Error parsing server_id: {e}")
        
        return result
    
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
    
    def _decode_header(self, header_bytes: Union[bytes, str]) -> str:
        """
        Decode RFC 2047 encoded header (=?UTF-8?Q?...?= format)
        
        Args:
            header_bytes: Raw header value (bytes or string)
        
        Returns:
            Decoded string
        """
        
        try:
            if isinstance(header_bytes, bytes):
                header_str = header_bytes.decode('utf-8', errors='replace')
            else:
                header_str = header_bytes
            
            if '=?' in header_str:
                decoded_parts = []
                for part, charset in decode_header(header_str):
                    if isinstance(part, bytes):
                        decoded = part.decode(charset or 'utf-8', errors='replace')
                    else:
                        decoded = part
                    decoded_parts.append(decoded)
                return ''.join(decoded_parts)
            
            return header_str
        except Exception as e:
            logger.debug(f"Error decoding header: {e}")
            return header_bytes if isinstance(header_bytes, str) else header_bytes.decode('utf-8', errors='replace')
    
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
            
            # Sammle Server-Antwort für CAPABILITY Request
            server_responses = []
            
            # Zeige CAPABILITY-Antwort für jede Extension
            extensions_to_test = {
                'CONDSTORE': 'Änderungen seit letztem Sync (MODSEQ)',
                'UTF8': 'UTF-8 Unterstützung',
                'ENABLE': 'Extension-Aktivierung',
                'COMPRESS': 'Datenkompression',
                'STARTTLS': 'TLS-Upgrade'
            }
            
            supported = {}
            enabled = {}
            
            # ENABLE Extension muss vorhanden sein, sonst macht es keinen Sinn
            has_enable = 'ENABLE' in caps_str or any('ENABLE' in cap for cap in caps_str)
            
            for ext_name, ext_desc in extensions_to_test.items():
                has_cap = ext_name in caps_str or any(ext_name in cap for cap in caps_str)
                supported[ext_name] = {
                    'name': ext_desc,
                    'available': has_cap
                }
                
                # Sammle Capability-Check Response
                if has_cap:
                    matching_caps = [cap for cap in caps_str if ext_name in cap]
                    server_responses.append({
                        'command': f'CAPABILITY (Check für {ext_name})',
                        'response': f'✅ Gefunden: {", ".join(matching_caps) if matching_caps else ext_name}',
                        'status': 'OK'
                    })
                else:
                    server_responses.append({
                        'command': f'CAPABILITY (Check für {ext_name})',
                        'response': f'❌ Nicht in Server-Capabilities vorhanden',
                        'status': 'NOT_FOUND'
                    })
            
            return {
                'success': True,
                'extensions': {
                    ext_name: {
                        'name': supported[ext_name]['name'],
                        'available': supported[ext_name]['available'],
                        'enabled': enabled.get(ext_name, False)
                    }
                    for ext_name in supported.keys()
                },
                'total_available': sum(1 for ext in supported.values() if ext['available']),
                'total_enabled': sum(1 for v in enabled.values() if v),
                'message': f'{sum(1 for ext in supported.values() if ext["available"])} Extensions verfügbar, {sum(1 for v in enabled.values() if v)} aktiviert',
                'server_responses': server_responses,
                'total_commands': len(server_responses),
                'successful_commands': sum(1 for r in server_responses if r['status'] == 'OK')
            }
        
        except Exception as e:
            logger.warning(f"Failed to test extensions: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': str(e),
                'extensions': {},
                'total_available': 0,
                'total_enabled': 0
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def test_thread_support(self, client=None) -> Dict[str, Any]:
        """
        Test THREAD extension support (conversation threading)
        
        THREAD groups messages by conversation using RFC or ORDEREDSUBJECT algorithm.
        Optional extension - many servers don't support it.
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with THREAD support info
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            # Check if THREAD capability exists
            caps = client.capabilities()
            caps_str = {cap.decode('ascii') if isinstance(cap, bytes) else cap 
                       for cap in caps}
            
            # THREAD shows supported algorithms (e.g., "THREAD=REFERENCES")
            thread_support = None
            algorithms = []
            
            for cap in caps_str:
                if 'THREAD' in cap:
                    thread_support = cap
                    # Extract algorithm (THREAD=REFERENCES, THREAD=ORDEREDSUBJECT)
                    if '=' in cap:
                        algo = cap.split('=')[1]
                        algorithms.append(algo)
            
            # Try to get thread results if supported
            thread_results = {}
            if thread_support and algorithms:
                try:
                    # Use first supported algorithm
                    algo = algorithms[0].lower()
                    threads = client.thread(algorithm=algo, criteria=['ALL'])
                    
                    # Helper to flatten nested thread structures
                    def flatten_thread(thread):
                        """Recursively flatten thread structure to get all UIDs"""
                        uids = []
                        for item in thread:
                            if isinstance(item, (list, tuple)):
                                uids.extend(flatten_thread(item))
                            else:
                                uids.append(item)
                        return uids
                    
                    # Calculate statistics (threads can be nested tuples)
                    thread_count = len(threads) if threads else 0
                    total_messages = sum(len(flatten_thread(t)) for t in threads) if threads else 0
                    largest_thread = max(len(flatten_thread(t)) for t in threads) if threads else 0
                    avg_messages_per_thread = total_messages / thread_count if thread_count > 0 else 0
                    
                    # Get dates for timeline
                    oldest_date = None
                    newest_date = None
                    sample_threads_detailed = []
                    
                    if threads:
                        # Get envelopes for all thread UIDs to extract dates
                        # THREAD returns nested tuples like (1, 2, (3, 4)) for threads with replies
                        # We need to flatten them to get all UIDs
                        def flatten_thread(thread):
                            """Recursively flatten thread structure to get all UIDs"""
                            uids = []
                            for item in thread:
                                if isinstance(item, (list, tuple)):
                                    uids.extend(flatten_thread(item))
                                else:
                                    uids.append(item)
                            return uids
                        
                        all_uids = []
                        for thread in threads:
                            all_uids.extend(flatten_thread(thread))
                        
                        uid_to_envelope = {}
                        try:
                            if all_uids:
                                logger.debug(f"Fetching ENVELOPE for {len(all_uids)} UIDs from {len(threads)} threads")
                                envelopes = client.fetch(all_uids, ['ENVELOPE'])
                                uid_to_envelope = envelopes
                                logger.debug(f"Successfully fetched {len(uid_to_envelope)} envelopes")
                        except Exception as e:
                            logger.warning(f"Failed to fetch envelopes for threads: {type(e).__name__}: {e}")
                            uid_to_envelope = {}
                        
                        # Sample first 3 threads
                        for thread_idx, thread in enumerate(threads[:3]):
                            sample_thread = []
                            thread_dates = []
                            
                            # Flatten this thread to get UIDs
                            thread_uids = flatten_thread(thread)
                            
                            for uid in thread_uids[:3]:  # First 3 messages of each thread
                                date_str = '?'
                                subject = '(keine Details verfügbar)'
                                
                                # Fetch envelope data for this UID
                                envelope_data = uid_to_envelope.get(uid)
                                if envelope_data:
                                    env = envelope_data.get(b'ENVELOPE')
                                    if env:
                                        try:
                                            if env.date:
                                                date_str = str(env.date)
                                                if len(date_str) > 10:
                                                    date_str = date_str.split()[0] if ' ' in date_str else date_str[:10]
                                                thread_dates.append(date_str)
                                            else:
                                                date_str = '(kein Datum)'
                                            
                                            if env.subject:
                                                subject = self._decode_header(env.subject)
                                            else:
                                                subject = '(kein Betreff)'
                                        except Exception as e:
                                            logger.debug(f"Error extracting envelope data for UID {uid}: {e}")
                                            subject = '(Fehler beim Laden)'
                                    else:
                                        logger.debug(f"No ENVELOPE key for UID {uid}")
                                else:
                                    logger.debug(f"UID {uid} not found in envelope_data")
                                
                                sample_thread.append({
                                    'uid': uid,
                                    'date': date_str,
                                    'subject': subject
                                })
                            
                            if thread_dates:
                                thread_dates_sorted = sorted(thread_dates)
                                sample_threads_detailed.append({
                                    'thread_num': thread_idx + 1,
                                    'size': len(thread),
                                    'oldest': thread_dates_sorted[0] if thread_dates_sorted else None,
                                    'newest': thread_dates_sorted[-1] if thread_dates_sorted else None,
                                    'messages': sample_thread
                                })
                            else:
                                sample_threads_detailed.append({
                                    'thread_num': thread_idx + 1,
                                    'size': len(thread),
                                    'messages': sample_thread
                                })
                            
                            # Track overall timeline
                            for date in thread_dates:
                                if oldest_date is None or date < oldest_date:
                                    oldest_date = date
                                if newest_date is None or date > newest_date:
                                    newest_date = date
                    
                    thread_results = {
                        'algorithm_used': algo,
                        'thread_count': thread_count,
                        'total_messages_in_threads': total_messages,
                        'largest_thread': largest_thread,
                        'average_messages_per_thread': round(avg_messages_per_thread, 2),
                        'oldest_date': oldest_date,
                        'newest_date': newest_date,
                        'sample_threads': sample_threads_detailed
                    }
                except Exception as e:
                    logger.debug(f"Could not retrieve threads: {e}")
                    thread_results = {'error': str(e)}
            
            return {
                'success': bool(thread_support),
                'supported': bool(thread_support),
                'capability': thread_support or None,
                'algorithms': algorithms,
                'thread_results': thread_results if thread_support else {},
                'message': f'THREAD {thread_support.split("=")[1] if thread_support and "=" in thread_support else "not supported"}'
            }
        
        except Exception as e:
            logger.warning(f"Failed to test THREAD support: {type(e).__name__}: {e}")
            return {
                'success': False,
                'supported': False,
                'error': str(e),
                'algorithms': []
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def test_sort_support(self, client=None) -> Dict[str, Any]:
        """
        Test SORT extension support (server-side sorting)
        
        SORT enables client to request pre-sorted message UIDs by various criteria.
        Optional extension - many servers don't support it.
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with SORT support info
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            # Check if SORT capability exists
            caps = client.capabilities()
            caps_str = {cap.decode('ascii') if isinstance(cap, bytes) else cap 
                       for cap in caps}
            
            sort_support = any('SORT' in cap for cap in caps_str)
            sort_charsets = []
            
            if sort_support:
                # Try to extract supported charsets
                for cap in caps_str:
                    if cap.startswith('SORT='):
                        charsets = cap.split('=')[1].split()
                        sort_charsets = charsets
                        break
            
            # Test various sort criteria
            sort_results = {}
            if sort_support:
                test_criteria = [
                    ('DATE', 'Datum'),
                    ('FROM', 'Absender'),
                    ('SUBJECT', 'Betreff'),
                    ('SIZE', 'Größe'),
                    ('ARRIVAL', 'Ankunftszeit')
                ]
                
                for criteria, label in test_criteria:
                    try:
                        result = client.sort(criteria)
                        sort_results[criteria] = {
                            'label': label,
                            'success': bool(result),
                            'message_count': len(result) if result else 0
                        }
                    except Exception as e:
                        sort_results[criteria] = {
                            'label': label,
                            'success': False,
                            'error': str(e)
                        }
            
            working_criteria = sum(1 for r in sort_results.values() if r.get('success'))
            
            return {
                'success': sort_support,
                'supported': sort_support,
                'charsets': sort_charsets,
                'working_criteria': working_criteria,
                'sort_results': sort_results,
                'message': f'SORT supported: {working_criteria}/{len(sort_results)} criteria working'
            }
        
        except Exception as e:
            logger.warning(f"Failed to test SORT support: {type(e).__name__}: {e}")
            return {
                'success': False,
                'supported': False,
                'error': str(e),
                'sort_results': {}
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def test_envelope_parsing(self, client=None) -> Dict[str, Any]:
        """
        Test envelope parsing (structured RFC 822 header analysis)
        
        ENVELOPE provides structured header information:
        - From, To, Cc, Bcc addresses
        - Date, Subject
        - Message-ID, In-Reply-To
        - Content-Type information
        
        Args:
            client: Optional pre-existing IMAPClient connection
        
        Returns:
            Dict with envelope parsing results
        """
        should_close = False
        try:
            if client is None:
                client = self._get_connection(timeout=90.0)
                client.login(self.username, self.password)
                should_close = True
            
            # Select INBOX to get sample emails
            client.select_folder('INBOX', readonly=True)
            
            # Get a few recent messages
            messages = client.search()
            if not messages:
                return {
                    'success': False,
                    'error': 'No messages in INBOX',
                    'sample_count': 0
                }
            
            # Take last 3 messages (most recent)
            sample_ids = messages[-3:] if len(messages) >= 3 else messages
            
            # Fetch envelopes
            results = client.fetch(sample_ids, ['ENVELOPE'])
            
            envelopes = []
            for position, msg_id in enumerate(sample_ids):
                if msg_id not in results:
                    continue
                
                envelope = results[msg_id].get(b'ENVELOPE')
                if not envelope:
                    continue
                
                # Extract IDs
                message_id = envelope.message_id.decode('ascii', errors='ignore') if envelope.message_id else None
                in_reply_to = envelope.in_reply_to.decode('ascii', errors='ignore') if envelope.in_reply_to else None
                
                # Determine if this is a reply
                is_reply = in_reply_to is not None and in_reply_to.strip() != ''
                
                # Parse envelope data
                parsed = {
                    'uid': msg_id,
                    'position': position + 1,
                    'total_samples': len(sample_ids),
                    'date': str(envelope.date) if envelope.date else None,
                    'subject': self._decode_header(envelope.subject) if envelope.subject else '(no subject)',
                    'from': self._parse_address_list(envelope.from_),
                    'to': self._parse_address_list(envelope.to),
                    'cc': self._parse_address_list(envelope.cc),
                    'bcc': self._parse_address_list(envelope.bcc),
                    'reply_to': self._parse_address_list(envelope.reply_to),
                    'message_id': message_id,
                    'in_reply_to': in_reply_to,
                    'is_reply': is_reply,
                    'sender': self._parse_address_list(envelope.sender)
                }
                envelopes.append(parsed)
            
            return {
                'success': True,
                'sample_count': len(envelopes),
                'total_messages': len(messages),
                'envelopes': envelopes,
                'message': f'Envelope parsing successful ({len(envelopes)} samples)'
            }
        
        except Exception as e:
            logger.warning(f"Failed to test envelope parsing: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': str(e),
                'sample_count': 0
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def test_debug_info(self, client=None) -> Dict[str, Any]:
        """
        Debug mode: Capture IMAP commands and responses
        
        Args:
            client: Optional IMAP client (creates new if not provided)
        
        Returns:
            Dict with debug information and IMAP interactions
        """
        should_close = False
        try:
            if not client:
                should_close = True
                client = self._get_connection()
                client.login(self.username, self.password)
            
            debug_commands = []
            
            try:
                caps = client.capabilities()
                debug_commands.append({
                    'command': 'CAPABILITY',
                    'response': f'Returned {len(caps)} capabilities',
                    'status': 'OK'
                })
            except Exception as e:
                debug_commands.append({
                    'command': 'CAPABILITY',
                    'response': str(e)[:100],
                    'status': 'ERROR'
                })
            
            try:
                namespace = client.namespace()
                debug_commands.append({
                    'command': 'NAMESPACE',
                    'response': f'Personal: {namespace[0]}, Other: {namespace[1]}, Shared: {namespace[2]}',
                    'status': 'OK'
                })
            except Exception as e:
                debug_commands.append({
                    'command': 'NAMESPACE',
                    'response': str(e)[:100],
                    'status': 'ERROR'
                })
            
            try:
                folders = client.list_folders()
                debug_commands.append({
                    'command': 'LIST "" "*"',
                    'response': f'Found {len(folders)} folders',
                    'status': 'OK'
                })
            except Exception as e:
                debug_commands.append({
                    'command': 'LIST "" "*"',
                    'response': str(e)[:100],
                    'status': 'ERROR'
                })
            
            try:
                client.select_folder('INBOX')
                debug_commands.append({
                    'command': 'SELECT INBOX',
                    'response': 'Folder selected',
                    'status': 'OK'
                })
            except Exception as e:
                debug_commands.append({
                    'command': 'SELECT INBOX',
                    'response': str(e)[:100],
                    'status': 'ERROR'
                })
            
            try:
                status = client.folder_status('INBOX', ['MESSAGES', 'UNSEEN', 'RECENT'])
                debug_commands.append({
                    'command': 'STATUS INBOX (MESSAGES UNSEEN RECENT)',
                    'response': f'Messages: {status.get(b"MESSAGES")}, Unseen: {status.get(b"UNSEEN")}, Recent: {status.get(b"RECENT")}',
                    'status': 'OK'
                })
            except Exception as e:
                debug_commands.append({
                    'command': 'STATUS INBOX (MESSAGES UNSEEN RECENT)',
                    'response': str(e)[:100],
                    'status': 'ERROR'
                })
            
            try:
                has_id = 'ID' in (client.capabilities() or [])
                if has_id:
                    server_id = client.id_()
                    debug_commands.append({
                        'command': 'ID NIL',
                        'response': f'Server ID received ({len(server_id)} pairs)' if server_id else 'No ID info',
                        'status': 'OK'
                    })
            except Exception as e:
                debug_commands.append({
                    'command': 'ID NIL',
                    'response': str(e)[:100],
                    'status': 'ERROR'
                })
            
            return {
                'success': True,
                'debug_commands': debug_commands,
                'total_commands': len(debug_commands),
                'successful_commands': sum(1 for cmd in debug_commands if cmd['status'] == 'OK'),
                'message': f'Debug info collected ({len(debug_commands)} commands)'
            }
        
        except Exception as e:
            logger.warning(f"Failed to collect debug info: {type(e).__name__}: {e}")
            return {
                'success': False,
                'error': str(e),
                'debug_commands': []
            }
        
        finally:
            if should_close and client:
                try:
                    client.logout()
                except:
                    pass
    
    def _parse_address_list(self, addr_list) -> List[str]:
        """
        Parse IMAP address list to strings
        
        Args:
            addr_list: Tuple of Address namedtuples or None
        
        Returns:
            List of email addresses as strings
        """
        if not addr_list:
            return []
        
        addresses = []
        for addr in addr_list:
            try:
                if hasattr(addr, 'mailbox') and hasattr(addr, 'host'):
                    mailbox = addr.mailbox.decode('ascii', errors='ignore') if isinstance(addr.mailbox, bytes) else addr.mailbox
                    host = addr.host.decode('ascii', errors='ignore') if isinstance(addr.host, bytes) else addr.host
                    addresses.append(f"{mailbox}@{host}")
                else:
                    addresses.append(str(addr))
            except Exception as e:
                logger.debug(f"Could not parse address: {e}")
        
        return addresses
    
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
            logger.info("Test 5/11: Listing all folders...")
            results['folders'] = self.list_all_folders(client, subscribed_only=subscribed_only)
            
            # Test 6: Flag detection
            logger.info("Test 6/11: Testing flag detection...")
            results['flags'] = self.test_flags(client)
            
            # Test 7: Server ID & Provider Detection
            logger.info("Test 7/11: Getting server ID and detecting provider...")
            results['server_id'] = self.get_server_id(client)
            
            # Test 8: Extensions Support
            logger.info("Test 8/11: Testing extension support...")
            results['extensions'] = self.test_enable_extensions(client)
            
            # Test 9: THREAD Support (optional)
            logger.info("Test 9/11: Testing THREAD support...")
            results['thread'] = self.test_thread_support(client)
            
            # Test 10: SORT Support (optional)
            logger.info("Test 10/11: Testing SORT support...")
            results['sort'] = self.test_sort_support(client)
            
            # Test 11: Envelope Parsing
            logger.info("Test 11/11: Testing envelope parsing...")
            results['envelope'] = self.test_envelope_parsing(client)
            
            # Summary (server_id is optional, so always count as ok)
            all_success = all([
                results['connection']['success'],
                results['capabilities']['success'],
                results['inbox_access']['success'],
                results['folders']['success'],
                results['flags']['success'],
                results['extensions']['success'],
                results['envelope']['success']
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
                'extensions': {'success': False},
                'thread': {'success': False},
                'sort': {'success': False},
                'envelope': {'success': False}
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
                'extensions': {'success': False},
                'thread': {'success': False},
                'sort': {'success': False},
                'envelope': {'success': False}
            }
        
        finally:
            if client:
                try:
                    client.logout()
                except:
                    pass
