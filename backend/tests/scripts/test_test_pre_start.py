from unittest.mock import AsyncMock, MagicMock, patch

from app.tests_pre_start import init, logger


def test_init_successful_connection() -> None:
    mock_client_instance = MagicMock()
    mock_admin = MagicMock()
    mock_admin.command = AsyncMock(return_value={"ok": 1})
    mock_client_instance.admin = mock_admin
    mock_client_instance.close = MagicMock()

    with (
        patch(
            "app.tests_pre_start.AsyncMongoClient",
            return_value=mock_client_instance,
        ),
        patch.object(logger, "info"),
        patch.object(logger, "error"),
        patch.object(logger, "warn"),
    ):
        import asyncio

        try:
            asyncio.run(init())
            connection_successful = True
        except Exception:
            connection_successful = False

        assert connection_successful, (
            "The database connection should be successful and not raise an exception."
        )

        mock_admin.command.assert_called_once_with("ping")
