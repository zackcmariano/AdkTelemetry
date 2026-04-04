import pytest

from adktelemetry.agentelemetry import agentelemetry


def test_agentelemetry_requires_modelkey():
    with pytest.raises(ValueError, match="modelkey"):
        agentelemetry(modelkey="")

    with pytest.raises(ValueError, match="modelkey"):
        agentelemetry(modelkey="   ")
