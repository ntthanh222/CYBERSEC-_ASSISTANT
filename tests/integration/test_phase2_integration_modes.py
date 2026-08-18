import os


def test_readiness_mode_allows_not_ready_modules():
    assert os.environ.get("PHASE2_CONTRACT_MODE", "readiness") == "readiness"


def test_required_mode_must_be_explicit():
    assert os.environ.get("PHASE2_REQUIRED_CONFIRMED") != "1"


if __name__ == "__main__":
    test_readiness_mode_allows_not_ready_modules()
    test_required_mode_must_be_explicit()
    print("phase2 integration mode checks passed")
