"""Password checks retain the bound identity after a local username correction."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.auth import verify_bound_password


class CasdoorAliasTests(unittest.IsolatedAsyncioTestCase):
    async def test_retained_provider_name_must_match_bound_subject(self):
        user = SimpleNamespace(username='new-name', casdoor_login_username='old-name', casdoor_subject='subject')
        verify = AsyncMock(side_effect=[HTTPException(401), 'subject'])
        with patch('app.api.v1.auth.verify_password_subject', verify):
            self.assertTrue(await verify_bound_password(user, 'password'))
        self.assertEqual([call.args[0] for call in verify.await_args_list], ['new-name', 'old-name'])

    async def test_other_provider_identity_is_not_accepted(self):
        user = SimpleNamespace(username='new-name', casdoor_login_username='old-name', casdoor_subject='subject')
        with patch('app.api.v1.auth.verify_password_subject', AsyncMock(return_value='different')):
            self.assertFalse(await verify_bound_password(user, 'password'))

    async def test_provider_failure_is_not_hidden(self):
        user = SimpleNamespace(username='new-name', casdoor_login_username='old-name', casdoor_subject='subject')
        with patch('app.api.v1.auth.verify_password_subject', AsyncMock(side_effect=HTTPException(503))):
            with self.assertRaises(HTTPException) as error:
                await verify_bound_password(user, 'password')
        self.assertEqual(error.exception.status_code, 503)
