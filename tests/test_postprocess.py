from voice_input.postprocess.processor import TextPostProcessor


def test_removes_leading_fillers_and_adds_chinese_period() -> None:
    processor = TextPostProcessor()
    assert processor.process("嗯，今天我们测试一下") == "今天我们测试一下。"


def test_normalizes_chinese_punctuation() -> None:
    processor = TextPostProcessor()
    assert processor.process("你好,可以吗?") == "你好，可以吗？"


def test_english_period() -> None:
    processor = TextPostProcessor()
    assert processor.process("um hello world") == "hello world."


def test_can_disable_appended_final_punctuation() -> None:
    processor = TextPostProcessor(append_final_punctuation=False)
    assert processor.process("嗯，今天我们测试一下") == "今天我们测试一下"


def test_disabled_final_punctuation_keeps_asr_punctuation() -> None:
    processor = TextPostProcessor(append_final_punctuation=False)
    assert processor.process("你好,可以吗?") == "你好，可以吗？"
