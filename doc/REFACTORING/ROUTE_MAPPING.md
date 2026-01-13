# ROUTE_MAPPING.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Exakte Zuordnung aller 123 Routes zu Blueprints

---

## 📊 ÜBERSICHT

| Blueprint | Prefix | Anzahl | 
|-----------|--------|--------|
| auth | - | 7 |
| emails | - | 5 |
| email_actions | - | 11 |
| accounts | - | 22 |
| tags | - | 2 |
| api | `/api` | 64 |
| rules | - | 10 |
| training | - | 1 |
| admin | - | 1 |
| **TOTAL** | | **123** |

---

## 🔐 auth_bp (7 Routes)

| Nr | Zeile | Route | Methods | Funktion | Blueprint-Route |
|----|-------|-------|---------|----------|-----------------|
| 1 | 647 | `/` | GET | `index` | `@auth_bp.route("/")` |
| 2 | 655 | `/login` | GET, POST | `login` | `@auth_bp.route("/login", ...)` |
| 3 | 765 | `/register` | GET, POST | `register` | `@auth_bp.route("/register", ...)` |
| 4 | 885 | `/2fa/verify` | GET, POST | `verify_2fa` | `@auth_bp.route("/2fa/verify", ...)` |
| 5 | 957 | `/logout` | GET | `logout` | `@auth_bp.route("/logout")` |
| 90 | 6497 | `/settings/2fa/setup` | GET, POST | `setup_2fa` | `@auth_bp.route("/settings/2fa/setup", ...)` |
| 91 | 6550 | `/settings/2fa/recovery-codes/regenerate` | POST | `regenerate_recovery_codes` | `@auth_bp.route(...)` |

---

## 📧 emails_bp (5 Routes)

| Nr | Zeile | Route | Methods | Funktion | Blueprint-Route |
|----|-------|-------|---------|----------|-----------------|
| 6 | 978 | `/dashboard` | GET | `dashboard` | `@emails_bp.route("/dashboard")` |
| 7 | 1123 | `/list` | GET | `list_view` | `@emails_bp.route("/list")` |
| 8 | 1465 | `/threads` | GET | `threads_view` | `@emails_bp.route("/threads")` |
| 9 | 1513 | `/email/<int:raw_email_id>` | GET | `email_detail` | `@emails_bp.route("/email/<int:raw_email_id>")` |
| 10 | 1693 | `/email/<int:raw_email_id>/render-html` | GET | `render_email_html` | `@emails_bp.route(...)` |

---

## ⚡ email_actions_bp (11 Routes)

| Nr | Zeile | Route | Methods | Funktion | Blueprint-Route |
|----|-------|-------|---------|----------|-----------------|
| 11 | 1796 | `/email/<int:raw_email_id>/done` | POST | `mark_done` | `@email_actions_bp.route(...)` |
| 12 | 1836 | `/email/<int:raw_email_id>/undo` | POST | `mark_undone` | `@email_actions_bp.route(...)` |
| 13 | 1874 | `/email/<int:raw_email_id>/reprocess` | POST | `reprocess_email` | `@email_actions_bp.route(...)` |
| 14 | 1995 | `/email/<int:raw_email_id>/optimize` | POST | `optimize_email` | `@email_actions_bp.route(...)` |
| 15 | 2126 | `/email/<int:raw_email_id>/correct` | POST | `correct_email` | `@email_actions_bp.route(...)` |
| 103 | 7527 | `/email/<int:raw_email_id>/delete` | POST | `delete_email` | `@email_actions_bp.route(...)` |
| 104 | 7621 | `/email/<int:raw_email_id>/move-trash` | POST | `move_email_to_trash` | `@email_actions_bp.route(...)` |
| 107 | 8031 | `/email/<int:raw_email_id>/move-to-folder` | POST | `move_email_to_folder` | `@email_actions_bp.route(...)` |
| 108 | 8181 | `/email/<int:raw_email_id>/mark-read` | POST | `mark_email_read` | `@email_actions_bp.route(...)` |
| 109 | 8274 | `/email/<int:raw_email_id>/toggle-read` | POST | `toggle_email_read` | `@email_actions_bp.route(...)` |
| 110 | 8381 | `/email/<int:raw_email_id>/mark-flag` | POST | `toggle_email_flag` | `@email_actions_bp.route(...)` |

---

## ⚙️ accounts_bp (22 Routes)

| Nr | Zeile | Route | Methods | Funktion |
|----|-------|-------|---------|----------|
| 20 | 2392 | `/reply-styles` | GET | `reply_styles_page` |
| 21 | 2399 | `/settings` | GET | `settings` |
| 22 | 2488 | `/mail-fetch-config` | GET | `mail_fetch_config` |
| 23 | 2526 | `/whitelist` | GET | `whitelist` |
| 24 | 2564 | `/ki-prio` | GET | `ki_prio` |
| 25 | 2571 | `/settings/fetch-config` | POST | `save_fetch_config` |
| 26 | 2667 | `/account/<int:account_id>/fetch-filters` | GET | `get_account_fetch_filters` |
| 86 | 6322 | `/settings/ai` | POST | `save_ai_preferences` |
| 87 | 6380 | `/settings/password` | GET, POST | `change_password` |
| 92 | 6583 | `/settings/mail-account/select-type` | GET | `select_account_type` |
| 93 | 6590 | `/settings/mail-account/google-setup` | GET, POST | `google_oauth_setup` |
| 94 | 6639 | `/settings/mail-account/google/callback` | GET | `google_oauth_callback` |
| 95 | 6809 | `/settings/mail-account/add` | GET, POST | `add_mail_account` |
| 96 | 6941 | `/settings/mail-account/<int:account_id>/edit` | GET, POST | `edit_mail_account` |
| 97 | 7155 | `/settings/mail-account/<int:account_id>/delete` | POST | `delete_mail_account` |
| 98 | 7190 | `/imap-diagnostics` | GET | `imap_diagnostics` |
| 100 | 7375 | `/mail-account/<int:account_id>/fetch` | POST | `fetch_mails` |
| 101 | 7447 | `/mail-account/<int:account_id>/purge` | POST | `purge_mail_account` |
| 102 | 7516 | `/jobs/<string:job_id>` | GET | `job_status` |
| 105 | 7763 | `/account/<int:account_id>/mail-count` | GET | `get_account_mail_count` |
| 106 | 7955 | `/account/<int:account_id>/folders` | GET | `get_account_folders` |
| 120 | 8985 | `/whitelist-imap-setup` | GET | `whitelist_imap_setup_page` |

---

## 🏷️ tags_bp (2 Routes)

| Nr | Zeile | Route | Methods | Funktion |
|----|-------|-------|---------|----------|
| 27 | 2725 | `/tags` | GET | `tags_view` |
| 39 | 3311 | `/tag-suggestions` | GET | `tag_suggestions_page` |

---

## 📏 rules_bp (10 Routes)

| Nr | Zeile | Route | Methods | Funktion |
|----|-------|-------|---------|----------|
| 68 | 4881 | `/rules` | GET | `rules_management` |
| 69 | 4908 | `/api/rules` | GET | `api_get_rules` |
| 70 | 4945 | `/api/rules` | POST | `api_create_rule` |
| 71 | 5010 | `/api/rules/<int:rule_id>` | PUT | `api_update_rule` |
| 72 | 5071 | `/api/rules/<int:rule_id>` | DELETE | `api_delete_rule` |
| 73 | 5107 | `/api/rules/<int:rule_id>/test` | POST | `api_test_rule` |
| 74 | 5207 | `/api/rules/apply` | POST | `api_apply_rules` |
| 75 | 5297 | `/api/rules/templates` | GET | `api_get_rule_templates` |
| 76 | 5323 | `/api/rules/templates/<template_name>` | POST | `api_create_rule_from_template` |
| 77 | 5382 | `/rules/execution-log` | GET | `rules_execution_log` |

**Hinweis:** rules_bp hat KEINEN Prefix. Die `/api/rules` Routes behalten ihren vollen Pfad!

---

## 🎓 training_bp (1 Route)

| Nr | Zeile | Route | Methods | Funktion |
|----|-------|-------|---------|----------|
| 17 | 2249 | `/retrain` | POST | `retrain_models` |

---

## 🔧 admin_bp (1 Route)

| Nr | Zeile | Route | Methods | Funktion |
|----|-------|-------|---------|----------|
| 123 | 9412 | `/api/debug-logger-status` | GET | `api_debug_logger_status` |

---

## 🌐 api_bp (64 Routes) - Prefix: `/api`

**WICHTIG:** api_bp hat `url_prefix="/api"`. Die Routes werden OHNE `/api` definiert!

| Nr | Zeile | Original Route | Blueprint Route (ohne /api) | Funktion |
|----|-------|----------------|---------------------------|----------|
| 16 | 2192 | `/api/email/<id>/flags` | `/email/<id>/flags` | `get_email_flags` |
| 18 | 2298 | `/api/training-stats` | `/training-stats` | `get_training_stats` |
| 19 | 2355 | `/api/models/<provider>` | `/models/<provider>` | `api_get_models_for_provider` |
| 28 | 2773 | `/api/accounts` | `/accounts` | `api_get_accounts` |
| 29 | 2818 | `/api/tags` | `/tags` | `api_get_tags` |
| 30 | 2848 | `/api/tags` | `/tags` | `api_create_tag` |
| 31 | 2891 | `/api/tags/<id>` | `/tags/<id>` | `api_update_tag` |
| 32 | 2932 | `/api/tags/<id>` | `/tags/<id>` | `api_delete_tag` |
| 33 | 2958 | `/api/emails/<id>/tags` | `/emails/<id>/tags` | `api_get_email_tags` |
| 34 | 3005 | `/api/emails/<id>/tag-suggestions` | `/emails/<id>/tag-suggestions` | `api_get_tag_suggestions` |
| 35 | 3107 | `/api/emails/<id>/tags` | `/emails/<id>/tags` | `api_assign_tag_to_email` |
| 36 | 3161 | `/api/emails/<id>/tags/<tag_id>` | `/emails/<id>/tags/<tag_id>` | `api_remove_tag_from_email` |
| 37 | 3206 | `/api/emails/<id>/tags/<tag_id>/reject` | `/emails/<id>/tags/<tag_id>/reject` | `api_reject_tag_for_email` |
| 38 | 3251 | `/api/tags/<id>/negative-examples` | `/tags/<id>/negative-examples` | `api_get_negative_examples` |
| 40 | 3343 | `/api/tag-suggestions` | `/tag-suggestions` | `api_get_pending_tag_suggestions` |
| 41 | 3376 | `/api/tag-suggestions/<id>/approve` | `/tag-suggestions/<id>/approve` | `api_approve_suggestion` |
| 42 | 3406 | `/api/tag-suggestions/<id>/reject` | `/tag-suggestions/<id>/reject` | `api_reject_suggestion` |
| 43 | 3425 | `/api/tag-suggestions/<id>/merge` | `/tag-suggestions/<id>/merge` | `api_merge_suggestion` |
| 44 | 3452 | `/api/tag-suggestions/batch-reject` | `/tag-suggestions/batch-reject` | `api_batch_reject_suggestions` |
| 45 | 3471 | `/api/tag-suggestions/batch-approve` | `/tag-suggestions/batch-approve` | `api_batch_approve_suggestions` |
| 46 | 3493 | `/api/tag-suggestions/settings` | `/tag-suggestions/settings` | `api_tag_suggestion_settings` |
| 47 | 3573 | `/api/phase-y/vip-senders` | `/phase-y/vip-senders` | `api_get_vip_senders` |
| 48 | 3607 | `/api/phase-y/vip-senders` | `/phase-y/vip-senders` | `api_create_vip_sender` |
| 49 | 3651 | `/api/phase-y/vip-senders/<id>` | `/phase-y/vip-senders/<id>` | `api_update_vip_sender` |
| 50 | 3684 | `/api/phase-y/vip-senders/<id>` | `/phase-y/vip-senders/<id>` | `api_delete_vip_sender` |
| 51 | 3711 | `/api/phase-y/keyword-sets` | `/phase-y/keyword-sets` | `api_get_keyword_sets` |
| 52 | 3764 | `/api/phase-y/keyword-sets` | `/phase-y/keyword-sets` | `api_save_keyword_set` |
| 53 | 3817 | `/api/phase-y/scoring-config` | `/phase-y/scoring-config` | `api_get_scoring_config` |
| 54 | 3859 | `/api/phase-y/scoring-config` | `/phase-y/scoring-config` | `api_save_scoring_config` |
| 55 | 3913 | `/api/phase-y/user-domains` | `/phase-y/user-domains` | `api_get_user_domains` |
| 56 | 3944 | `/api/phase-y/user-domains` | `/phase-y/user-domains` | `api_create_user_domain` |
| 57 | 3976 | `/api/phase-y/user-domains/<id>` | `/phase-y/user-domains/<id>` | `api_delete_user_domain` |
| 58 | 4006 | `/api/search/semantic` | `/search/semantic` | `api_semantic_search` |
| 59 | 4123 | `/api/emails/<id>/similar` | `/emails/<id>/similar` | `api_find_similar_emails` |
| 60 | 4231 | `/api/embeddings/stats` | `/embeddings/stats` | `api_embedding_stats` |
| 61 | 4276 | `/api/emails/<id>/generate-reply` | `/emails/<id>/generate-reply` | `api_generate_reply` |
| 62 | 4603 | `/api/reply-tones` | `/reply-tones` | `api_get_reply_tones` |
| 63 | 4633 | `/api/reply-styles` | `/reply-styles` | `api_get_reply_styles` |
| 64 | 4676 | `/api/reply-styles/<key>` | `/reply-styles/<key>` | `api_get_reply_style` |
| 65 | 4718 | `/api/reply-styles/<key>` | `/reply-styles/<key>` | `api_save_reply_style` |
| 66 | 4766 | `/api/reply-styles/<key>` | `/reply-styles/<key>` | `api_delete_reply_style_override` |
| 67 | 4799 | `/api/reply-styles/preview` | `/reply-styles/preview` | `api_preview_reply_style` |
| 78 | 5481 | `/api/account/<id>/smtp-status` | `/account/<id>/smtp-status` | `api_smtp_status` |
| 79 | 5539 | `/api/account/<id>/test-smtp` | `/account/<id>/test-smtp` | `api_test_smtp` |
| 80 | 5585 | `/api/emails/<id>/send-reply` | `/emails/<id>/send-reply` | `api_send_reply` |
| 81 | 5716 | `/api/account/<id>/send` | `/account/<id>/send` | `api_send_email` |
| 82 | 5844 | `/api/emails/<id>/generate-and-send` | `/emails/<id>/generate-and-send` | `api_generate_and_send_reply` |
| 83 | 5953 | `/api/emails/<id>/check-embedding-compatibility` | `/emails/<id>/check-embedding-compatibility` | `api_check_embedding_compatibility` |
| 84 | 6031 | `/api/emails/<id>/reprocess` | `/emails/<id>/reprocess` | `api_reprocess_email` |
| 85 | 6177 | `/api/batch-reprocess-embeddings` | `/batch-reprocess-embeddings` | `api_batch_reprocess_embeddings` |
| 88 | 6472 | `/api/available-models/<provider>` | `/available-models/<provider>` | `get_available_models` |
| 89 | 6485 | `/api/available-providers` | `/available-providers` | `get_available_providers` |
| 99 | 7243 | `/api/imap-diagnostics/<id>` | `/imap-diagnostics/<id>` | `api_imap_diagnostics` |
| 111 | 8508 | `/api/trusted-senders` | `/trusted-senders` | `api_list_trusted_senders` |
| 112 | 8554 | `/api/trusted-senders` | `/trusted-senders` | `api_add_trusted_sender` |
| 113 | 8619 | `/api/trusted-senders/<id>` | `/trusted-senders/<id>` | `api_update_trusted_sender` |
| 114 | 8689 | `/api/trusted-senders/<id>` | `/trusted-senders/<id>` | `api_delete_trusted_sender` |
| 115 | 8730 | `/api/settings/urgency-booster` | `/settings/urgency-booster` | `api_get_urgency_booster` |
| 116 | 8752 | `/api/settings/urgency-booster` | `/settings/urgency-booster` | `api_set_urgency_booster` |
| 117 | 8785 | `/api/accounts/urgency-booster-settings` | `/accounts/urgency-booster-settings` | `api_get_accounts_urgency_booster_settings` |
| 118 | 8834 | `/api/accounts/<id>/urgency-booster` | `/accounts/<id>/urgency-booster` | `api_set_account_urgency_booster` |
| 119 | 8909 | `/api/trusted-senders/suggestions` | `/trusted-senders/suggestions` | `api_get_trusted_senders_suggestions` |
| 121 | 9033 | `/api/scan-account-senders/<id>` | `/scan-account-senders/<id>` | `api_scan_account_senders` |
| 122 | 9154 | `/api/trusted-senders/bulk-add` | `/trusted-senders/bulk-add` | `api_bulk_add_trusted_senders` |

---

## ✅ VERIFIZIERUNG

```
auth:          7 Routes ✓
emails:        5 Routes ✓
email_actions: 11 Routes ✓
accounts:      22 Routes ✓
tags:          2 Routes ✓
api:           64 Routes ✓
rules:         10 Routes ✓
training:      1 Route ✓
admin:         1 Route ✓
─────────────────────────
TOTAL:         123 Routes ✓
```
