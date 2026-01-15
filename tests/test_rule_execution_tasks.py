"""
Unit Tests: Auto-Rules Celery Tasks (Tag 11)

Tests für rule_execution_tasks.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from celery.exceptions import Reject, Retry

from src.tasks.rule_execution_tasks import (
    apply_rules_to_emails,
    apply_rules_to_new_emails,
    test_rule
)


class TestApplyRulesToEmails:
    """Tests für apply_rules_to_emails Task"""
    
    @patch("src.tasks.rule_execution_tasks.get_session_factory")
    @patch("src.tasks.rule_execution_tasks.AutoRulesEngine")
    def test_apply_rules_success(self, mock_engine_class, mock_session_factory):
        """Test: Erfolgreiche Rule-Execution"""
        # Mock DB Session
        mock_session = MagicMock()
        mock_session_factory.return_value.return_value.__enter__.return_value = mock_session
        
        # Mock AutoRulesEngine
        mock_engine = Mock()
        mock_result = Mock(
            success=True,
            actions_executed=["tag_added", "priority_set"]
        )
        mock_engine.process_email.return_value = [mock_result]
        mock_engine_class.return_value = mock_engine
        
        # Mock Task
        mock_task = Mock()
        mock_task.request.id = "test-task-123"
        
        # Execute
        result = apply_rules_to_emails(
            mock_task,
            user_id=1,
            email_ids=[100, 101],
            master_key="test_key"
        )
        
        # Assertions
        assert result["emails_processed"] == 2
        assert result["rules_triggered"] == 2
        assert result["actions_executed"] == 4  # 2 rules * 2 actions
        assert result["errors"] == 0
        assert result["email_ids"] == [100, 101]
        
        # Verify Engine calls
        assert mock_engine.process_email.call_count == 2
        mock_engine.process_email.assert_any_call(100, dry_run=False)
        mock_engine.process_email.assert_any_call(101, dry_run=False)
    
    def test_apply_rules_invalid_params(self):
        """Test: Ungültige Parameter → Reject"""
        mock_task = Mock()
        
        with pytest.raises(Reject):
            apply_rules_to_emails(
                mock_task,
                user_id=0,  # Invalid
                email_ids=[],
                master_key="test_key"
            )
        
        with pytest.raises(Reject):
            apply_rules_to_emails(
                mock_task,
                user_id=1,
                email_ids=[100],
                master_key=""  # Missing
            )
    
    @patch("src.tasks.rule_execution_tasks.get_session_factory")
    @patch("src.tasks.rule_execution_tasks.AutoRulesEngine")
    def test_apply_rules_partial_errors(self, mock_engine_class, mock_session_factory):
        """Test: Teilweise Fehler bei Rule-Execution"""
        mock_session = MagicMock()
        mock_session_factory.return_value.return_value.__enter__.return_value = mock_session
        
        mock_engine = Mock()
        # Email 100: Success
        # Email 101: Error
        mock_engine.process_email.side_effect = [
            [Mock(success=True, actions_executed=["tag"])],
            Exception("Processing error")
        ]
        mock_engine_class.return_value = mock_engine
        
        mock_task = Mock()
        mock_task.request.id = "test-task-123"
        
        result = apply_rules_to_emails(
            mock_task,
            user_id=1,
            email_ids=[100, 101],
            master_key="test_key"
        )
        
        assert result["emails_processed"] == 1  # Only 100 succeeded
        assert result["errors"] == 1
    
    @patch("src.tasks.rule_execution_tasks.get_session_factory")
    def test_apply_rules_import_error(self, mock_session_factory):
        """Test: AutoRulesEngine Import-Fehler → Reject"""
        mock_session = MagicMock()
        mock_session_factory.return_value.return_value.__enter__.return_value = mock_session
        
        mock_task = Mock()
        
        with patch("src.tasks.rule_execution_tasks.AutoRulesEngine", side_effect=ImportError("No module")):
            with pytest.raises(Reject):
                apply_rules_to_emails(
                    mock_task,
                    user_id=1,
                    email_ids=[100],
                    master_key="test_key"
                )
    
    @patch("src.tasks.rule_execution_tasks.get_session_factory")
    @patch("src.tasks.rule_execution_tasks.AutoRulesEngine")
    def test_apply_rules_dry_run(self, mock_engine_class, mock_session_factory):
        """Test: Dry-Run Modus"""
        mock_session = MagicMock()
        mock_session_factory.return_value.return_value.__enter__.return_value = mock_session
        
        mock_engine = Mock()
        mock_result = Mock(
            success=True,
            actions_executed=["[DRY-RUN] Would execute..."]
        )
        mock_engine.process_email.return_value = [mock_result]
        mock_engine_class.return_value = mock_engine
        
        mock_task = Mock()
        mock_task.request.id = "test-task-123"
        
        result = apply_rules_to_emails(
            mock_task,
            user_id=1,
            email_ids=[100],
            master_key="test_key",
            dry_run=True
        )
        
        assert result["emails_processed"] == 1
        # Verify dry_run=True was passed
        mock_engine.process_email.assert_called_with(100, dry_run=True)


class TestApplyRulesToNewEmails:
    """Tests für apply_rules_to_new_emails Task (Batch)"""
    
    @patch("src.tasks.rule_execution_tasks.get_session_factory")
    @patch("src.tasks.rule_execution_tasks.AutoRulesEngine")
    def test_batch_processing_success(self, mock_engine_class, mock_session_factory):
        """Test: Batch-Verarbeitung neuer E-Mails"""
        mock_session = MagicMock()
        mock_session_factory.return_value.return_value.__enter__.return_value = mock_session
        
        mock_engine = Mock()
        mock_engine.process_new_emails.return_value = {
            "emails_checked": 50,
            "rules_triggered": 10,
            "actions_executed": 25,
            "errors": 0,
            "processed_email_ids": list(range(100, 150))
        }
        mock_engine_class.return_value = mock_engine
        
        mock_task = Mock()
        mock_task.request.id = "test-batch-123"
        
        result = apply_rules_to_new_emails(
            mock_task,
            user_id=1,
            master_key="test_key",
            since_minutes=60,
            limit=500
        )
        
        assert result["emails_checked"] == 50
        assert result["rules_triggered"] == 10
        assert result["actions_executed"] == 25
        
        # Verify Engine call
        mock_engine.process_new_emails.assert_called_once_with(
            since_minutes=60,
            limit=500
        )
    
    def test_batch_invalid_params(self):
        """Test: Ungültige Parameter → Reject"""
        mock_task = Mock()
        
        with pytest.raises(Reject):
            apply_rules_to_new_emails(
                mock_task,
                user_id=0,  # Invalid
                master_key="test_key"
            )


class TestRuleTesting:
    """Tests für test_rule Task (Dry-Run Preview)"""
    
    @patch("src.tasks.rule_execution_tasks.get_session_factory")
    @patch("src.tasks.rule_execution_tasks.AutoRulesEngine")
    def test_rule_test_matched(self, mock_engine_class, mock_session_factory):
        """Test: Regel matched E-Mail (Preview)"""
        mock_session = MagicMock()
        mock_session_factory.return_value.return_value.__enter__.return_value = mock_session
        
        mock_engine = Mock()
        mock_result = Mock(
            success=True,
            actions_executed=["[DRY-RUN] Would add tag 'Important'"],
            rule_name="VIP Sender Rule",
            rule_id=5
        )
        mock_engine.process_email.return_value = [mock_result]
        mock_engine_class.return_value = mock_engine
        
        mock_task = Mock()
        mock_task.request.id = "test-preview-123"
        
        result = test_rule(
            mock_task,
            user_id=1,
            rule_id=5,
            email_id=100,
            master_key="test_key"
        )
        
        assert result["matched"] is True
        assert result["rule_name"] == "VIP Sender Rule"
        assert result["rule_id"] == 5
        assert len(result["would_execute"]) > 0
    
    @patch("src.tasks.rule_execution_tasks.get_session_factory")
    @patch("src.tasks.rule_execution_tasks.AutoRulesEngine")
    def test_rule_test_not_matched(self, mock_engine_class, mock_session_factory):
        """Test: Regel matched NICHT"""
        mock_session = MagicMock()
        mock_session_factory.return_value.return_value.__enter__.return_value = mock_session
        
        mock_engine = Mock()
        mock_engine.process_email.return_value = []  # No match
        mock_engine_class.return_value = mock_engine
        
        mock_task = Mock()
        mock_task.request.id = "test-preview-123"
        
        result = test_rule(
            mock_task,
            user_id=1,
            rule_id=5,
            email_id=100,
            master_key="test_key"
        )
        
        assert result["matched"] is False
        assert result["would_execute"] == []
        assert result["rule_id"] == 5


# =============================================================================
# Integration Test Helpers
# =============================================================================
class TestRuleTaskIntegration:
    """Integration-Test-Helper (benötigt echte DB + Celery Worker)"""
    
    @pytest.mark.integration
    @pytest.mark.skip(reason="Benötigt laufenden Celery Worker + PostgreSQL")
    def test_real_rule_execution(self):
        """
        Echter Integration-Test mit Celery Worker.
        
        Führe aus mit:
        pytest tests/test_rule_execution_tasks.py::TestRuleTaskIntegration -m integration
        """
        from src.tasks.rule_execution_tasks import apply_rules_to_emails
        
        # Real task execution
        task = apply_rules_to_emails.delay(
            user_id=1,
            email_ids=[1],
            master_key="test_master_key"
        )
        
        # Wait for result
        result = task.get(timeout=10)
        
        assert "emails_processed" in result
        assert result["emails_processed"] >= 0
