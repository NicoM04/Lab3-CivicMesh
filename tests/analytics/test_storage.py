from civicmesh.analytics import write_metric, read_metrics


def test_write_metric(tmp_path):
    metric = {
        "peer_id": "peer-1",
        "topic": "Santiago",
        "channel": "objetivo",
        "value": 20,
    }

    file_path = write_metric(
        tmp_path,
        "peer-1",
        metric,
    )

    assert file_path.exists()


def test_read_metrics(tmp_path):
    metric = {
        "peer_id": "peer-1",
        "topic": "Santiago",
        "channel": "objetivo",
        "value": 20,
    }

    write_metric(
        tmp_path,
        "peer-1",
        metric,
    )

    records = read_metrics(tmp_path)

    assert len(records) == 1
    assert records[0]["peer_id"] == "peer-1"
    assert records[0]["value"] == 20


def test_multiple_metrics(tmp_path):
    write_metric(
        tmp_path,
        "peer-1",
        {"value": 10},
    )

    write_metric(
        tmp_path,
        "peer-1",
        {"value": 20},
    )

    records = read_metrics(tmp_path)

    assert len(records) == 2


def test_read_missing_directory(tmp_path):
    records = read_metrics(
        tmp_path / "no-existe"
    )

    assert records == []