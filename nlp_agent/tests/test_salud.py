"""`/health` dice que el proceso vive; `/ready`, que Ollama y el modelo están listos (criterio 2)."""


def test_health_no_depende_de_ollama(api, ollama):
    ollama.caido = True
    r = api.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "servicio": "nlp-agent", "version": "0.1.0"}


def test_ready_listo(api):
    r = api.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "listo", "modelo": "qwen3:8b", "version_ollama": "0.40.5", "version": "0.1.0"}


def test_ready_sin_el_modelo(api, ollama):
    ollama.modelos = ["llama3.1:8b"]
    r = api.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "no_listo", "modelo": "qwen3:8b", "motivo": "modelo_no_descargado"}


def test_ready_sin_ollama(api, ollama):
    ollama.caido = True
    r = api.get("/ready")
    assert r.status_code == 503 and r.json()["motivo"] == "ollama_no_alcanzable"
