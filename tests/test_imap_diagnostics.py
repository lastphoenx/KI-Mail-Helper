"""
Tests für IMAP Connection Diagnostics (Phase 11.5a)

Test-First Development: Tests BEVOR Implementation!
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.imap_diagnostics import IMAPDiagnostics


class TestIMAPDiagnosticsConnection:
    """Test Connection & Basic Info"""
    
    def test_connect_success(self):
        """Test erfolgreiche IMAP-Verbindung"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.login.return_value = b'LOGIN OK'
            mock_client.return_value.__enter__.return_value = mock_instance
            
            result = diagnostics.test_connection()
            
            assert result['success'] is True
            assert result['message'] == 'Connection successful'
            assert 'welcome' in result
            mock_instance.login.assert_called_once()
    
    def test_connect_failure_timeout(self):
        """Test Connection Timeout"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="test_password",
            timeout=5
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_client.side_effect = TimeoutError("Connection timeout")
            
            result = diagnostics.test_connection()
            
            assert result['success'] is False
            assert 'timeout' in result['error'].lower()
    
    def test_connect_failure_auth(self):
        """Test Authentication Failure"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="wrong_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.login.side_effect = Exception("Authentication failed")
            mock_client.return_value.__enter__.return_value = mock_instance
            
            result = diagnostics.test_connection()
            
            assert result['success'] is False
            assert 'authentication' in result['error'].lower()


class TestIMAPDiagnosticsCapabilities:
    """Test Server Capabilities Detection"""
    
    def test_get_capabilities(self):
        """Test Capabilities abrufen"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.capabilities.return_value = {
                b'IMAP4REV1', b'IDLE', b'NAMESPACE', b'ID',
                b'CHILDREN', b'UNSELECT', b'UIDPLUS'
            }
            mock_client.return_value.__enter__.return_value = mock_instance
            
            caps = diagnostics.get_capabilities()
            
            assert caps['success'] is True
            assert 'IDLE' in caps['capabilities']
            assert 'NAMESPACE' in caps['capabilities']
            assert caps['supports_idle'] is True
            assert caps['supports_namespace'] is True
    
    def test_capabilities_minimal_server(self):
        """Test Server mit minimalen Capabilities"""
        diagnostics = IMAPDiagnostics(
            host="imap.example.com",
            port=993,
            username="test@example.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.capabilities.return_value = {b'IMAP4REV1'}
            mock_client.return_value.__enter__.return_value = mock_instance
            
            caps = diagnostics.get_capabilities()
            
            assert caps['success'] is True
            assert caps['supports_idle'] is False
            assert caps['supports_namespace'] is False


class TestIMAPDiagnosticsNamespace:
    """Test Namespace Detection"""
    
    def test_get_namespace_gmail(self):
        """Test Namespace für Gmail"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            # Gmail namespace: personal=('', '/'), other=None, shared=None
            mock_namespace = Mock()
            mock_namespace.personal = [('', '/')]
            mock_namespace.other = None
            mock_namespace.shared = None
            mock_instance.namespace.return_value = mock_namespace
            mock_client.return_value.__enter__.return_value = mock_instance
            
            ns = diagnostics.get_namespace()
            
            assert ns['success'] is True
            assert ns['personal'] == [('', '/')]
            assert ns['delimiter'] == '/'
    
    def test_namespace_not_supported(self):
        """Test Server ohne NAMESPACE support"""
        diagnostics = IMAPDiagnostics(
            host="imap.example.com",
            port=993,
            username="test@example.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.namespace.side_effect = Exception("NAMESPACE not supported")
            mock_client.return_value.__enter__.return_value = mock_instance
            
            ns = diagnostics.get_namespace()
            
            assert ns['success'] is False
            assert ns['delimiter'] == '/'  # fallback


class TestIMAPDiagnosticsFolders:
    """Test Folder Access & Structure"""
    
    def test_test_folder_access_inbox(self):
        """Test INBOX Zugriff"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.select_folder.return_value = {
                b'EXISTS': 42,
                b'RECENT': 3,
                b'UIDVALIDITY': 123456,
                b'FLAGS': (b'\\Seen', b'\\Answered', b'\\Flagged', b'\\Deleted', b'\\Draft')
            }
            mock_client.return_value.__enter__.return_value = mock_instance
            
            access = diagnostics.test_folder_access('INBOX')
            
            assert access['success'] is True
            assert access['exists'] == 42
            assert access['recent'] == 3
            assert access['uidvalidity'] == 123456
            assert b'\\Seen' in access['flags']
    
    def test_test_folder_access_nonexistent(self):
        """Test Zugriff auf nicht-existierenden Ordner"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.select_folder.side_effect = Exception("Folder not found")
            mock_client.return_value.__enter__.return_value = mock_instance
            
            access = diagnostics.test_folder_access('NonExistent')
            
            assert access['success'] is False
            assert 'not found' in access['error'].lower()


class TestIMAPDiagnosticsComplete:
    """Test Complete Diagnostics Run"""
    
    def test_run_complete_diagnostics(self):
        """Test vollständiger Diagnose-Durchlauf"""
        diagnostics = IMAPDiagnostics(
            host="imap.gmail.com",
            port=993,
            username="test@gmail.com",
            password="test_password"
        )
        
        with patch('src.imap_diagnostics.IMAPClient') as mock_client:
            mock_instance = Mock()
            mock_instance.login.return_value = b'LOGIN OK'
            mock_instance.welcome = "* OK Gimap ready"
            mock_instance.capabilities.return_value = {b'IMAP4REV1', b'IDLE'}
            mock_namespace = Mock()
            mock_namespace.personal = [('', '/')]
            mock_instance.namespace.return_value = mock_namespace
            mock_instance.select_folder.return_value = {b'EXISTS': 10}
            mock_client.return_value.__enter__.return_value = mock_instance
            
            report = diagnostics.run_diagnostics()
            
            assert report['connection']['success'] is True
            assert report['capabilities']['success'] is True
            assert report['namespace']['success'] is True
            assert report['inbox_access']['success'] is True
            assert 'summary' in report
