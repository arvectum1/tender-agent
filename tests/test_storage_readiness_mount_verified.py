from __future__ import annotations

import pytest

from src.shared.storage import capacity


@pytest.mark.parametrize("mount_verified", [True, False])
def test_storage_metrics_exposes_mount_verified(monkeypatch, mount_verified: bool) -> None:
    snapshot = capacity.StorageSnapshot(
        filesystem_total_bytes=100,
        filesystem_free_bytes=50,
        used_percent=50.0,
        state=capacity.StorageState.NORMAL,
        mount_verified=mount_verified,
    )
    monkeypatch.setattr(capacity, "get_storage_snapshot", lambda: snapshot)

    metrics = capacity.storage_metrics_dict()

    assert "mount_verified" in metrics
    assert metrics["mount_verified"] is mount_verified
