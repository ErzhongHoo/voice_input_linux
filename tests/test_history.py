from voice_input.history import append_history, clear_history, load_history


def test_append_history_persists_latest_first(tmp_path) -> None:
    path = tmp_path / "history.json"

    append_history("第一条", "mock", path=path)
    entries = append_history("第二条", "doubao", path=path)

    assert [entry.text for entry in entries] == ["第二条", "第一条"]
    assert entries[0].asr_provider == "doubao"
    assert [entry.text for entry in load_history(path)] == ["第二条", "第一条"]


def test_append_history_trims_limit(tmp_path) -> None:
    path = tmp_path / "history.json"

    append_history("one", path=path, max_entries=2)
    append_history("two", path=path, max_entries=2)
    entries = append_history("three", path=path, max_entries=2)

    assert [entry.text for entry in entries] == ["three", "two"]


def test_clear_history_writes_empty_list(tmp_path) -> None:
    path = tmp_path / "history.json"

    append_history("hello", path=path)
    clear_history(path)

    assert load_history(path) == []
