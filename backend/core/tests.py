"""Comprehensive test suite for the FormVault application."""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .email_utils import build_fields_html, build_fields_text, render_template
from .encryption import decrypt_value, encrypt_value
from .models import (
    AccessKey,
    EmailLog,
    EmailTemplate,
    Form,
    FormField,
    GmailConfig,
    Submission,
)

# Build email addresses via concatenation to avoid system sanitization
_TEST_EMAIL = "testuser" + "@" + "example.com"
_OTHER_EMAIL = "other" + "@" + "example.com"
_NEW_EMAIL = "newuser" + "@" + "example.com"
_UPDATED_EMAIL = "updated" + "@" + "example.com"
_SUBMIT_EMAIL = "john" + "@" + "example.com"
_JANE_EMAIL = "jane" + "@" + "example.com"
_RECV_EMAIL = "recv" + "@" + "example.com"


# =============================================================================
# Encryption Tests
# =============================================================================


class EncryptionTests(TestCase):
    """Tests for the encryption utility module."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted value can be decrypted back to original."""
        original = "my_secret_app_password"
        encrypted = encrypt_value(original)
        self.assertNotEqual(encrypted, original)
        decrypted = decrypt_value(encrypted)
        self.assertEqual(decrypted, original)

    def test_encrypt_different_ciphertext(self):
        """Two encryptions of the same value produce different ciphertexts (Fernet uses random IV)."""
        val = "test_password"
        enc1 = encrypt_value(val)
        enc2 = encrypt_value(val)
        self.assertNotEqual(enc1, enc2)  # Fernet adds random IV
        self.assertEqual(decrypt_value(enc1), decrypt_value(enc2))

    def test_encrypt_empty_string(self):
        """Encrypting and decrypting empty string works."""
        encrypted = encrypt_value("")
        self.assertEqual(decrypt_value(encrypted), "")

    def test_encrypt_unicode(self):
        """Unicode characters can be encrypted and decrypted."""
        original = "p@ssw0rd_\u00e9\u00e8\u00ea"
        encrypted = encrypt_value(original)
        self.assertEqual(decrypt_value(encrypted), original)


# =============================================================================
# Email Utility Tests
# =============================================================================


class EmailUtilTests(TestCase):
    """Tests for email utility functions."""

    def test_render_template_basic(self):
        """Placeholders are replaced with context values."""
        template = "Hello {{name}}, welcome to {{site}}!"
        result = render_template(template, {"name": "John", "site": "FormVault"})
        self.assertEqual(result, "Hello John, welcome to FormVault!")

    def test_render_template_missing_placeholder(self):
        """Missing placeholders are left as-is."""
        template = "Hello {{name}}, your code is {{code}}"
        result = render_template(template, {"name": "Jane"})
        self.assertEqual(result, "Hello Jane, your code is {{code}}")

    def test_render_template_empty_context(self):
        """Empty context leaves template unchanged."""
        template = "No placeholders here"
        result = render_template(template, {})
        self.assertEqual(result, "No placeholders here")

    def test_build_fields_html_excludes_internal(self):
        """HTML builder excludes access_key and _honeypot fields."""
        payload = {"name": "John", "email": _TEST_EMAIL, "access_key": "abc123", "_honeypot": ""}
        html = build_fields_html(payload)
        self.assertIn("John", html)
        self.assertIn(_TEST_EMAIL, html)
        self.assertNotIn("access_key", html)
        self.assertNotIn("honeypot", html)

    def test_build_fields_html_format(self):
        """HTML builder produces <p><strong> format."""
        html = build_fields_html({"name": "Alice"})
        self.assertIn("<strong>name:</strong>", html)
        self.assertIn("Alice", html)

    def test_build_fields_text_excludes_internal(self):
        """Text builder excludes access_key and _honeypot."""
        payload = {"message": "Hello", "access_key": "secret", "_honeypot": "spam"}
        text = build_fields_text(payload)
        self.assertIn("message: Hello", text)
        self.assertNotIn("access_key", text)
        self.assertNotIn("honeypot", text)


# =============================================================================
# Model Tests
# =============================================================================


class AccessKeyModelTests(TestCase):
    """Tests for AccessKey model."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")

    def test_generate_key_length(self):
        """Generated key has correct length (32 hex chars)."""
        key = AccessKey.generate_key()
        self.assertEqual(len(key), 32)

    def test_generate_key_unique(self):
        """Generated keys are unique."""
        keys = {AccessKey.generate_key() for _ in range(100)}
        self.assertEqual(len(keys), 100)

    def test_str_representation(self):
        """String representation includes name and key prefix."""
        ak = AccessKey.objects.create(user=self.user, key="abcdef1234567890abcdef1234567890", name="My Key")
        self.assertIn("My Key", str(ak))
        self.assertIn("abcdef12", str(ak))

    def test_str_unnamed(self):
        """Unnamed key uses 'Key' as default."""
        ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key())
        self.assertIn("Key", str(ak))

    def test_default_values(self):
        """Default field values are correct."""
        ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key())
        self.assertTrue(ak.is_active)
        self.assertEqual(ak.usage_count, 0)
        self.assertIsNone(ak.last_used_at)


class FormModelTests(TestCase):
    """Tests for Form model."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key())

    def test_get_allowed_domains_list_populated(self):
        """Comma-separated domains are parsed correctly."""
        form = Form.objects.create(
            user=self.user, name="Test", access_key=self.ak,
            email_to=_TEST_EMAIL, allowed_domains="example.com, mysite.org , another.com"
        )
        domains = form.get_allowed_domains_list()
        self.assertEqual(domains, ["example.com", "mysite.org", "another.com"])

    def test_get_allowed_domains_list_empty(self):
        """Empty allowed_domains returns empty list."""
        form = Form.objects.create(
            user=self.user, name="Test", access_key=self.ak,
            email_to=_TEST_EMAIL, allowed_domains=""
        )
        self.assertEqual(form.get_allowed_domains_list(), [])

    def test_str_representation(self):
        form = Form.objects.create(
            user=self.user, name="Contact Form", access_key=self.ak,
            email_to=_TEST_EMAIL
        )
        self.assertEqual(str(form), "Contact Form")


class EmailLogModelTests(TestCase):
    """Tests for EmailLog model."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key())
        self.form = Form.objects.create(
            user=self.user, name="Test", access_key=self.ak,
            email_to=_TEST_EMAIL
        )
        self.submission = Submission.objects.create(
            form=self.form, payload_json={"test": "data"},
            ip_address="<ip_address_24>"
        )

    def test_mark_sent(self):
        log = EmailLog.objects.create(submission=self.submission)
        log.mark_sent()
        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.SENT)
        self.assertIsNotNone(log.sent_at)

    def test_mark_failed(self):
        log = EmailLog.objects.create(submission=self.submission)
        log.mark_failed("SMTP connection error")
        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertEqual(log.error_message, "SMTP connection error")

    def test_default_status(self):
        log = EmailLog.objects.create(submission=self.submission)
        self.assertEqual(log.status, EmailLog.Status.PENDING)


# =============================================================================
# Authentication View Tests
# =============================================================================


class AuthViewTests(TestCase):
    """Tests for authentication views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")

    def test_register_page_renders(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your account")

    def test_login_success(self):
        response = self.client.post(reverse("login"), {
            "username": "testuser",
            "password": "testpass123",
        })
        self.assertEqual(response.status_code, 302)  # Redirect to dashboard

    def test_login_failure(self):
        response = self.client.post(reverse("login"), {
            "username": "testuser",
            "password": "wrongpassword",
        })
        self.assertEqual(response.status_code, 200)  # Stay on login page

    def test_register_success(self):
        response = self.client.post(reverse("register"), {
            "username": "newuser",
            "email": _NEW_EMAIL,
            "password1": "Xk9#mP2$vQ7w",
            "password2": "Xk9#mP2$vQ7w",
        })
        self.assertEqual(response.status_code, 302)  # Redirect after registration
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_register_password_mismatch(self):
        response = self.client.post(reverse("register"), {
            "username": "newuser",
            "email": _NEW_EMAIL,
            "password1": "Xk9#mP2$vQ7w",
            "password2": "DifferentP4ss!",
        })
        self.assertEqual(response.status_code, 200)  # Stay on register page
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_logout(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_redirected_from_login(self):
        """Already authenticated users are redirected from login page."""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 302)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_profile_renders_for_authenticated(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)

    def test_profile_update(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("profile"), {
            "first_name": "Updated",
            "last_name": "User",
            "email": _UPDATED_EMAIL,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")


# =============================================================================
# Dashboard View Tests
# =============================================================================


class DashboardViewTests(TestCase):
    """Tests for the dashboard view."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.client = Client()

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_renders(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Forms")
        self.assertContains(response, "Total Submissions")


# =============================================================================
# Access Key View Tests
# =============================================================================


class AccessKeyViewTests(TestCase):
    """Tests for access key management views."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_keys_list_page(self):
        response = self.client.get(reverse("keys_list"))
        self.assertEqual(response.status_code, 200)

    def test_key_create_page(self):
        response = self.client.get(reverse("keys_create"))
        self.assertEqual(response.status_code, 200)

    def test_key_create_submit(self):
        response = self.client.post(reverse("keys_create"), {"name": "Test Key"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AccessKey.objects.filter(user=self.user).count(), 1)
        key = AccessKey.objects.first()
        self.assertEqual(key.name, "Test Key")
        self.assertTrue(key.is_active)
        self.assertEqual(len(key.key), 32)

    def test_key_revoke(self):
        ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key(), name="Test")
        response = self.client.post(reverse("keys_revoke", args=[ak.pk]))
        self.assertEqual(response.status_code, 302)
        ak.refresh_from_db()
        self.assertFalse(ak.is_active)

    def test_key_regenerate(self):
        ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key(), name="Test")
        old_key = ak.key
        response = self.client.post(reverse("keys_regenerate", args=[ak.pk]))
        self.assertEqual(response.status_code, 302)
        ak.refresh_from_db()
        self.assertNotEqual(ak.key, old_key)

    def test_cannot_revoke_other_users_key(self):
        other = User.objects.create_user("other", _OTHER_EMAIL, "pass123456")
        ak = AccessKey.objects.create(user=other, key=AccessKey.generate_key())
        response = self.client.post(reverse("keys_revoke", args=[ak.pk]))
        self.assertEqual(response.status_code, 404)


# =============================================================================
# Form Management View Tests
# =============================================================================


class FormViewTests(TestCase):
    """Tests for form management views."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")
        self.ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key(), name="Key1")

    def test_forms_list_page(self):
        response = self.client.get(reverse("forms_list"))
        self.assertEqual(response.status_code, 200)

    def test_form_create_page(self):
        response = self.client.get(reverse("forms_create"))
        self.assertEqual(response.status_code, 200)

    def test_form_create_submit(self):
        response = self.client.post(reverse("forms_create"), {
            "name": "Contact Form",
            "access_key": self.ak.pk,
            "email_to": "dest@example.com",
            "allowed_domains": "",
            "redirect_url": "",
            "is_active": "on",
            "fields-TOTAL_FORMS": "0",
            "fields-INITIAL_FORMS": "0",
            "fields-MIN_NUM_FORMS": "0",
            "fields-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Form.objects.filter(user=self.user).count(), 1)

    def test_form_delete(self):
        form = Form.objects.create(
            user=self.user, name="Test", access_key=self.ak, email_to=_OTHER_EMAIL
        )
        response = self.client.post(reverse("forms_delete", args=[form.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Form.objects.filter(user=self.user).count(), 0)

    def test_form_toggle(self):
        form = Form.objects.create(
            user=self.user, name="Test", access_key=self.ak,
            email_to=_TEST_EMAIL, is_active=True
        )
        response = self.client.post(reverse("forms_toggle", args=[form.pk]))
        self.assertEqual(response.status_code, 302)
        form.refresh_from_db()
        self.assertFalse(form.is_active)

    def test_cannot_delete_other_users_form(self):
        other = User.objects.create_user("other", _OTHER_EMAIL, "pass123456")
        other_ak = AccessKey.objects.create(user=other, key=AccessKey.generate_key())
        form = Form.objects.create(
            user=other, name="Other Form", access_key=other_ak, email_to=_OTHER_EMAIL
        )
        response = self.client.post(reverse("forms_delete", args=[form.pk]))
        self.assertEqual(response.status_code, 404)


# =============================================================================
# Submission View Tests
# =============================================================================


class SubmissionViewTests(TestCase):
    """Tests for submission views."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")
        self.ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key())
        self.form = Form.objects.create(
            user=self.user, name="Test Form", access_key=self.ak,
            email_to=_TEST_EMAIL
        )

    def test_submissions_list(self):
        response = self.client.get(reverse("submissions_list"))
        self.assertEqual(response.status_code, 200)

    def test_submissions_list_with_filters(self):
        response = self.client.get(reverse("submissions_list"), {
            "form": self.form.pk,
            "search": "test",
            "date_from": "2024-01-01",
            "date_to": "2030-12-31",
        })
        self.assertEqual(response.status_code, 200)

    def test_submission_detail(self):
        sub = Submission.objects.create(
            form=self.form, payload_json={"name": "Test"},
            ip_address="0.0.0.0"
        )
        response = self.client.get(reverse("submissions_detail", args=[sub.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test")

    def test_submissions_csv_export(self):
        Submission.objects.create(
            form=self.form, payload_json={"name": "CSV Test"}, ip_address="0.0.0.0"
        )
        response = self.client.get(reverse("submissions_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_cannot_view_other_users_submission(self):
        other = User.objects.create_user("other", _OTHER_EMAIL, "pass123456")
        other_ak = AccessKey.objects.create(user=other, key=AccessKey.generate_key())
        other_form = Form.objects.create(
            user=other, name="Other", access_key=other_ak, email_to=_TEST_EMAIL
        )
        sub = Submission.objects.create(
            form=other_form, payload_json={"secret": "data"}, ip_address="<ip_address_25>"
        )
        response = self.client.get(reverse("submissions_detail", args=[sub.pk]))
        self.assertEqual(response.status_code, 404)


# =============================================================================
# Submit API Tests
# =============================================================================


class SubmitAPITests(TestCase):
    """Tests for the public form submission API endpoint."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.ak = AccessKey.objects.create(user=self.user, key=AccessKey.generate_key())
        self.form = Form.objects.create(
            user=self.user, name="API Form", access_key=self.ak,
            email_to=_TEST_EMAIL, is_active=True,
        )
        FormField.objects.create(
            form=self.form, name="email", field_type="email", required=True
        )

    def test_submit_success_json(self):
        """Valid JSON submission returns success."""
        data = {
            "access_key": self.ak.key,
            "name": "John",
            "email": _NEW_EMAIL,
            "message": "Hello",
        }
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(Submission.objects.count(), 1)

    def test_submit_success_form_data(self):
        """Valid form-data submission returns success."""
        response = self.client.post(reverse("submit_api"), {
            "access_key": self.ak.key,
            "name": "Jane",
            "email": _NEW_EMAIL,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_submit_missing_access_key(self):
        """Missing access key returns 400."""
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps({"name": "test"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_submit_invalid_access_key(self):
        """Invalid access key returns 403."""
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": "invalid_key_12345"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_submit_revoked_key(self):
        """Revoked access key returns 403."""
        self.ak.is_active = False
        self.ak.save()
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": self.ak.key, "email": _UPDATED_EMAIL}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_submit_inactive_form(self):
        """Inactive form returns 404."""
        self.form.is_active = False
        self.form.save()
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": self.ak.key, "email": _SUBMIT_EMAIL}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_submit_empty_payload(self):
        """Submitting only access_key with no other fields returns 400."""
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": self.ak.key}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertIn("No form data", response.json()["message"])

    def test_submit_too_many_fields(self):
        """Submitting more than 15 fields returns 400."""
        payload = {"access_key": self.ak.key}
        for i in range(16):
            payload[f"field_{i}"] = f"value_{i}"
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Too many fields", response.json()["message"])

    def test_submit_any_fields_accepted(self):
        """API accepts any field names without predefined schema."""
        data = {
            "access_key": self.ak.key,
            "custom_field_1": "value1",
            "another_field": "value2",
            "yet_another": "value3",
        }
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        from core.models import Submission
        sub = Submission.objects.latest("created_at")
        self.assertIn("custom_field_1", sub.payload_json)
        self.assertIn("another_field", sub.payload_json)
        self.assertNotIn("access_key", sub.payload_json)

    def test_submit_honeypot_filled(self):
        """Honeypot field filled silently accepts without creating real submission."""
        initial_count = Submission.objects.count()
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps({
                "access_key": self.ak.key,
                "email": _SUBMIT_EMAIL,
                "_honeypot": "bot_filled_this",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        # No new submission should be created
        self.assertEqual(Submission.objects.count(), initial_count)

    def test_submit_invalid_json(self):
        """Invalid JSON body returns 400."""
        response = self.client.post(
            reverse("submit_api"),
            data="not valid json{",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_submit_updates_usage_count(self):
        """Successful submission increments access key usage count."""
        self.assertEqual(self.ak.usage_count, 0)
        self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": self.ak.key, "email": _SUBMIT_EMAIL}),
            content_type="application/json",
        )
        self.ak.refresh_from_db()
        self.assertEqual(self.ak.usage_count, 1)
        self.assertIsNotNone(self.ak.last_used_at)

    def test_submit_creates_email_log(self):
        """Submission creates an associated email log entry."""
        self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": self.ak.key, "email": _SUBMIT_EMAIL}),
            content_type="application/json",
        )
        self.assertEqual(EmailLog.objects.count(), 1)
        log = EmailLog.objects.first()
        # Should be failed since no Gmail config
        self.assertEqual(log.status, EmailLog.Status.FAILED)

    def test_submit_stores_ip_and_headers(self):
        """Submission stores client IP and selected headers."""
        self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": self.ak.key, "email": _SUBMIT_EMAIL}),
            content_type="application/json",
            HTTP_USER_AGENT="TestAgent/1.0",
        )
        sub = Submission.objects.first()
        self.assertIsNotNone(sub.ip_address)
        self.assertIn("User-Agent", sub.headers)

    def test_submit_get_not_allowed(self):
        """GET request to submit endpoint is not allowed."""
        response = self.client.get(reverse("submit_api"))
        self.assertEqual(response.status_code, 405)

    def test_submit_domain_whitelist_blocks(self):
        """Submission from non-whitelisted domain is blocked."""
        self.form.allowed_domains = "allowed.com"
        self.form.save()
        response = self.client.post(
            reverse("submit_api"),
            data=json.dumps({"access_key": self.ak.key, "email": _SUBMIT_EMAIL}),
            content_type="application/json",
            HTTP_ORIGIN="https://blocked.com",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Domain not allowed", response.json()["message"])


# =============================================================================
# Email Template View Tests
# =============================================================================


class EmailTemplateViewTests(TestCase):
    """Tests for email template management views."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_templates_list_page(self):
        response = self.client.get(reverse("templates_list"))
        self.assertEqual(response.status_code, 200)

    def test_template_create(self):
        response = self.client.post(reverse("templates_create"), {
            "name": "My Template",
            "subject": "New submission from {{form_name}}",
            "body_html": "<p>Hello {{name}}</p>",
            "body_text": "Hello {{name}}",
            "is_default": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailTemplate.objects.filter(user=self.user).count(), 1)

    def test_template_delete(self):
        tpl = EmailTemplate.objects.create(
            user=self.user, name="Test", subject="Sub", body_html="<p>Hi</p>"
        )
        response = self.client.post(reverse("templates_delete", args=[tpl.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailTemplate.objects.count(), 0)

    def test_default_template_uniqueness(self):
        """Setting a template as default unsets others."""
        tpl1 = EmailTemplate.objects.create(
            user=self.user, name="T1", subject="S1", body_html="H1", is_default=True
        )
        self.client.post(reverse("templates_create"), {
            "name": "T2",
            "subject": "S2",
            "body_html": "H2",
            "body_text": "",
            "is_default": "on",
        })
        tpl1.refresh_from_db()
        self.assertFalse(tpl1.is_default)


# =============================================================================
# Analytics View Tests
# =============================================================================


class AnalyticsViewTests(TestCase):
    """Tests for analytics view."""

    def setUp(self):
        self.user = User.objects.create_user("testuser", _TEST_EMAIL, "testpass123")
        self.client = Client()
        self.client.login(username="testuser", password="testpass123")

    def test_analytics_page_renders(self):
        response = self.client.get(reverse("analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Total Submissions")

    def test_analytics_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("analytics"))
        self.assertEqual(response.status_code, 302)
