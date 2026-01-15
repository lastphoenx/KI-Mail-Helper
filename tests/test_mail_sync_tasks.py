"""Unit Tests für Mail Sync Celery Tasks

Tests für src/tasks/mail_sync_tasks.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.tasks.mail_sync_tasks import sync_user_emails, sync_all_accounts


class TestSyncUserEmailsTask:
    """Tests für sync_user_emails Celery Task"""
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    @patch('src.tasks.mail_sync_tasks.get_mail_account')
    def test_sync_success(self, mock_get_account, mock_get_user, mock_get_session):
        """Test: Erfolgreiche Email-Synchronisation"""
        # Setup mocks
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        mock_user = Mock(id=1)
        mock_get_user.return_value = mock_user
        
        mock_account = Mock(
            id=2,
            email="test@example.com",
            fetch_filters=[{"folder": "INBOX"}],
            initial_sync_done=False
        )
        mock_get_account.return_value = mock_account
        
        # Mock encryption
        with patch('src.tasks.mail_sync_tasks.decrypt_imap_credentials') as mock_decrypt:
            mock_decrypt.return_value = {
                'imap_server': 'imap.example.com',
                'imap_port': 993,
                'use_ssl': True,
                'username': 'test@example.com',
                'password': 'secret'
            }
            
            # Mock IMAP connection
            with patch('src.tasks.mail_sync_tasks.IMAPClient') as mock_imap:
                mock_conn = Mock()
                mock_imap.return_value = mock_conn
                
                # Mock MailSyncServiceV2
                with patch('src.tasks.mail_sync_tasks.MailSyncServiceV2') as mock_service_class:
                    mock_service = Mock()
                    mock_service_class.return_value = mock_service
                    
                    # Mock sync stats
                    mock_stats = Mock(
                        fetched=10,
                        raw_updated=5,
                        folders_scanned=1,
                        errors=[]
                    )
                    mock_service.sync_state_with_server.return_value = mock_stats
                    mock_service.fetch_missing_emails.return_value = 10
                    
                    # Execute task
                    result = sync_user_emails(
                        user_id=1,
                        account_id=2,
                        master_key="test_key_123",
                        max_emails=50
                    )
                    
                    # Assertions
                    assert result['status'] == 'success'
                    assert result['user_id'] == 1
                    assert result['account_id'] == 2
                    assert result['email_count'] == 10
                    
                    # Verify service was called
                    mock_service.sync_state_with_server.assert_called_once()
                    mock_service.fetch_missing_emails.assert_called_once()
                    mock_service.sync_raw_emails_with_state.assert_called_once()
                    
                    # Verify IMAP logout
                    mock_conn.logout.assert_called_once()
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    def test_sync_user_not_found(self, mock_get_user, mock_get_session):
        """Test: User nicht gefunden"""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_get_user.return_value = None
        
        result = sync_user_emails(
            user_id=999,
            account_id=1,
            master_key="test_key",
            max_emails=50
        )
        
        assert result['status'] == 'error'
        assert result['message'] == 'User not found'
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    @patch('src.tasks.mail_sync_tasks.get_mail_account')
    def test_sync_account_not_owned(self, mock_get_account, mock_get_user, mock_get_session):
        """Test: Account gehört nicht dem User"""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        mock_user = Mock(id=1)
        mock_get_user.return_value = mock_user
        
        mock_get_account.return_value = None  # Account nicht gefunden
        
        result = sync_user_emails(
            user_id=1,
            account_id=999,
            master_key="test_key",
            max_emails=50
        )
        
        assert result['status'] == 'error'
        assert result['message'] == 'Unauthorized'
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    @patch('src.tasks.mail_sync_tasks.get_mail_account')
    def test_sync_missing_master_key(self, mock_get_account, mock_get_user, mock_get_session):
        """Test: Master Key fehlt"""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        mock_user = Mock(id=1)
        mock_get_user.return_value = mock_user
        
        mock_account = Mock(id=2)
        mock_get_account.return_value = mock_account
        
        # Call without master_key (simulate missing from kwargs)
        result = sync_user_emails.apply(
            args=[1, 2],
            kwargs={'max_emails': 50}  # master_key fehlt!
        ).get()
        
        assert result['status'] == 'error'
        assert 'encryption key' in result['message'].lower()


class TestSyncAllAccountsTask:
    """Tests für sync_all_accounts Celery Task"""
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    @patch('src.tasks.mail_sync_tasks.sync_user_emails')
    def test_sync_all_success(self, mock_sync_task, mock_get_user, mock_get_session):
        """Test: Alle Accounts erfolgreich synced"""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # Mock user with 2 accounts
        mock_account1 = Mock(id=1, email="acc1@example.com")
        mock_account2 = Mock(id=2, email="acc2@example.com")
        mock_user = Mock(id=1, mail_accounts=[mock_account1, mock_account2])
        mock_get_user.return_value = mock_user
        
        # Mock sync results
        mock_result1 = Mock()
        mock_result1.get.return_value = {
            'status': 'success',
            'email_count': 10
        }
        mock_result2 = Mock()
        mock_result2.get.return_value = {
            'status': 'success',
            'email_count': 15
        }
        
        mock_sync_task.apply_async.side_effect = [mock_result1, mock_result2]
        
        # Execute
        result = sync_all_accounts(user_id=1, master_key="test_key")
        
        # Assertions
        assert result['status'] == 'success'
        assert result['user_id'] == 1
        assert result['accounts_synced'] == 2
        assert result['total_accounts'] == 2
        assert result['total_emails'] == 25
        
        # Verify both accounts were synced
        assert mock_sync_task.apply_async.call_count == 2
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    def test_sync_all_user_not_found(self, mock_get_user, mock_get_session):
        """Test: User nicht gefunden"""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        mock_get_user.return_value = None
        
        result = sync_all_accounts(user_id=999, master_key="test_key")
        
        assert result['status'] == 'error'
        assert result['message'] == 'User not found'
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    @patch('src.tasks.mail_sync_tasks.sync_user_emails')
    def test_sync_all_partial_failure(self, mock_sync_task, mock_get_user, mock_get_session):
        """Test: Ein Account schlägt fehl, andere erfolgreich"""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        # Mock user with 2 accounts
        mock_account1 = Mock(id=1, email="acc1@example.com")
        mock_account2 = Mock(id=2, email="acc2@example.com")
        mock_user = Mock(id=1, mail_accounts=[mock_account1, mock_account2])
        mock_get_user.return_value = mock_user
        
        # First succeeds, second fails
        mock_result1 = Mock()
        mock_result1.get.return_value = {'status': 'success', 'email_count': 10}
        
        mock_result2 = Mock()
        mock_result2.get.side_effect = Exception("IMAP connection failed")
        
        mock_sync_task.apply_async.side_effect = [mock_result1, mock_result2]
        
        # Execute
        result = sync_all_accounts(user_id=1, master_key="test_key")
        
        # Assertions: Sollte nicht komplett fehlschlagen
        assert result['status'] == 'success'
        assert result['accounts_synced'] == 1  # Nur 1 erfolgreich
        assert result['total_accounts'] == 2
        assert result['total_emails'] == 10


class TestTaskRetryMechanism:
    """Tests für Retry-Logik"""
    
    @patch('src.tasks.mail_sync_tasks.get_session')
    @patch('src.tasks.mail_sync_tasks.get_user')
    @patch('src.tasks.mail_sync_tasks.get_mail_account')
    def test_retry_on_failure(self, mock_get_account, mock_get_user, mock_get_session):
        """Test: Task wird bei Fehler retried"""
        mock_session = Mock()
        mock_get_session.return_value = mock_session
        
        mock_user = Mock(id=1)
        mock_get_user.return_value = mock_user
        
        mock_account = Mock(id=2)
        mock_get_account.return_value = mock_account
        
        # Mock decrypt to raise exception
        with patch('src.tasks.mail_sync_tasks.decrypt_imap_credentials') as mock_decrypt:
            mock_decrypt.side_effect = Exception("Decryption failed")
            
            # Execute task (should trigger retry)
            with pytest.raises(Exception):
                sync_user_emails(
                    user_id=1,
                    account_id=2,
                    master_key="test_key",
                    max_emails=50
                )
            
            # Note: In real Celery, retry() würde den Task neu queuen
            # In Unit-Test wird Exception geworfen


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
