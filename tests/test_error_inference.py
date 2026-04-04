from adktelemetry.store import infer_content_runtime_error


def test_infer_error_prefix_404():
    text = (
        "Error: 404 NOT_FOUND. {'error': {'code': 404, 'message': "
        "'This model is no longer available', 'status': 'NOT_FOUND'}}"
    )
    code, msg = infer_content_runtime_error(text)
    assert code == "NOT_FOUND"
    assert "404" in msg
    assert "no longer available" in msg


def test_infer_error_http_fallback():
    code, msg = infer_content_runtime_error("Error: something weird happened")
    assert code == "RUNTIME_ERROR"
    assert "Error:" in msg


def test_infer_no_error_normal_reply():
    code, msg = infer_content_runtime_error("Olá! Como posso ajudar?")
    assert code is None
    assert msg is None
