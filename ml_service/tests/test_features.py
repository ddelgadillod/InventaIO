"""INV-20 — FeatureStore y determinar_rama, con un snapshot chico armado
en el propio test (no el real, para no depender del pipeline completo)."""
import pandas as pd
import pytest

from prediccion.features import FeatureStore, determinar_rama


@pytest.fixture()
def snapshot_chico(tmp_path):
    df = pd.DataFrame(
        [
            {
                "codigo_item": "P1", "sucursal": "PRINCIPAL", "familia_modelo": "suave",
                "cond2_perecedero": 0, "fecha_origen": pd.Timestamp("2025-12-01"), "trail_15": 5.0,
            },
            {
                "codigo_item": "P2", "sucursal": "LA 21", "familia_modelo": "suave",
                "cond2_perecedero": 1, "fecha_origen": pd.Timestamp("2025-12-01"), "trail_15": 3.0,
            },
            {
                "codigo_item": "P3", "sucursal": "GLORIETA", "familia_modelo": "intermitente",
                "cond2_perecedero": 0, "fecha_origen": pd.Timestamp("2025-12-01"), "trail_15": 1.0,
            },
        ]
    )
    path = tmp_path / "snapshot.parquet"
    df.to_parquet(path, index=False)
    return FeatureStore(path)


def test_busca_par_existente(snapshot_chico):
    fila = snapshot_chico.buscar("P1", "PRINCIPAL")
    assert fila is not None
    assert len(fila) == 1
    assert fila.iloc[0]["trail_15"] == 5.0


def test_par_inexistente_devuelve_none(snapshot_chico):
    assert snapshot_chico.buscar("NOEXISTE", "PRINCIPAL") is None


def test_snapshot_faltante_lanza_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        FeatureStore(tmp_path / "no_existe.parquet")


def test_determinar_rama_intermitente():
    fila = pd.Series({"familia_modelo": "intermitente", "cond2_perecedero": 0})
    assert determinar_rama(fila) == "intermitente"


def test_determinar_rama_suave_perecedero():
    fila = pd.Series({"familia_modelo": "suave", "cond2_perecedero": 1})
    assert determinar_rama(fila) == "suave_perecedero"


def test_determinar_rama_suave_no_perecedero():
    fila = pd.Series({"familia_modelo": "suave", "cond2_perecedero": 0})
    assert determinar_rama(fila) == "suave_no_perecedero"
