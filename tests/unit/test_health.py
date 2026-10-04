"""Tests for api/routes/health.py's Redis probe (issue #62)."""

import contextlib
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from api.routes.health import health_check


@pytest.mark.unit
class TestHealthCheckRedisProbe:
    """Test suite for the health route's Redis dependency probe."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async db session whose postgres probe succeeds."""
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_redis_probe_builds_client_from_redis_url(self, mock_db):
        """The probe must construct its client from settings.redis_url, not
        the nonexistent settings.redis_host/redis_port fields."""
        with patch("redis.Redis.from_url") as mock_from_url:
            mock_client = Mock()
            mock_client.ping = Mock(return_value=True)
            mock_from_url.return_value = mock_client

            with contextlib.suppress(HTTPException):
                # other dependencies may still be unhealthy in this unit test
                await health_check(db=mock_db)

            mock_from_url.assert_called_once()
            args, kwargs = mock_from_url.call_args
            assert (
                args[0] == "redis://localhost:6379/0"
                or kwargs.get("url") == "redis://localhost:6379/0"
            )

    @pytest.mark.asyncio
    async def test_redis_healthy_when_reachable(self, mock_db):
        """A reachable Redis (ping succeeds) must report dependencies.redis
        as healthy, not unhealthy -- this is the exact field this issue's
        AttributeError used to always flip to unhealthy."""
        with patch("redis.Redis.from_url") as mock_from_url:
            mock_client = Mock()
            mock_client.ping = Mock(return_value=True)
            mock_from_url.return_value = mock_client

            try:
                result = await health_check(db=mock_db)
            except HTTPException as exc:
                result = exc.detail

            assert result["dependencies"]["redis"] == "healthy"

    @pytest.mark.asyncio
    async def test_redis_unhealthy_when_ping_fails(self, mock_db):
        """A genuinely unreachable Redis must still report unhealthy -- the
        fix must not mask real Redis outages."""
        with patch("redis.Redis.from_url") as mock_from_url:
            mock_client = Mock()
            mock_client.ping = Mock(side_effect=ConnectionError("refused"))
            mock_from_url.return_value = mock_client

            try:
                result = await health_check(db=mock_db)
            except HTTPException as exc:
                result = exc.detail

            assert result["dependencies"]["redis"] == "unhealthy"
