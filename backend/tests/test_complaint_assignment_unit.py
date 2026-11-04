"""Unit checks for complaint assignment validation without a database."""
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from app.services.complaint_assignment import validate_assignment


class ComplaintAssignmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_leader_must_belong_to_selected_department(self):
        groups = [{"id": 4, "name": "星座营销中心", "people": [
            {"id": 10, "name": "甲", "responsibilities": ["海洋应用业务投诉"]},
            {"id": 11, "name": "乙", "responsibilities": ["政企业务投诉"]},
        ]}]
        with patch("app.services.complaint_assignment.departments", AsyncMock(return_value=groups)):
            step = await validate_assignment(None, 2103, "海洋应用业务投诉", 4, 10)
            self.assertEqual(step["assigned_owner_id"], 10)
            with self.assertRaises(HTTPException):
                await validate_assignment(None, 2103, "海洋应用业务投诉", 4, 11)
            with self.assertRaises(HTTPException):
                await validate_assignment(None, 2104, "海洋应用业务投诉", 4, 10)

    async def test_empty_draft_can_be_saved(self):
        self.assertIsNone(await validate_assignment(None, 2102, None, None, None, draft=True))
